"""
openpair.session — multi-turn chat on top of the OpenPair router
==================================================================
Usage:
    from openpair import OpenPair, ChatSession

    session = ChatSession(OpenPair(), system="Answer in Thai.")
    session.send("My name is Mali.")
    result = session.send("What is my name?")   # the model sees the whole history
    print(result.response_text, session.last_fallback_from)
"""

from __future__ import annotations

from typing import Iterator, Optional

from .attach import Attachment, check_pending_caps, render_attachments
from .caller import CallResult, is_loopback_url, make_chat_call, make_chat_stream
from .client import OpenPair


class ConfirmationRequired(Exception):
    """
    Attached-file text would be sent to a cloud provider the user has not approved.
    Raised before anything is sent. `provider` is the provider that would receive it.
    The chat REPL asks y/N and calls ChatSession.confirm_cloud(provider) on "y".
    """

    def __init__(self, provider: str, label: str) -> None:
        super().__init__(f"sending attached file text to {label} needs confirmation")
        self.provider = provider
        self.label = label


class ChatSession:
    """
    Keeps a conversation history and sends all of it on every turn, through the
    same routing and fallback chain as OpenPair.call()
    (routed provider -> groq -> google -> Ollama).

    Args:
        client: The OpenPair instance that owns the API keys and routing.
        system: System prompt. Kept separate: it is never stored in `messages`.
        preferred_provider: Pin routing to one provider for this session
                            (falls back to the client's own pin if None).
        max_tokens: Maximum tokens per response.
        local_only: Local-only mode. When True, requests can only go to Ollama on a
                    loopback URL: cloud keys are ignored, there is no cloud fallback,
                    and anything else is refused with a LocalModeError. Default False.

    Attributes:
        messages: The history as a list of {"role": "user" | "assistant",
                  "content": str}. Always alternates user, assistant, ...
        last_fallback_from: After send(), the provider that failed (with a
                  transient error) right before the one that answered, or None
                  if the first provider tried answered. Reset on every send()/stream().
        last_result: After a stream() has finished successfully, the CallResult
                  (model, provider, tier, tokens, latency, full text). None before
                  that, and reset to None when a new stream() starts or fails.

    The response cache is deliberately NOT used: its key only covers a single
    prompt, so a cached answer could ignore the conversation so far.
    """

    def __init__(
        self,
        client: OpenPair,
        system: Optional[str] = None,
        preferred_provider: Optional[str] = None,
        max_tokens: int = 2048,
        local_only: bool = False,
    ) -> None:
        self._client = client
        self.system = system
        self.preferred_provider = preferred_provider
        self.max_tokens = max_tokens
        self.local_only = local_only
        self.messages: list[dict] = []
        self.last_fallback_from: Optional[str] = None
        self.last_result: Optional[CallResult] = None

        # -- Attachments (see openpair.attach) --------------------------------
        # `messages` is the in-memory history that is SENT to the model, so a user
        # message that carried files contains their text. Everything that is SAVED
        # goes through typed_messages() / sent_attachments instead and never has it.
        self.pending_attachments: list[Attachment] = []   # buffered by /add, sent with the next turn
        self.sent_attachments: list[dict] = []            # {path, sha256, chars} of files already sent
        self._typed: dict[int, str] = {}                  # history index -> what the user typed
        self._history_has_attachment_text = False
        self._confirmed_cloud: set[str] = set()           # cloud providers the user said "y" to
        self.resumed_attachments: list[dict] = []         # refs loaded from a saved session (kept when saving)
        self.clear_count = 0                              # bumped by clear(); a new saved session starts after it

    # -- Attachments ---------------------------------------------------------

    def add_attachment(self, att: Attachment) -> None:
        """Buffer a validated file for the next turn (replaces the same path). Raises
        AttachError if the 5 files / 128 KB pending caps would be exceeded. Any earlier
        cloud confirmation is dropped: the new text has not been approved yet."""
        check_pending_caps(self.pending_attachments, att)
        self.pending_attachments = [a for a in self.pending_attachments if a.path != att.path]
        self.pending_attachments.append(att)
        self._confirmed_cloud.clear()

    @property
    def attachment_text_unconfirmed(self) -> bool:
        """History contains attachment text and no cloud provider has been confirmed for
        it (e.g. it was added and sent in local mode). Cloud sends ask until "y" or /clear."""
        return self._history_has_attachment_text and not self._confirmed_cloud

    def typed_messages(self) -> list[dict]:
        """The history as the user typed it: same roles and order as `messages`, but with
        no attachment text. This is what gets saved."""
        return [
            {"role": m["role"], "content": self._typed.get(i, m["content"])}
            for i, m in enumerate(self.messages)
        ]

    def confirm_cloud(self, provider: str) -> None:
        self._confirmed_cloud.add(provider)

    def _cloud_target(self, user_text: str):
        """
        (provider, label, remote) that would get the next request in cloud mode: the first
        usable provider of the router's chain, found without any API call. `remote` is
        False only for Ollama on a loopback URL.
        """
        first = next(self._client._candidates(user_text, self.preferred_provider, None))
        provider = first[0]
        if provider == "ollama":
            url = self._client.local_ollama_url()
            if is_loopback_url(url):
                return provider, "ollama (this machine)", False
            return provider, f"ollama at {url}", True
        return provider, provider, True

    def cloud_confirmation_needed(self, user_text: str):
        """(provider, label) if sending `user_text` now would put attachment text in front
        of a cloud provider the user has not confirmed, else None. No API call."""
        if self.local_only or not (self.pending_attachments or self._history_has_attachment_text):
            return None
        provider, label, remote = self._cloud_target(user_text)
        if remote and provider not in self._confirmed_cloud:
            return provider, label
        return None

    def _prepare(self, user_text: str):
        """
        -> (content, attachments, pin). `content` is the user message as sent (attachment
        block first). `pin` is the provider this ONE call must be restricted to, with no
        fallback, or None. Whenever attachment text would be in the request in cloud mode
        the call is pinned to the confirmed provider, so no other cloud provider can get it.
        """
        attachments = list(self.pending_attachments)
        content = render_attachments(attachments) + user_text if attachments else user_text
        pin = None
        if not self.local_only and (attachments or self._history_has_attachment_text):
            provider, label, remote = self._cloud_target(user_text)
            if remote and provider not in self._confirmed_cloud:
                raise ConfirmationRequired(provider, label)
            pin = provider
        return content, attachments, pin

    def _commit(self, history: list, user_text: str, attachments: list, reply: str) -> None:
        index = len(self.messages)  # where the new user message lands
        self.messages = history + [{"role": "assistant", "content": reply}]
        if attachments:
            self._typed[index] = user_text
            self._history_has_attachment_text = True
            known = {a["path"]: i for i, a in enumerate(self.sent_attachments)}
            for a in attachments:
                if a.path in known:
                    self.sent_attachments[known[a.path]] = a.ref()
                else:
                    self.sent_attachments.append(a.ref())
            self.pending_attachments = []

    def send(self, user_text: str) -> CallResult:
        """
        Add `user_text` to the conversation, get the reply, and return it.

        On success both the user message and the assistant reply are appended to
        `messages`. On any failure `messages` is left exactly as it was before
        the call, so roles still alternate and the same text can be re-sent.
        """
        if not isinstance(user_text, str) or not user_text.strip():
            raise ValueError("user_text must be a non-empty string")

        self.last_fallback_from = None

        content, attachments, pin = self._prepare(user_text)
        # Work on a copy: self.messages only changes once the call has succeeded.
        history = self.messages + [{"role": "user", "content": content}]

        def dispatch(provider: str, model_id: str, api_key: str):
            return make_chat_call(
                provider   = provider,
                model_id   = model_id,
                messages   = history,
                api_key    = api_key,
                system     = self.system,
                max_tokens = self.max_tokens,
                **self._policy_kwargs(),
            )

        # Tradeoff: routing looks only at the latest user message. Complexity,
        # language (Thai/English) and tier are decided from `user_text` alone, so
        # an earlier turn that made the conversation "hard" is ignored, and a short
        # follow-up like "why?" may be routed to a cheaper model than the context
        # deserves. The whole history is still sent to whichever model is chosen.
        result, failed = self._client._call_with_fallback(
            route_prompt       = user_text,
            preferred_provider = pin or self.preferred_provider,
            fallback_providers = None,
            dispatch           = dispatch,
            local_only         = self.local_only,
            no_fallback        = pin is not None,
        )

        self._commit(history, user_text, attachments, result.response_text)
        self.last_fallback_from = failed[-1] if failed else None
        return result

    def stream(self, user_text: str) -> Iterator[str]:
        """
        Like send(), but a generator that yields the reply in text chunks as they arrive.

        When it is exhausted, `last_result` and `last_fallback_from` are set and the
        user message + full reply are appended to `messages`. If the stream fails or
        is closed early (cancelled), `messages` is left exactly as it was.

        Fallback: another provider is tried only if the first one failed before
        yielding any text; after that, the error is raised (providers never mix in
        one reply). Errors (including an empty user_text) surface on the first next().
        """
        if not isinstance(user_text, str) or not user_text.strip():
            raise ValueError("user_text must be a non-empty string")

        self.last_fallback_from = None
        self.last_result = None
        content, attachments, pin = self._prepare(user_text)
        history = self.messages + [{"role": "user", "content": content}]

        def open_stream(provider: str, model_id: str, api_key: str):
            return make_chat_stream(
                provider   = provider,
                model_id   = model_id,
                messages   = history,
                api_key    = api_key,
                system     = self.system,
                max_tokens = self.max_tokens,
                **self._policy_kwargs(),
            )

        # Same routing tradeoff as send(): routed from the latest user message only.
        result, failed = yield from self._client._stream_with_fallback(
            route_prompt       = user_text,
            preferred_provider = pin or self.preferred_provider,
            fallback_providers = None,
            open_stream        = open_stream,
            local_only         = self.local_only,
            no_fallback        = pin is not None,
        )

        self._commit(history, user_text, attachments, result.response_text)
        self.last_fallback_from = failed[-1] if failed else None
        self.last_result = result

    def route(self, text: str):
        """
        Dry run: the routing decision for `text` (honouring the provider pin) without
        any API call and without touching the history. In local mode the request would
        still run on Ollama; this only shows what the router itself would pick.
        """
        return self._client.route(text, preferred_provider=self.preferred_provider)

    def _policy_kwargs(self) -> dict:
        """Extra arguments for the low-level dispatchers; empty when local mode is off."""
        if not self.local_only:
            return {}
        return {"local_only": True, "ollama_base_url": self._client.local_ollama_url()}

    def clear(self) -> None:
        """Forget the conversation, attachments and cloud confirmations (system prompt and settings are kept)."""
        self.messages = []
        self.last_fallback_from = None
        self.last_result = None
        self.pending_attachments = []
        self.sent_attachments = []
        self._typed = {}
        self._history_has_attachment_text = False
        self._confirmed_cloud = set()
        self.resumed_attachments = []
        self.clear_count += 1

    def __repr__(self) -> str:
        return f"ChatSession(turns={len(self.messages) // 2}, preferred='{self.preferred_provider}')"
