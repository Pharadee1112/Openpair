"""
tests/conftest.py — shared pytest fixtures for the openpair test suite.
"""

from __future__ import annotations

import types
from unittest.mock import patch

import pytest


class _FakeOllamaClient:
    """
    Stand-in for `openai.OpenAI(base_url=..., api_key="ollama")`. Mimics just
    enough of the SDK surface (`.chat.completions.create(...)`) that
    `caller.call_ollama` runs its real code — message building, response
    parsing — without any real Ollama server on the network.
    """

    def __init__(self, response_text: str, prompt_tokens: int, completion_tokens: int, calls: list):
        self._response_text = response_text
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self._calls = calls
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))

    def _create(self, *, model, messages, max_tokens=None, **kwargs):
        self._calls.append({"model": model, "messages": messages, "max_tokens": max_tokens})
        usage = types.SimpleNamespace(
            prompt_tokens=self._prompt_tokens,
            completion_tokens=self._completion_tokens,
        )
        message = types.SimpleNamespace(content=self._response_text)
        choice = types.SimpleNamespace(message=message)
        return types.SimpleNamespace(choices=[choice], usage=usage)


class FakeOllama:
    """
    Simulates a running local Ollama server well enough to exercise the real
    `call_ollama` function and the client's Ollama fallback path, without
    requiring Ollama to actually be installed or running.

    Mutate `.response_text` / `.prompt_tokens` / `.completion_tokens` before
    the call under test; inspect `.calls` (payloads sent to `.create()`) and
    `.client_kwargs` (how `openai.OpenAI(...)` was constructed) afterwards.
    """

    def __init__(self) -> None:
        self.response_text = "Fake Ollama response"
        self.prompt_tokens = 8
        self.completion_tokens = 16
        self.calls: list[dict] = []
        self.client_kwargs: list[dict] = []

    def _make_client(self, **kwargs):
        self.client_kwargs.append(kwargs)
        return _FakeOllamaClient(
            response_text=self.response_text,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            calls=self.calls,
        )


@pytest.fixture
def fake_ollama():
    """
    Patches `openai.OpenAI` to return a `FakeOllama`-backed client, and
    `ApiKeys.is_ollama_available` to report the server as reachable — proving
    the Ollama fallback path works end-to-end without a real Ollama install.
    """
    from openpair.config import ApiKeys

    fake = FakeOllama()
    with patch("openai.OpenAI", side_effect=lambda **kw: fake._make_client(**kw)), \
         patch.object(ApiKeys, "is_ollama_available", return_value=True):
        yield fake
