"""
openpair.caller — Real API call layer
=======================================
Makes actual HTTP calls to OpenAI, Anthropic, Google AI, Groq, OpenRouter, and Ollama.
Called by OpenPair.call() after routing decides which model to use.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional


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
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        raise ImportError("Install google-genai: pip install google-genai")

    system_text, turns = _normalize_messages(prompt, messages, system)
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
) -> tuple[str, int, int]:
    """
    Call a local Ollama server (OpenAI-compatible endpoint). No auth required.
    Pass a single `prompt` or a multi-turn `messages` list (not both).
    Returns (response_text, input_tokens, output_tokens).
    """
    try:
        import openai
    except ImportError:
        raise ImportError("Install openai: pip install openai")

    system_text, turns = _normalize_messages(prompt, messages, system)
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
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


def make_chat_call(
    *,
    provider:   str,
    model_id:   str,
    messages:   list,
    api_key:    str,
    system:     Optional[str] = None,
    max_tokens: int = 2048,
) -> tuple[str, int, int, float]:
    """
    Dispatch a multi-turn conversation to the correct provider and measure latency.
    `messages` is a list of {"role": "user" | "assistant" | "system", "content": str}.
    Returns (response_text, input_tokens, output_tokens, latency_ms).
    """
    caller = _CALLERS.get(provider)
    if caller is None:
        raise ValueError(f"Unknown provider: {provider!r}. Expected one of {list(_CALLERS)}")

    t0 = time.perf_counter()
    text, in_tok, out_tok = caller(model_id, None, api_key, system, max_tokens, messages=messages)
    latency_ms = (time.perf_counter() - t0) * 1000

    return text, in_tok, out_tok, latency_ms


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
