"""
openpair.caller — Real API call layer
=======================================
Makes actual HTTP calls to OpenAI, Anthropic, and Google AI APIs.
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


# ── OpenAI ──────────────────────────────────────────────────────────────────

def call_openai(
    model_id: str,
    prompt: str,
    api_key: str,
    system: Optional[str] = None,
    max_tokens: int = 2048,
) -> tuple[str, int, int]:
    """
    Call OpenAI Chat Completions API.
    Returns (response_text, input_tokens, output_tokens).
    """
    try:
        import openai
    except ImportError:
        raise ImportError("Install openai: pip install openai")

    client = openai.OpenAI(api_key=api_key)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = client.chat.completions.create(
        model=model_id,
        messages=messages,
        max_tokens=max_tokens,
    )

    text          = resp.choices[0].message.content or ""
    input_tokens  = resp.usage.prompt_tokens
    output_tokens = resp.usage.completion_tokens
    return text, input_tokens, output_tokens


# ── Anthropic ────────────────────────────────────────────────────────────────

def call_anthropic(
    model_id: str,
    prompt: str,
    api_key: str,
    system: Optional[str] = None,
    max_tokens: int = 2048,
) -> tuple[str, int, int]:
    """
    Call Anthropic Messages API.
    Returns (response_text, input_tokens, output_tokens).
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError("Install anthropic: pip install anthropic")

    client = anthropic.Anthropic(api_key=api_key)
    kwargs: dict = dict(
        model=model_id,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    if system:
        kwargs["system"] = system

    resp = client.messages.create(**kwargs)

    text          = resp.content[0].text if resp.content else ""
    input_tokens  = resp.usage.input_tokens
    output_tokens = resp.usage.output_tokens
    return text, input_tokens, output_tokens


# ── Google ───────────────────────────────────────────────────────────────────

def call_google(
    model_id: str,
    prompt: str,
    api_key: str,
    system: Optional[str] = None,
    max_tokens: int = 2048,
) -> tuple[str, int, int]:
    """
    Call Google Generative AI (Gemini) API via the new google-genai SDK.
    Returns (response_text, input_tokens, output_tokens).
    """
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        raise ImportError("Install google-genai: pip install google-genai")

    client = genai.Client(api_key=api_key)

    config = genai_types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        system_instruction=system or None,
    )

    resp = client.models.generate_content(
        model=model_id,
        contents=prompt,
        config=config,
    )

    text = resp.text or ""

    # Token counts
    try:
        input_tokens  = resp.usage_metadata.prompt_token_count or 0
        output_tokens = resp.usage_metadata.candidates_token_count or 0
    except AttributeError:
        input_tokens  = len(prompt.split())   # rough estimate
        output_tokens = len(text.split())

    return text, input_tokens, output_tokens


# ── Groq ─────────────────────────────────────────────────────────────────────

def call_groq(
    model_id: str,
    prompt: str,
    api_key: str,
    system: Optional[str] = None,
    max_tokens: int = 2048,
) -> tuple[str, int, int]:
    """
    Call Groq API (OpenAI-compatible endpoint).
    Returns (response_text, input_tokens, output_tokens).
    """
    try:
        import openai
    except ImportError:
        raise ImportError("Install openai: pip install openai")

    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = client.chat.completions.create(
        model=model_id,
        messages=messages,
        max_tokens=max_tokens,
    )

    text          = resp.choices[0].message.content or ""
    input_tokens  = resp.usage.prompt_tokens
    output_tokens = resp.usage.completion_tokens
    return text, input_tokens, output_tokens


# ── Ollama (local) ──────────────────────────────────────────────────────────

def call_ollama(
    model_id: str,
    prompt: str,
    api_key: str,
    system: Optional[str] = None,
    max_tokens: int = 2048,
) -> tuple[str, int, int]:
    """
    Call a local Ollama server (OpenAI-compatible endpoint). No auth required.
    Returns (response_text, input_tokens, output_tokens).
    """
    try:
        import openai
    except ImportError:
        raise ImportError("Install openai: pip install openai")

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    client = openai.OpenAI(api_key="ollama", base_url=f"{base_url}/v1")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = client.chat.completions.create(
        model=model_id,
        messages=messages,
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
    "ollama":    call_ollama,
}


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
    Dispatch to the correct provider and measure latency.
    Returns (response_text, input_tokens, output_tokens, latency_ms).
    """
    caller = _CALLERS.get(provider)
    if caller is None:
        raise ValueError(f"Unknown provider: {provider!r}. Expected one of {list(_CALLERS)}")

    t0 = time.perf_counter()
    text, in_tok, out_tok = caller(model_id, prompt, api_key, system, max_tokens)
    latency_ms = (time.perf_counter() - t0) * 1000

    return text, in_tok, out_tok, latency_ms
