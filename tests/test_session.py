"""
ChatSession — multi-turn history on top of the OpenPair routing/fallback chain.

All provider calls are mocked (`openpair.session.make_chat_call`), so no network
and no API keys are needed. The real Rust router is used for routing.
"""

from __future__ import annotations

import copy
from unittest.mock import patch

import pytest

from openpair import ApiKeys, ChatSession, OpenPair, caller


@pytest.fixture(autouse=True)
def _no_local_ollama():
    """Never ping a real Ollama server; the Ollama path has its own test below."""
    with patch.object(ApiKeys, "is_ollama_available", return_value=False):
        yield


@pytest.fixture
def client():
    return OpenPair(api_keys=ApiKeys(google="sk-fake-google", groq="gsk-fake-groq"))


class FakeChat:
    """
    Stand-in for make_chat_call. Records a deep copy of every call (so later
    history changes can't rewrite what a call saw) and answers via `handler`.
    """

    def __init__(self, handler=None):
        self.calls: list[dict] = []
        self.handler = handler or (lambda provider, n: f"reply {n}")

    def __call__(self, *, provider, model_id, messages, api_key, system=None, max_tokens=2048):
        self.calls.append({
            "provider": provider,
            "model_id": model_id,
            "messages": copy.deepcopy(messages),
            "system": system,
            "max_tokens": max_tokens,
        })
        return self.handler(provider, len(self.calls)), 10, 20, 5.0


def _roles(messages):
    return [m["role"] for m in messages]


def _alternates(messages):
    return _roles(messages) == ["user", "assistant"] * (len(messages) // 2)


class TestHistory:
    def test_ten_turns_keep_full_context_and_alternate(self, client):
        fake = FakeChat()
        session = ChatSession(client, system="Be brief.", preferred_provider="groq", max_tokens=77)

        with patch("openpair.session.make_chat_call", fake):
            for turn in range(1, 11):
                result = session.send(f"question {turn}")
                assert result.response_text == f"reply {turn}"

        assert len(fake.calls) == 10
        for turn, call in enumerate(fake.calls, start=1):
            # Turn N is sent with 2*(N-1) earlier messages plus the new user message.
            assert len(call["messages"]) == 2 * (turn - 1) + 1
            assert call["messages"][-1] == {"role": "user", "content": f"question {turn}"}
            assert _alternates(call["messages"][:-1])
            assert call["system"] == "Be brief."
            assert call["max_tokens"] == 77

        # The last call saw every earlier question and reply, in order.
        last = fake.calls[-1]["messages"]
        for earlier in range(1, 10):
            assert last[2 * (earlier - 1)] == {"role": "user", "content": f"question {earlier}"}
            assert last[2 * (earlier - 1) + 1] == {"role": "assistant", "content": f"reply {earlier}"}

        assert len(session.messages) == 20
        assert _alternates(session.messages)

    def test_system_prompt_is_not_stored_in_history(self, client):
        session = ChatSession(client, system="Secret instructions.", preferred_provider="groq")
        with patch("openpair.session.make_chat_call", FakeChat()):
            session.send("hi")

        assert all(m["role"] in ("user", "assistant") for m in session.messages)
        assert "Secret instructions." not in [m["content"] for m in session.messages]

    def test_clear_empties_history_but_keeps_settings(self, client):
        session = ChatSession(client, system="S", preferred_provider="groq", max_tokens=5)
        with patch("openpair.session.make_chat_call", FakeChat()):
            session.send("one")
            session.send("two")
            assert len(session.messages) == 4

            session.clear()
            assert session.messages == []
            assert session.last_fallback_from is None
            assert (session.system, session.preferred_provider, session.max_tokens) == ("S", "groq", 5)

            # After clearing, the next call starts a fresh conversation.
            fake = FakeChat()
        with patch("openpair.session.make_chat_call", fake):
            session.send("three")
        assert fake.calls[0]["messages"] == [{"role": "user", "content": "three"}]

    def test_blank_message_is_rejected_without_a_call(self, client):
        fake = FakeChat()
        session = ChatSession(client, preferred_provider="groq")
        with patch("openpair.session.make_chat_call", fake):
            for bad in ("", "   ", None):
                with pytest.raises(ValueError):
                    session.send(bad)  # type: ignore[arg-type]
        assert fake.calls == []
        assert session.messages == []


class TestFailures:
    def test_failed_call_leaves_history_unchanged(self, client):
        session = ChatSession(client, preferred_provider="groq")
        with patch("openpair.session.make_chat_call", FakeChat()):
            session.send("first")
        before = copy.deepcopy(session.messages)

        def boom(provider, n):
            raise ValueError("400 bad request")  # not retryable

        with patch("openpair.session.make_chat_call", FakeChat(boom)):
            with pytest.raises(ValueError, match="bad request"):
                session.send("this one fails")

        assert session.messages == before
        assert _alternates(session.messages)
        assert session.last_fallback_from is None

        # The same text can simply be sent again and the roles still alternate.
        with patch("openpair.session.make_chat_call", FakeChat()):
            session.send("this one fails")
        assert len(session.messages) == 4
        assert _alternates(session.messages)

    def test_all_providers_rate_limited_raises_and_keeps_history(self, client):
        session = ChatSession(client, preferred_provider="groq")

        def limited(provider, n):
            raise Exception("429 rate limit")

        fake = FakeChat(limited)
        with patch("openpair.session.make_chat_call", fake):
            with pytest.raises(Exception, match="429"):
                session.send("hello")

        assert [c["provider"] for c in fake.calls] == ["groq", "google"]
        assert session.messages == []

    def test_no_usable_key_raises_runtime_error_and_keeps_history(self):
        session = ChatSession(OpenPair(api_keys=ApiKeys()), preferred_provider="groq")
        with patch.object(ApiKeys, "for_provider", return_value=None):
            with pytest.raises(RuntimeError, match="No API key"):
                session.send("hello")
        assert session.messages == []


class TestFallback:
    def test_retryable_error_falls_back_and_records_the_failed_provider(self, client):
        def handler(provider, n):
            if provider == "groq":
                raise Exception("429 rate limit")
            return "from google"

        fake = FakeChat(handler)
        session = ChatSession(client, preferred_provider="groq")
        with patch("openpair.session.make_chat_call", fake):
            result = session.send("hello")

        assert result.provider == "google"
        assert result.response_text == "from google"
        assert session.last_fallback_from == "groq"
        assert [c["provider"] for c in fake.calls] == ["groq", "google"]
        # The fallback provider received the same full message list.
        assert fake.calls[0]["messages"] == fake.calls[1]["messages"]
        assert session.messages == [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "from google"},
        ]

    def test_last_fallback_from_resets_when_the_next_turn_needs_no_fallback(self, client):
        state = {"groq_down": True}

        def handler(provider, n):
            if provider == "groq" and state["groq_down"]:
                raise Exception("503 overloaded")
            return f"{provider} ok"

        session = ChatSession(client, preferred_provider="groq")
        with patch("openpair.session.make_chat_call", FakeChat(handler)):
            session.send("one")
            assert session.last_fallback_from == "groq"

            state["groq_down"] = False
            result = session.send("two")

        assert result.provider == "groq"
        assert session.last_fallback_from is None

    def test_ollama_answers_a_multi_turn_chat_when_no_cloud_key_exists(self, monkeypatch, fake_ollama):
        for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY"):
            monkeypatch.delenv(var, raising=False)
        fake_ollama.response_text = "local reply"

        session = ChatSession(OpenPair(api_keys=ApiKeys()), system="Be brief.")
        first = session.send("My name is Mali.")
        second = session.send("What is my name?")

        assert first.provider == second.provider == "ollama"
        # Real call path: second request carries the whole history (system first).
        assert fake_ollama.calls[1]["messages"] == [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "My name is Mali."},
            {"role": "assistant", "content": "local reply"},
            {"role": "user", "content": "What is my name?"},
        ]


class TestCacheAndRouting:
    def test_identical_prompts_are_never_served_from_cache(self, client):
        fake = FakeChat()
        session = ChatSession(client, preferred_provider="groq")
        with patch("openpair.session.make_chat_call", fake):
            first = session.send("Hello!")
            second = session.send("Hello!")

        assert len(fake.calls) == 2
        assert first.from_cache is False and second.from_cache is False
        assert first.response_text != second.response_text
        assert len(client._cache) == 0
        # The second request carried the first exchange as context.
        assert len(fake.calls[1]["messages"]) == 3

    def test_routing_uses_only_the_latest_user_message(self, client):
        session = ChatSession(client)
        with patch("openpair.session.make_chat_call", FakeChat()), \
             patch.object(client._rust, "route", wraps=client._rust.route) as route:
            session.send("Explain the architecture of a distributed database in depth.")
            session.send("why?")

        routed_prompts = [c.args[0] for c in route.call_args_list]
        assert routed_prompts[0].startswith("Explain the architecture")
        assert "why?" in routed_prompts
        assert all("Explain the architecture" not in p for p in routed_prompts[1:])

    def test_openpair_call_still_uses_cache_after_the_refactor(self, client):
        with patch("openpair.client.make_call", return_value=("r", 1, 2, 3.0)) as mock_call:
            client.call("Hello!")
            again = client.call("Hello!")
        assert mock_call.call_count == 1
        assert again.from_cache is True
