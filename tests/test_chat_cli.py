"""
`openpair chat` — the interactive REPL. Everything is mocked: scripted input()
and a fake make_chat_call, so no network and no API keys are needed.
"""

from __future__ import annotations

import copy
from unittest.mock import patch

import pytest

from openpair import ApiKeys, ChatSession, OpenPair
from openpair.chat_cli import run_chat
from openpair.cli import main


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
                "GROQ_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    with patch.object(ApiKeys, "is_ollama_available", return_value=False):
        yield


@pytest.fixture
def session():
    client = OpenPair(api_keys=ApiKeys(google="sk-fake-google", groq="gsk-fake-groq"))
    return ChatSession(client)


def script_input(monkeypatch, items):
    """Feed `items` to input(); an exception instance in the list is raised."""
    it = iter(items)

    def fake_input(prompt=""):
        try:
            item = next(it)
        except StopIteration:
            raise EOFError
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr("builtins.input", fake_input)


class FakeChat:
    def __init__(self, handler=None):
        self.calls = []
        self.handler = handler or (lambda provider, n: f"reply {n}")

    def __call__(self, *, provider, model_id, messages, api_key, system=None, max_tokens=2048):
        self.calls.append({"provider": provider, "messages": copy.deepcopy(messages)})
        return self.handler(provider, len(self.calls)), 10, 20, 5.0


class TestLoop:
    def test_three_turns_keep_context(self, session, monkeypatch, capsys):
        fake = FakeChat()
        script_input(monkeypatch, ["one", "two", "three", "/exit"])
        with patch("openpair.session.make_chat_call", fake):
            assert run_chat(session) == 0

        assert len(fake.calls) == 3
        assert fake.calls[1]["messages"][0] == {"role": "user", "content": "one"}
        assert fake.calls[1]["messages"][1] == {"role": "assistant", "content": "reply 1"}
        assert len(fake.calls[2]["messages"]) == 5
        out = capsys.readouterr().out
        assert "reply 1" in out and "reply 3" in out

    def test_empty_lines_are_ignored(self, session, monkeypatch):
        fake = FakeChat()
        script_input(monkeypatch, ["", "   ", "hi", "/exit"])
        with patch("openpair.session.make_chat_call", fake):
            run_chat(session)
        assert len(fake.calls) == 1

    @pytest.mark.parametrize("ender", [EOFError(), KeyboardInterrupt(), "/exit"])
    def test_clean_exit(self, session, monkeypatch, ender):
        fake = FakeChat()
        script_input(monkeypatch, ["hi", ender])
        with patch("openpair.session.make_chat_call", fake):
            assert run_chat(session) == 0
        assert len(session.messages) == 2

    def test_ctrl_c_during_send_exits_cleanly(self, session, monkeypatch):
        def boom(provider, n):
            raise KeyboardInterrupt
        script_input(monkeypatch, ["hi"])
        with patch("openpair.session.make_chat_call", FakeChat(boom)):
            assert run_chat(session) == 0
        assert session.messages == []


class TestStatusLine:
    def test_no_fallback(self, session, monkeypatch, capsys):
        script_input(monkeypatch, ["hi", "/exit"])
        with patch("openpair.session.make_chat_call", FakeChat()):
            run_chat(session)
        err = capsys.readouterr().err
        status = [l for l in err.splitlines() if l.startswith("model:")][0]
        assert "fallback: none" in status
        assert "(google)" in status or "(groq)" in status
        assert "tier " in status and "10+20 tok" in status and "5ms" in status

    def test_fallback_names_failed_provider(self, session, monkeypatch, capsys):
        def handler(provider, n):
            if n == 1:
                raise RuntimeError("429 rate limit")
            return "from the second provider"
        script_input(monkeypatch, ["hi", "/exit"])
        fake = FakeChat(handler)
        with patch("openpair.session.make_chat_call", fake):
            run_chat(session)
        first = fake.calls[0]["provider"]
        cap = capsys.readouterr()
        assert f"fallback: from {first}" in cap.err
        assert "from the second provider" in cap.out


class TestErrors:
    def test_failure_prints_error_and_continues(self, session, monkeypatch, capsys):
        def handler(provider, n):
            if n == 1:  # first turn fails with a non-retryable error
                raise ValueError("bad request\nwith detail")
            return "ok now"
        script_input(monkeypatch, ["first", "second", "/exit"])
        with patch("openpair.session.make_chat_call", FakeChat(handler)):
            assert run_chat(session) == 0
        cap = capsys.readouterr()
        assert "Error: bad request with detail" in cap.err
        assert "Traceback" not in cap.err
        assert "ok now" in cap.out
        # failed turn left no trace: only the second turn is in history
        assert session.messages == [
            {"role": "user", "content": "second"},
            {"role": "assistant", "content": "ok now"},
        ]

    def test_no_key_is_a_short_error(self, monkeypatch, capsys):
        sess = ChatSession(OpenPair(api_keys=ApiKeys()))
        script_input(monkeypatch, ["hi", "/exit"])
        assert run_chat(sess) == 0
        err = capsys.readouterr().err
        assert err.startswith("Error: No API key")
        assert sess.messages == []


class TestDispatch:
    def test_prompt_goes_to_one_shot(self, monkeypatch, capsys):
        monkeypatch.setenv("GROQ_API_KEY", "gsk-fake")
        with patch("openpair.chat_cli.chat_main") as chat, \
             patch("openpair.client.make_call", return_value=("one-shot", 1, 1, 1.0)):
            code = main(["some prompt"])
        assert code == 0
        chat.assert_not_called()
        assert "one-shot" in capsys.readouterr().out

    def test_chat_goes_to_repl(self):
        with patch("openpair.chat_cli.chat_main", return_value=0) as chat:
            assert main(["chat", "--provider", "groq"]) == 0
        chat.assert_called_once_with(["--provider", "groq"])

    def test_double_dash_chat_is_a_one_shot_prompt(self, monkeypatch, capsys):
        monkeypatch.setenv("GROQ_API_KEY", "gsk-fake")
        with patch("openpair.chat_cli.chat_main") as chat, \
             patch("openpair.client.make_call", return_value=("hello", 1, 1, 1.0)) as call:
            main(["--", "chat"])
        chat.assert_not_called()
        call.assert_called_once()
