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

from typing import Optional

from .caller import CallResult, make_chat_call
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
                  if the first provider tried answered. Reset on every send().

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

    def clear(self) -> None:
        """Forget the conversation (the system prompt and settings are kept)."""
        self.messages = []
        self.last_fallback_from = None

    def __repr__(self) -> str:
        return f"ChatSession(turns={len(self.messages) // 2}, preferred='{self.preferred_provider}')"
