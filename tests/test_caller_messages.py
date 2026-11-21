"""
Multi-turn `messages` support in the provider callers (caller.py).

Every provider SDK is mocked — no network and no API keys. Each test checks the
exact payload the SDK would have received, because providers disagree on the
conversation format:

  * OpenAI / Groq / OpenRouter / Ollama: system prompt is the first message.
  * Anthropic: system prompt is a separate top-level `system` field.
  * Gemini: assistant role is called "model" and the system prompt is
    `system_instruction` in the config.
"""

from __future__ import annotations

import types
from unittest.mock import patch

import pytest

from openpair import caller
from openpair.caller import (
    call_anthropic,
    call_google,
    call_groq,
    call_ollama,
    call_openai,
    call_openrouter,
    make_call,
    make_chat_call,
)

CONVERSATION = [
    {"role": "user", "content": "My name is Mali."},
    {"role": "assistant", "content": "Nice to meet you, Mali!"},
    {"role": "user", "content": "What is my name?"},
]


# ── OpenAI-compatible providers (openai, groq, openrouter, ollama) ───────────

OPENAI_STYLE = [
    ("openai",     call_openai,     {"api_key": "sk-test"}),
    ("groq",       call_groq,       {"api_key": "sk-test", "base_url": "https://api.groq.com/openai/v1"}),
    ("openrouter", call_openrouter, {"api_key": "sk-test", "base_url": "https://openrouter.ai/api/v1"}),
    ("ollama",     call_ollama,     {"api_key": "ollama", "base_url": "http://localhost:11434/v1"}),
]


@pytest.mark.parametrize("name,fn,client_kwargs", OPENAI_STYLE, ids=[p[0] for p in OPENAI_STYLE])
class TestOpenAIStyleMessages:
    @pytest.fixture(autouse=True)
    def _no_ollama_env(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

    def test_multi_turn_history_is_passed_in_order(self, fake_ollama, name, fn, client_kwargs):
        fake_ollama.response_text = "Your name is Mali."
        text, in_tok, out_tok = fn("some-model", None, "sk-test", messages=CONVERSATION)

        assert text == "Your name is Mali."
        assert (in_tok, out_tok) == (8, 16)
        [call] = fake_ollama.calls
        assert call["model"] == "some-model"
        assert call["messages"] == CONVERSATION
        assert fake_ollama.client_kwargs == [client_kwargs]

    def test_system_argument_becomes_first_message(self, fake_ollama, name, fn, client_kwargs):
        fn("some-model", None, "sk-test", system="Be brief.", messages=CONVERSATION)

        [call] = fake_ollama.calls
        assert call["messages"] == [{"role": "system", "content": "Be brief."}] + CONVERSATION

    def test_system_role_message_is_merged_with_system_argument(self, fake_ollama, name, fn, client_kwargs):
        history = [{"role": "system", "content": "Answer in Thai."}] + CONVERSATION
        fn("some-model", None, "sk-test", system="Be brief.", messages=history)

        [call] = fake_ollama.calls
        assert call["messages"] == [
            {"role": "system", "content": "Be brief.\n\nAnswer in Thai."}
        ] + CONVERSATION

    def test_single_prompt_still_works(self, fake_ollama, name, fn, client_kwargs):
        fn("some-model", "Hi", "sk-test", system="Be brief.", max_tokens=64)

        [call] = fake_ollama.calls
        assert call["max_tokens"] == 64
        assert call["messages"] == [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "Hi"},
        ]


# ── Anthropic ────────────────────────────────────────────────────────────────

class _FakeAnthropic:
    def __init__(self, calls: list):
        self.messages = types.SimpleNamespace(create=lambda **kw: self._create(calls, **kw))

    @staticmethod
    def _create(calls, **kwargs):
        calls.append(kwargs)
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(text="claude reply")],
            usage=types.SimpleNamespace(input_tokens=11, output_tokens=22),
        )


@pytest.fixture
def fake_anthropic():
    calls: list[dict] = []
    with patch("anthropic.Anthropic", side_effect=lambda **kw: _FakeAnthropic(calls)):
        yield calls


class TestAnthropicMessages:
    def test_multi_turn_history_is_passed_in_order(self, fake_anthropic):
        text, in_tok, out_tok = call_anthropic("claude-x", None, "sk-ant", messages=CONVERSATION, max_tokens=99)

        assert (text, in_tok, out_tok) == ("claude reply", 11, 22)
        [kwargs] = fake_anthropic
        assert kwargs["model"] == "claude-x"
        assert kwargs["max_tokens"] == 99
        assert kwargs["messages"] == CONVERSATION
        assert "system" not in kwargs

    def test_system_is_top_level_never_inside_messages(self, fake_anthropic):
        history = [{"role": "system", "content": "Answer in Thai."}] + CONVERSATION
        call_anthropic("claude-x", None, "sk-ant", system="Be brief.", messages=history)

        [kwargs] = fake_anthropic
        assert kwargs["system"] == "Be brief.\n\nAnswer in Thai."
        assert kwargs["messages"] == CONVERSATION
        assert all(m["role"] in ("user", "assistant") for m in kwargs["messages"])

    def test_single_prompt_still_works(self, fake_anthropic):
        call_anthropic("claude-x", "Hi", "sk-ant", system="Be terse.")

        [kwargs] = fake_anthropic
        assert kwargs["messages"] == [{"role": "user", "content": "Hi"}]
        assert kwargs["system"] == "Be terse."


# ── Google Gemini ────────────────────────────────────────────────────────────

class _FakeGemini:
    def __init__(self, calls: list):
        def generate_content(*, model, contents, config):
            calls.append({"model": model, "contents": contents, "config": config})
            return types.SimpleNamespace(
                text="gemini reply",
                usage_metadata=types.SimpleNamespace(prompt_token_count=7, candidates_token_count=3),
            )

        self.models = types.SimpleNamespace(generate_content=generate_content)


@pytest.fixture
def fake_gemini():
    calls: list[dict] = []
    with patch("google.genai.Client", side_effect=lambda **kw: _FakeGemini(calls)):
        yield calls


def _roles_and_texts(contents):
    return [(c.role, c.parts[0].text) for c in contents]


class TestGoogleMessages:
    def test_assistant_role_is_renamed_to_model(self, fake_gemini):
        text, in_tok, out_tok = call_google("gemini-x", None, "key", messages=CONVERSATION, max_tokens=50)

        assert (text, in_tok, out_tok) == ("gemini reply", 7, 3)
        [call] = fake_gemini
        assert call["model"] == "gemini-x"
        assert _roles_and_texts(call["contents"]) == [
            ("user", "My name is Mali."),
            ("model", "Nice to meet you, Mali!"),
            ("user", "What is my name?"),
        ]
        assert call["config"].max_output_tokens == 50

    def test_system_goes_to_system_instruction_not_contents(self, fake_gemini):
        history = [{"role": "system", "content": "Answer in Thai."}] + CONVERSATION
        call_google("gemini-x", None, "key", system="Be brief.", messages=history)

        [call] = fake_gemini
        assert call["config"].system_instruction == "Be brief.\n\nAnswer in Thai."
        assert len(call["contents"]) == 3
        assert {c.role for c in call["contents"]} == {"user", "model"}

    def test_no_system_instruction_when_none_given(self, fake_gemini):
        call_google("gemini-x", None, "key", messages=CONVERSATION)

        [call] = fake_gemini
        assert call["config"].system_instruction is None

    def test_single_prompt_still_works(self, fake_gemini):
        call_google("gemini-x", "Hi", "key", system="Be terse.")

        [call] = fake_gemini
        assert _roles_and_texts(call["contents"]) == [("user", "Hi")]
        assert call["config"].system_instruction == "Be terse."


# ── Input validation (shared by every provider) ──────────────────────────────

class TestMessageValidation:
    def test_prompt_and_messages_together_are_rejected(self, fake_ollama):
        with pytest.raises(ValueError, match="not both"):
            call_ollama("m", "Hi", "ollama", messages=CONVERSATION)

    def test_neither_prompt_nor_messages_is_rejected(self, fake_ollama):
        with pytest.raises(ValueError, match="required"):
            call_ollama("m", None, "ollama")

    def test_empty_messages_are_rejected(self, fake_ollama):
        with pytest.raises(ValueError, match="empty"):
            call_ollama("m", None, "ollama", messages=[])

    def test_unknown_role_is_rejected(self, fake_ollama):
        with pytest.raises(ValueError, match="role"):
            call_ollama("m", None, "ollama", messages=[{"role": "model", "content": "x"}])

    def test_non_string_content_is_rejected(self, fake_ollama):
        with pytest.raises(ValueError, match="content"):
            call_ollama("m", None, "ollama", messages=[{"role": "user", "content": None}])

    def test_only_system_messages_are_rejected(self, fake_ollama):
        with pytest.raises(ValueError, match="at least one"):
            call_ollama("m", None, "ollama", messages=[{"role": "system", "content": "x"}])

    def test_invalid_messages_make_no_api_call(self, fake_ollama):
        with pytest.raises(ValueError):
            call_ollama("m", None, "ollama", messages=[])
        assert fake_ollama.calls == []


# ── Dispatcher: make_chat_call and the make_call wrapper ─────────────────────

class TestDispatcher:
    def test_make_chat_call_forwards_the_full_history(self, monkeypatch):
        seen: dict = {}

        def stub(model_id, prompt, api_key, system, max_tokens, messages=None):
            seen.update(model_id=model_id, prompt=prompt, api_key=api_key,
                        system=system, max_tokens=max_tokens, messages=messages)
            return "ok", 1, 2

        monkeypatch.setitem(caller._CALLERS, "groq", stub)
        text, in_tok, out_tok, latency = make_chat_call(
            provider="groq", model_id="m", messages=CONVERSATION,
            api_key="k", system="S", max_tokens=33,
        )

        assert (text, in_tok, out_tok) == ("ok", 1, 2)
        assert latency >= 0
        assert seen == {"model_id": "m", "prompt": None, "api_key": "k",
                        "system": "S", "max_tokens": 33, "messages": CONVERSATION}

    def test_make_call_is_a_thin_wrapper_building_one_user_message(self, monkeypatch):
        seen: dict = {}

        def stub(model_id, prompt, api_key, system, max_tokens, messages=None):
            seen["messages"] = messages
            seen["system"] = system
            return "ok", 5, 6

        monkeypatch.setitem(caller._CALLERS, "google", stub)
        result = make_call(provider="google", model_id="m", prompt="Hello", api_key="k", system="S")

        assert result[:3] == ("ok", 5, 6)
        assert seen["messages"] == [{"role": "user", "content": "Hello"}]
        assert seen["system"] == "S"

    def test_make_call_end_to_end_matches_the_old_payload(self, fake_ollama):
        make_call(provider="openrouter", model_id="m", prompt="สวัสดี",
                  api_key="k", system="ตอบเป็นภาษาไทย", max_tokens=128)

        [call] = fake_ollama.calls
        assert call["messages"] == [
            {"role": "system", "content": "ตอบเป็นภาษาไทย"},
            {"role": "user", "content": "สวัสดี"},
        ]
        assert call["max_tokens"] == 128

    def test_unknown_provider_is_rejected_by_make_chat_call(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            make_chat_call(provider="nope", model_id="m", messages=CONVERSATION, api_key="k")
