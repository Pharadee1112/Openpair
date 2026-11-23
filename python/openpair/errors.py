"""
openpair.errors — shared classification for transient/retryable API errors
=============================================================================
Used by both the benchmark runner (retry the same provider) and the client
(fall back to a different provider): 429 rate limit / quota exhaustion, or
503 overloaded/unavailable are worth retrying — anything else is not.
"""

from __future__ import annotations


def is_retryable_error(error: Exception) -> bool:
    """True if `error` looks like a transient 429 rate-limit or 503 overloaded/unavailable error."""
    msg = str(error)
    return (
        "429" in msg
        or "503" in msg
        or "RESOURCE_EXHAUSTED" in msg
        or "UNAVAILABLE" in msg
        or "overloaded" in msg.lower()
        or "rate_limit_exceeded" in msg.lower()
        or "rate limit" in msg.lower()
    )


class LocalModeError(RuntimeError):
    """
    Raised when local-only mode refuses or cannot complete a request: a non-Ollama
    provider was requested, the Ollama URL is not a loopback address, Ollama is
    unreachable, or the local model is missing. Never retried and never falls back
    to a cloud provider.
    """


class NoProviderError(RuntimeError):
    """
    Raised when no provider can serve a request: no GOOGLE_API_KEY / GROQ_API_KEY and no
    reachable Ollama. A RuntimeError subclass with the same message as before, so existing
    `except RuntimeError` code keeps working; `openpair chat` uses the type to print a
    friendlier, actionable message.
    """
