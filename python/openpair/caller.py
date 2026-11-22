"""
openpair.caller — Real API call layer
=======================================
Makes actual HTTP calls to OpenAI, Anthropic, Google AI, Groq, OpenRouter, and Ollama.
Called by OpenPair.call() after routing decides which model to use.
"""

from __future__ import annotations

import ipaddress
import os
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

from .errors import LocalModeError

DEFAULT_OLLAMA_URL = "http://localhost:11434"


@dataclass
class CallResult:
    """Full result of an API call, including routing metadata."""
    # Routing info
    model_id:          str
    model_name:        str
    provider:          str
    tier:              str
    complexity_score:  int
    routing_reason:    str
    cost_per_1k_input: float

    # Response info
    response_text:     str
    input_tokens:      int
    output_tokens:     int
    latency_ms:        float
    from_cache:        bool = False

    @property
    def estimated_cost(self) -> float:
        """Approximate cost of this call in USD. Cache hits cost nothing — no API call was made."""
        if self.from_cache:
            return 0.0
        return (self.input_tokens / 1000) * self.cost_per_1k_input

    def __repr__(self) -> str:
        return (
            f"CallResult(model='{self.model_name}', "
            f"score={self.complexity_score}/10, "
            f"tokens={self.input_tokens}+{self.output_tokens}, "
            f"latency={self.latency_ms:.0f}ms)"
        )


# ── Chat messages ───────────────────────────────────────────────────────────
#
# A chat message is a dict {"role": "system" | "user" | "assistant", "content": str}.
# Every provider caller below accepts either a single `prompt` string (the original
# behaviour) or a `messages` list (multi-turn). Providers disagree on how a
# conversation must be shaped, so each caller converts the neutral list itself.

_VALID_ROLES = ("system", "user", "assistant")


def _normalize_messages(
    prompt: Optional[str],
    messages: Optional[list],
    system: Optional[str],
) -> tuple[Optional[str], list[dict]]:
    """
    Validate the input and return (system_text, turns).

    - `prompt` and `messages` are alternatives: exactly one must be given.
    - Any {"role": "system"} messages are pulled out and merged with the `system`
      argument (blank-line separated), because Anthropic and Gemini take the
      system prompt outside the conversation.
    - `turns` holds only {"role", "content"} dicts with role "user" or "assistant".
    """
    if prompt is not None and messages is not None:
        raise ValueError("Pass either prompt or messages, not both")
    if messages is None:
        if prompt is None:
            raise ValueError("Either prompt or messages is required")
        messages = [{"role": "user", "content": prompt}]
    if not messages:
        raise ValueError("messages must not be empty")

    system_parts = [system] if system else []
    turns: list[dict] = []
    for i, msg in enumerate(messages):
        role = msg.get("role")
        content = msg.get("content")
        if role not in _VALID_ROLES:
            raise ValueError(f"messages[{i}]: role must be one of {_VALID_ROLES}, got {role!r}")
        if not isinstance(content, str):
            raise ValueError(f"messages[{i}]: content must be a string")
        if role == "system":
            system_parts.append(content)
        else:
            turns.append({"role": role, "content": content})

    if not turns:
        raise ValueError("messages must contain at least one user or assistant message")
    return ("\n\n".join(system_parts) or None), turns


def _openai_style_messages(system: Optional[str], turns: list[dict]) -> list[dict]:
    """OpenAI-compatible APIs take the system prompt as the first message in the list."""
    out: list[dict] = []
    if system:
        out.append({"role": "system", "content": system})
    out.extend(turns)
    return out


# ── OpenAI ──────────────────────────────────────────────────────────────────

def call_openai(
    model_id: str,
    prompt: Optional[str],
    api_key: str,
    system: Optional[str] = None,
    max_tokens: int = 2048,
    messages: Optional[list] = None,
) -> tuple[str, int, int]:
    """
    Call OpenAI Chat Completions API.
    Pass a single `prompt` or a multi-turn `messages` list (not both).
    Returns (response_text, input_tokens, output_tokens).
    """
    try:
        import openai
    except ImportError:
        raise ImportError("Install openai: pip install openai")

    system_text, turns = _normalize_messages(prompt, messages, system)
    client = openai.OpenAI(api_key=api_key)

    resp = client.chat.completions.create(
        model=model_id,
        messages=_openai_style_messages(system_text, turns),
        max_tokens=max_tokens,
    )

    text          = resp.choices[0].message.content or ""
    input_tokens  = resp.usage.prompt_tokens
    output_tokens = resp.usage.completion_tokens
    return text, input_tokens, output_tokens


# ── Anthropic ────────────────────────────────────────────────────────────────

def call_anthropic(
    model_id: str,
    prompt: Optional[str],
    api_key: str,
    system: Optional[str] = None,
    max_tokens: int = 2048,
    messages: Optional[list] = None,
) -> tuple[str, int, int]:
    """
    Call Anthropic Messages API.
    Pass a single `prompt` or a multi-turn `messages` list (not both).
    The system prompt goes in the top-level `system` field, never in `messages`.
    Returns (response_text, input_tokens, output_tokens).
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError("Install anthropic: pip install anthropic")

    system_text, turns = _normalize_messages(prompt, messages, system)
    client = anthropic.Anthropic(api_key=api_key)
    kwargs: dict = dict(
        model=model_id,
        max_tokens=max_tokens,
        messages=turns,
    )
    if system_text:
        kwargs["system"] = system_text

    resp = client.messages.create(**kwargs)

    text          = resp.content[0].text if resp.content else ""
    input_tokens  = resp.usage.input_tokens
    output_tokens = resp.usage.output_tokens
    return text, input_tokens, output_tokens


# ── Google ───────────────────────────────────────────────────────────────────

def _google_request(api_key: str, system_text: Optional[str], turns: list[dict], max_tokens: int):
    """Build (client, config, contents) for a Gemini call; shared by call_google and the streamer."""
    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=api_key)
    config = genai_types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        system_instruction=system_text,
    )

    # Gemini role names: "user" stays "user", "assistant" becomes "model".
    gemini_role = {"user": "user", "assistant": "model"}
    contents = [
        genai_types.Content(
            role=gemini_role[t["role"]],
            parts=[genai_types.Part(text=t["content"])],
        )
        for t in turns
    ]
    return client, config, contents


def call_google(
    model_id: str,
    prompt: Optional[str],
    api_key: str,
    system: Optional[str] = None,
    max_tokens: int = 2048,
    messages: Optional[list] = None,
) -> tuple[str, int, int]:
    """
    Call Google Generative AI (Gemini) API via the new google-genai SDK.
    Pass a single `prompt` or a multi-turn `messages` list (not both).
    Gemini names the assistant role "model" and takes the system prompt
    separately (`system_instruction`), not inside `contents`.
    Returns (response_text, input_tokens, output_tokens).
    """
    try:
        import google.genai  # noqa: F401
    except ImportError:
        raise ImportError("Install google-genai: pip install google-genai")

    system_text, turns = _normalize_messages(prompt, messages, system)
    client, config, contents = _google_request(api_key, system_text, turns, max_tokens)

    resp = client.models.generate_content(
        model=model_id,
        contents=contents,
        config=config,
    )

    text = resp.text or ""

    # Token counts
    try:
        input_tokens  = resp.usage_metadata.prompt_token_count or 0
        output_tokens = resp.usage_metadata.candidates_token_count or 0
    except AttributeError:
        input_tokens  = sum(len(t["content"].split()) for t in turns)   # rough estimate
        output_tokens = len(text.split())

    return text, input_tokens, output_tokens


# ── Groq ─────────────────────────────────────────────────────────────────────

def call_groq(
    model_id: str,
    prompt: Optional[str],
    api_key: str,
    system: Optional[str] = None,
    max_tokens: int = 2048,
    messages: Optional[list] = None,
) -> tuple[str, int, int]:
    """
    Call Groq API (OpenAI-compatible endpoint).
    Pass a single `prompt` or a multi-turn `messages` list (not both).
    Returns (response_text, input_tokens, output_tokens).
    """
    try:
        import openai
    except ImportError:
        raise ImportError("Install openai: pip install openai")

    system_text, turns = _normalize_messages(prompt, messages, system)
    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )

    resp = client.chat.completions.create(
        model=model_id,
        messages=_openai_style_messages(system_text, turns),
        max_tokens=max_tokens,
    )

    text          = resp.choices[0].message.content or ""
    input_tokens  = resp.usage.prompt_tokens
    output_tokens = resp.usage.completion_tokens
    return text, input_tokens, output_tokens


# ── OpenRouter ───────────────────────────────────────────────────────────────

def call_openrouter(
    model_id: str,
    prompt: Optional[str],
    api_key: str,
    system: Optional[str] = None,
    max_tokens: int = 2048,
    messages: Optional[list] = None,
) -> tuple[str, int, int]:
    """
    Call OpenRouter (OpenAI-compatible endpoint, hosts many open-source models).
    model_id is OpenRouter's own ID, e.g. "meta-llama/llama-3.3-70b-instruct".
    Pass a single `prompt` or a multi-turn `messages` list (not both).
    Returns (response_text, input_tokens, output_tokens).
    """
    try:
        import openai
    except ImportError:
        raise ImportError("Install openai: pip install openai")

    system_text, turns = _normalize_messages(prompt, messages, system)
    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )

    resp = client.chat.completions.create(
        model=model_id,
        messages=_openai_style_messages(system_text, turns),
        max_tokens=max_tokens,
    )

    text          = resp.choices[0].message.content or ""
    input_tokens  = resp.usage.prompt_tokens if resp.usage else 0
    output_tokens = resp.usage.completion_tokens if resp.usage else 0
    return text, input_tokens, output_tokens


# ── Ollama (local) ──────────────────────────────────────────────────────────

def call_ollama(
    model_id: str,
    prompt: Optional[str],
    api_key: str,
    system: Optional[str] = None,
    max_tokens: int = 2048,
    messages: Optional[list] = None,
    base_url: Optional[str] = None,
) -> tuple[str, int, int]:
    """
    Call a local Ollama server (OpenAI-compatible endpoint). No auth required.
    Pass a single `prompt` or a multi-turn `messages` list (not both).
    `base_url` overrides the OLLAMA_BASE_URL environment variable (local-only mode
    passes the exact URL it validated, so the check and the call use the same value).
    Returns (response_text, input_tokens, output_tokens).
    """
    try:
        import openai
    except ImportError:
        raise ImportError("Install openai: pip install openai")

    system_text, turns = _normalize_messages(prompt, messages, system)
    base_url = base_url or os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL)
    client = openai.OpenAI(api_key="ollama", base_url=f"{base_url}/v1")

    resp = client.chat.completions.create(
        model=model_id,
        messages=_openai_style_messages(system_text, turns),
        max_tokens=max_tokens,
    )

    text          = resp.choices[0].message.content or ""
    input_tokens  = resp.usage.prompt_tokens if resp.usage else 0
    output_tokens = resp.usage.completion_tokens if resp.usage else 0
    return text, input_tokens, output_tokens


# ── Dispatcher ───────────────────────────────────────────────────────────────

_CALLERS = {
    "openai":    call_openai,
    "anthropic": call_anthropic,
    "google":    call_google,
    "groq":      call_groq,
    "openrouter": call_openrouter,
    "ollama":    call_ollama,
}


# ── Local-only policy ────────────────────────────────────────────────────────

def is_loopback_url(url: str) -> bool:
    """True if `url` is http(s) and its host is localhost or a loopback IP (127.x, ::1)."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _enforce_local_only(provider: str, ollama_base_url: Optional[str]) -> str:
    """
    The lowest-level guard of local-only mode, run before any network I/O.
    Refuses every provider except Ollama and any non-loopback Ollama URL.
    Returns the validated Ollama base URL.
    """
    if provider != "ollama":
        raise LocalModeError(
            f"Local mode is on: refusing to send a request to the cloud provider {provider!r}."
        )
    url = ollama_base_url or os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL)
    if not is_loopback_url(url):
        raise LocalModeError(
            f"Local mode is on: refusing Ollama URL {url!r} because it is not a loopback "
            f"address (localhost, 127.0.0.1 or ::1)."
        )
    return url


def _friendly_ollama_error(error: Exception, url: str, model_id: str) -> Exception:
    """Map low-level Ollama failures to short messages without a traceback."""
    if isinstance(error, LocalModeError):
        return error
    if getattr(error, "status_code", None) == 404:
        return LocalModeError(
            f"model {model_id} not found, run `ollama pull {model_id}` or set OLLAMA_MODEL"
        )
    if isinstance(error, OSError) or type(error).__name__ in ("APIConnectionError", "APITimeoutError"):
        return LocalModeError(f"Ollama was not reachable at {url}")
    return error


def make_chat_call(
    *,
    provider:   str,
    model_id:   str,
    messages:   list,
    api_key:    str,
    system:     Optional[str] = None,
    max_tokens: int = 2048,
    local_only: bool = False,
    ollama_base_url: Optional[str] = None,
) -> tuple[str, int, int, float]:
    """
    Dispatch a multi-turn conversation to the correct provider and measure latency.
    `messages` is a list of {"role": "user" | "assistant" | "system", "content": str}.
    With `local_only=True` only Ollama on a loopback URL is allowed (see
    _enforce_local_only) and `ollama_base_url` is the URL used for the call.
    Returns (response_text, input_tokens, output_tokens, latency_ms).
    """
    caller = _CALLERS.get(provider)
    if caller is None:
        raise ValueError(f"Unknown provider: {provider!r}. Expected one of {list(_CALLERS)}")

    extra: dict = {}
    if local_only:
        extra["base_url"] = _enforce_local_only(provider, ollama_base_url)

    t0 = time.perf_counter()
    try:
        text, in_tok, out_tok = caller(model_id, None, api_key, system, max_tokens, messages=messages, **extra)
    except Exception as e:
        if local_only:
            raise _friendly_ollama_error(e, extra["base_url"], model_id) from e
        raise
    latency_ms = (time.perf_counter() - t0) * 1000

    return text, in_tok, out_tok, latency_ms


# ── Streaming ────────────────────────────────────────────────────────────────
#
# A streamer is a generator: it yields non-empty text chunks as they arrive and
# RETURNS (input_tokens, output_tokens) when the stream ends (read it with
# `yield from` or StopIteration.value). Token counts are 0 when the provider
# did not report usage. make_chat_stream() adds the latency.

def _stream_openai_compat(client, model_id, system_text, turns, max_tokens):
    """Shared by Groq and Ollama (OpenAI-compatible streaming)."""
    stream = client.chat.completions.create(
        model=model_id,
        messages=_openai_style_messages(system_text, turns),
        max_tokens=max_tokens,
        stream=True,
        stream_options={"include_usage": True},
    )
    in_tok = out_tok = 0
    try:
        for chunk in stream:
            usage = getattr(chunk, "usage", None)
            if usage is None:  # Groq also reports usage under x_groq on the last chunk
                usage = getattr(getattr(chunk, "x_groq", None), "usage", None)
            if usage is not None:
                in_tok  = getattr(usage, "prompt_tokens", 0) or 0
                out_tok = getattr(usage, "completion_tokens", 0) or 0
            # The final usage chunk has no choices; a delta's content can be None.
            if not chunk.choices:
                continue
            text = chunk.choices[0].delta.content
            if text:
                yield text
    finally:
        close = getattr(stream, "close", None)
        if close:
            close()
    return in_tok, out_tok


def _stream_groq(model_id, api_key, system_text, turns, max_tokens):
    import openai
    client = openai.OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
    return (yield from _stream_openai_compat(client, model_id, system_text, turns, max_tokens))


def _stream_ollama(model_id, api_key, system_text, turns, max_tokens, base_url=None):
    import openai
    base_url = base_url or os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL)
    client = openai.OpenAI(api_key="ollama", base_url=f"{base_url}/v1")
    return (yield from _stream_openai_compat(client, model_id, system_text, turns, max_tokens))


def _stream_google(model_id, api_key, system_text, turns, max_tokens):
    client, config, contents = _google_request(api_key, system_text, turns, max_tokens)
    in_tok = out_tok = 0
    for chunk in client.models.generate_content_stream(model=model_id, contents=contents, config=config):
        meta = getattr(chunk, "usage_metadata", None)
        if meta is not None:  # the last chunk carries the totals
            in_tok  = meta.prompt_token_count or 0
            out_tok = meta.candidates_token_count or 0
        text = chunk.text  # None for chunks without text parts
        if text:
            yield text
    return in_tok, out_tok


_STREAMERS = {
    "groq":   _stream_groq,
    "ollama": _stream_ollama,
    "google": _stream_google,
}


def make_chat_stream(
    *,
    provider:   str,
    model_id:   str,
    messages:   list,
    api_key:    str,
    system:     Optional[str] = None,
    max_tokens: int = 2048,
    local_only: bool = False,
    ollama_base_url: Optional[str] = None,
):
    """
    Streaming counterpart of make_chat_call: a generator that yields text chunks and
    returns (input_tokens, output_tokens, latency_ms). `local_only` and
    `ollama_base_url` behave as in make_chat_call.

    Providers without a streamer (openai, anthropic, openrouter) still work: their
    whole reply is yielded as one chunk.
    """
    if provider not in _CALLERS:
        raise ValueError(f"Unknown provider: {provider!r}. Expected one of {list(_CALLERS)}")

    url = _enforce_local_only(provider, ollama_base_url) if local_only else None

    t0 = time.perf_counter()
    try:
        streamer = _STREAMERS.get(provider)
        if streamer is None:
            text, in_tok, out_tok = _CALLERS[provider](model_id, None, api_key, system, max_tokens, messages=messages)
            if text:
                yield text
        else:
            system_text, turns = _normalize_messages(None, messages, system)
            extra = {"base_url": url} if local_only else {}
            in_tok, out_tok = yield from streamer(model_id, api_key, system_text, turns, max_tokens, **extra)
    except Exception as e:
        if local_only:
            raise _friendly_ollama_error(e, url, model_id) from e
        raise
    return in_tok, out_tok, (time.perf_counter() - t0) * 1000


def make_call(
    *,
    provider:   str,
    model_id:   str,
    prompt:     str,
    api_key:    str,
    system:     Optional[str] = None,
    max_tokens: int = 2048,
) -> tuple[str, int, int, float]:
    """
    Single-prompt wrapper around make_chat_call (the original API, unchanged).
    Returns (response_text, input_tokens, output_tokens, latency_ms).
    """
    return make_chat_call(
        provider   = provider,
        model_id   = model_id,
        messages   = [{"role": "user", "content": prompt}],
        api_key    = api_key,
        system     = system,
        max_tokens = max_tokens,
    )
