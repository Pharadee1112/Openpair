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

from .caller import CallResult, make_chat_call, make_chat_stream
from .client import OpenPair


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
    ) -> None:
        self._client = client
        self.system = system
        self.preferred_provider = preferred_provider
        self.max_tokens = max_tokens
        self.messages: list[dict] = []
        self.last_fallback_from: Optional[str] = None
        self.last_result: Optional[CallResult] = None

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

        # Work on a copy: self.messages only changes once the call has succeeded.
        history = self.messages + [{"role": "user", "content": user_text}]

        def dispatch(provider: str, model_id: str, api_key: str):
            return make_chat_call(
                provider   = provider,
                model_id   = model_id,
                messages   = history,
                api_key    = api_key,
                system     = self.system,
                max_tokens = self.max_tokens,
            )

        # Tradeoff: routing looks only at the latest user message. Complexity,
        # language (Thai/English) and tier are decided from `user_text` alone, so
        # an earlier turn that made the conversation "hard" is ignored, and a short
        # follow-up like "why?" may be routed to a cheaper model than the context
        # deserves. The whole history is still sent to whichever model is chosen.
        result, failed = self._client._call_with_fallback(
            route_prompt       = user_text,
            preferred_provider = self.preferred_provider,
            fallback_providers = None,
            dispatch           = dispatch,
        )

        self.messages = history + [{"role": "assistant", "content": result.response_text}]
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
        history = self.messages + [{"role": "user", "content": user_text}]

        def open_stream(provider: str, model_id: str, api_key: str):
            return make_chat_stream(
                provider   = provider,
                model_id   = model_id,
                messages   = history,
                api_key    = api_key,
                system     = self.system,
                max_tokens = self.max_tokens,
            )

        # Same routing tradeoff as send(): routed from the latest user message only.
        result, failed = yield from self._client._stream_with_fallback(
            route_prompt       = user_text,
            preferred_provider = self.preferred_provider,
            fallback_providers = None,
            open_stream        = open_stream,
        )

        self.messages = history + [{"role": "assistant", "content": result.response_text}]
        self.last_fallback_from = failed[-1] if failed else None
        self.last_result = result

    def clear(self) -> None:
        """Forget the conversation (the system prompt and settings are kept)."""
        self.messages = []
        self.last_fallback_from = None
        self.last_result = None

    def __repr__(self) -> str:
        return f"ChatSession(turns={len(self.messages) // 2}, preferred='{self.preferred_provider}')"
