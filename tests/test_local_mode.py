"""
Local-only mode and slash commands. Everything is mocked: no network, no API keys.

The local-mode tests patch the lowest layer (caller._CALLERS / caller._STREAMERS), so
they exercise the real fallback code and the real dispatch guards.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from openpair import ApiKeys, ChatSession, OpenPair, caller
from openpair.caller import is_loopback_url, make_chat_call, make_chat_stream
from openpair.chat_cli import run_chat
from openpair.errors import LocalModeError

CLOUD = ("openai", "anthropic", "google", "groq", "openrouter")
MSGS = [{"role": "user", "content": "hi"}]


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY",
                "OPENROUTER_API_KEY", "OLLAMA_BASE_URL", "OLLAMA_MODEL"):
        monkeypatch.delenv(var, raising=False)


def make_session(url="http://localhost:11434", local_only=True, **kw):
    keys = ApiKeys(google="sk-fake-g", groq="gsk-fake", openai="sk-fake-o",
                   anthropic="sk-fake-a", openrouter="sk-fake-r",
                   ollama_base_url=url, ollama_model="qwen-test")
    return ChatSession(OpenPair(api_keys=keys), local_only=local_only, **kw)


class Spies:
    """Replace every provider entry point with a recording stub."""

    def __init__(self, monkeypatch, ollama_stream=None):
        self.cloud_calls: list[str] = []
        self.ollama_urls: list = []
        for name in CLOUD:
            def blocking(*a, _n=name, **k):
                self.cloud_calls.append(_n)
                return "cloud text", 1, 1
            monkeypatch.setitem(caller._CALLERS, name, blocking)

        for name in ("google", "groq"):
            def cloud_stream(*a, _n=name, **k):
                self.cloud_calls.append(_n)
                yield "cloud text"
                return 1, 1
            monkeypatch.setitem(caller._STREAMERS, name, cloud_stream)

        def default_ollama(model_id, api_key, system_text, turns, max_tokens, base_url=None):
            self.ollama_urls.append(base_url)
            yield "local "
            yield "text"
            return 5, 6

        monkeypatch.setitem(caller._STREAMERS, "ollama", ollama_stream or default_ollama)
        monkeypatch.setitem(caller._CALLERS, "ollama", lambda *a, **k: self._ollama_call(k))

    def _ollama_call(self, k):
        self.ollama_urls.append(k.get("base_url"))
        return "local text", 5, 6


@pytest.fixture
def ollama_up():
    with patch.object(ApiKeys, "is_ollama_available", return_value=True) as m:
        yield m


# ── local-only enforcement ──────────────────────────────────────────────────

class TestNoCloudEver:
    def test_stream_uses_only_ollama_despite_cloud_keys(self, monkeypatch, ollama_up):
        spies = Spies(monkeypatch)
        session = make_session()
        assert "".join(session.stream("hello")) == "local text"
        assert spies.cloud_calls == []
        assert session.last_result.provider == "ollama"
        assert session.last_fallback_from is None

    def test_send_uses_only_ollama_despite_cloud_keys(self, monkeypatch, ollama_up):
        spies = Spies(monkeypatch)
        result = make_session().send("hello")
        assert result.provider == "ollama" and spies.cloud_calls == []

    @pytest.mark.parametrize("pin", ["groq", "google", None])
    def test_provider_pin_is_ignored(self, monkeypatch, ollama_up, pin):
        spies = Spies(monkeypatch)
        session = make_session(preferred_provider=pin)
        list(session.stream("hello"))
        assert spies.cloud_calls == []

    def test_ollama_failure_never_falls_back_to_cloud_stream(self, monkeypatch, ollama_up):
        def failing(*a, **k):
            raise RuntimeError("429 rate limit")   # even a "retryable" error
            yield
        spies = Spies(monkeypatch, ollama_stream=failing)
        session = make_session()
        with pytest.raises(RuntimeError):
            list(session.stream("hello"))
        assert spies.cloud_calls == []
        assert session.messages == []

    def test_ollama_failure_never_falls_back_to_cloud_send(self, monkeypatch, ollama_up):
        spies = Spies(monkeypatch)
        monkeypatch.setitem(caller._CALLERS, "ollama", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("503 unavailable")))
        with pytest.raises(RuntimeError):
            make_session().send("hello")
        assert spies.cloud_calls == []

    def test_ollama_down_is_a_friendly_error_not_a_cloud_call(self, monkeypatch):
        spies = Spies(monkeypatch)
        with patch.object(ApiKeys, "is_ollama_available", return_value=False):
            with pytest.raises(LocalModeError, match="Ollama was not reachable at http://localhost:11434"):
                list(make_session().stream("hello"))
        assert spies.cloud_calls == []

    def test_connection_error_mid_call_is_friendly(self, monkeypatch, ollama_up):
        class APIConnectionError(Exception):
            pass

        def boom(*a, **k):
            raise APIConnectionError("Connection error.")
            yield
        Spies(monkeypatch, ollama_stream=boom)
        with pytest.raises(LocalModeError, match="not reachable at http://localhost:11434"):
            list(make_session().stream("hello"))

    def test_missing_model_404_is_friendly(self, monkeypatch, ollama_up):
        class NotFound(Exception):
            status_code = 404

        def boom(*a, **k):
            raise NotFound("Error code: 404 - model 'qwen-test' not found")
            yield
        Spies(monkeypatch, ollama_stream=boom)
        with pytest.raises(LocalModeError) as ei:
            list(make_session().stream("hello"))
        assert str(ei.value) == "model qwen-test not found, run `ollama pull qwen-test` or set OLLAMA_MODEL"


class TestLowestLevelGuard:
    @pytest.mark.parametrize("provider", CLOUD)
    def test_make_chat_call_refuses_cloud(self, monkeypatch, provider):
        spies = Spies(monkeypatch)
        with pytest.raises(LocalModeError, match="refusing"):
            make_chat_call(provider=provider, model_id="m", messages=MSGS, api_key="k", local_only=True)
        assert spies.cloud_calls == []

    @pytest.mark.parametrize("provider", CLOUD)
    def test_make_chat_stream_refuses_cloud(self, monkeypatch, provider):
        spies = Spies(monkeypatch)
        with pytest.raises(LocalModeError, match="refusing"):
            list(make_chat_stream(provider=provider, model_id="m", messages=MSGS, api_key="k", local_only=True))
        assert spies.cloud_calls == []

    def test_guard_off_still_allows_cloud(self, monkeypatch):
        spies = Spies(monkeypatch)
        make_chat_call(provider="groq", model_id="m", messages=MSGS, api_key="k")
        assert spies.cloud_calls == ["groq"]

    def test_non_loopback_url_refused_at_low_level(self, monkeypatch):
        spies = Spies(monkeypatch)
        with pytest.raises(LocalModeError, match="not a loopback"):
            make_chat_call(provider="ollama", model_id="m", messages=MSGS, api_key="k",
                           local_only=True, ollama_base_url="http://example.com:11434")
        with pytest.raises(LocalModeError, match="not a loopback"):
            list(make_chat_stream(provider="ollama", model_id="m", messages=MSGS, api_key="k",
                                  local_only=True, ollama_base_url="http://10.0.0.5:11434"))
        assert spies.ollama_urls == []


class TestLoopbackUrl:
    @pytest.mark.parametrize("url", [
        "http://localhost:11434", "http://127.0.0.1:11434", "http://[::1]:11434",
        "https://localhost", "http://LOCALHOST:1",
    ])
    def test_accepts(self, url):
        assert is_loopback_url(url)

    @pytest.mark.parametrize("url", [
        "http://192.168.1.10:11434", "http://example.com", "http://localhost.evil.com",
        "http://0.0.0.0:11434", "ftp://localhost", "localhost:11434", "", "http://",
        "http://127.0.0.1.evil.com",
    ])
    def test_rejects(self, url):
        assert not is_loopback_url(url)

    def test_session_refuses_non_loopback_url(self, monkeypatch, ollama_up):
        spies = Spies(monkeypatch)
        session = make_session(url="http://192.168.1.5:11434")
        with pytest.raises(LocalModeError, match="not a loopback"):
            list(session.stream("hello"))
        with pytest.raises(LocalModeError, match="not a loopback"):
            session.send("hello")
        assert spies.cloud_calls == [] and spies.ollama_urls == []


class TestSingleUrl:
    def test_check_and_call_use_the_same_url(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9999")  # a different env value
        spies = Spies(monkeypatch)
        checked = []

        def fake_available(self, timeout=1.0):
            checked.append(self.ollama_base_url)
            return True

        with patch.object(ApiKeys, "is_ollama_available", fake_available):
            session = make_session(url="http://localhost:11434")
            list(session.stream("hello"))
        assert checked == ["http://localhost:11434"]
        assert spies.ollama_urls == ["http://localhost:11434"]

    def test_call_ollama_stays_backward_compatible(self, monkeypatch):
        seen = {}

        class FakeOpenAI:
            def __init__(self, **kw):
                seen["base_url"] = kw["base_url"]
                from types import SimpleNamespace as NS
                self.chat = NS(completions=NS(create=lambda **k: NS(
                    choices=[NS(message=NS(content="x"))], usage=None)))

        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:1234")
        with patch("openai.OpenAI", FakeOpenAI):
            caller.call_ollama("m", "hi", "k")
            assert seen["base_url"] == "http://localhost:1234/v1"      # env, as before
            caller.call_ollama("m", "hi", "k", base_url="http://127.0.0.1:1")
            assert seen["base_url"] == "http://127.0.0.1:1/v1"         # explicit wins


class TestLocalOffUnchanged:
    def test_default_is_off_and_no_extra_kwargs(self):
        session = make_session(local_only=False)
        assert session.local_only is False
        assert ChatSession(OpenPair(api_keys=ApiKeys())).local_only is False
        assert session._policy_kwargs() == {}

    def test_cloud_fallback_still_works_when_off(self, monkeypatch):
        spies = Spies(monkeypatch)
        with patch.object(ApiKeys, "is_ollama_available", return_value=False):
            session = make_session(local_only=False)
            list(session.stream("hello"))
        assert spies.cloud_calls and session.last_result.provider in ("google", "groq")


# ── slash commands in the REPL ──────────────────────────────────────────────

def script_input(monkeypatch, items):
    it = iter(items)

    def fake_input(prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise EOFError

    monkeypatch.setattr("builtins.input", fake_input)


class RecordingStream:
    def __init__(self):
        self.calls = []

    def __call__(self, *, provider, model_id, messages, api_key, system=None, max_tokens=2048, **kw):
        self.calls.append({"provider": provider, "messages": [dict(m) for m in messages], **kw})
        yield "ok"
        return 1, 2, 3.0


@pytest.fixture
def cloud_session():
    with patch.object(ApiKeys, "is_ollama_available", return_value=False):
        yield make_session(local_only=False)


def run(session, monkeypatch, lines, stream=None):
    script_input(monkeypatch, lines + ["/exit"])
    stream = stream or RecordingStream()
    with patch("openpair.session.make_chat_stream", stream):
        assert run_chat(session) == 0
    return stream


class TestSlashCommands:
    @pytest.mark.parametrize("cmd", ["/help", "/clear", "/model", "/provider", "/local", "/provider groq",
                                     "/route hello", "/nonsense", "/"])
    def test_commands_are_never_sent_to_the_model(self, cloud_session, monkeypatch, cmd):
        stream = run(cloud_session, monkeypatch, [cmd])
        assert stream.calls == []
        assert cloud_session.messages == []

    def test_double_slash_sends_single_slash_text(self, cloud_session, monkeypatch):
        stream = run(cloud_session, monkeypatch, ["//help me", "//etc/hosts"])
        assert [c["messages"][-1]["content"] for c in stream.calls] == ["/help me", "/etc/hosts"]

    def test_unknown_command_prints_error_and_help(self, cloud_session, monkeypatch, capsys):
        run(cloud_session, monkeypatch, ["/bogus"])
        err = capsys.readouterr().err
        assert "unknown command /bogus" in err and "/route <text>" in err

    def test_help_lists_commands(self, cloud_session, monkeypatch, capsys):
        run(cloud_session, monkeypatch, ["/help"])
        out = capsys.readouterr().out
        for name in ("/help", "/exit", "/clear", "/route", "/provider", "/model", "/local"):
            assert name in out
        assert "Display only" in out   # /model is documented as display-only

    def test_clear_resets_history(self, cloud_session, monkeypatch):
        stream = run(cloud_session, monkeypatch, ["one", "/clear", "two"])
        assert stream.calls[1]["messages"] == [{"role": "user", "content": "two"}]
        assert cloud_session.messages[0]["content"] == "two"

    def test_route_is_a_dry_run(self, cloud_session, monkeypatch, capsys):
        cloud_session.messages = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
        before = list(cloud_session.messages)
        with patch("openpair.session.make_chat_call") as call:
            stream = run(cloud_session, monkeypatch, ["/route Explain quantum computing"])
        out = capsys.readouterr().out
        assert stream.calls == [] and not call.called
        assert cloud_session.messages == before
        for label in ("Model:", "Provider:", "Tier:", "Score:", "Reason:"):
            assert label in out

    def test_route_without_text_is_a_usage_error(self, cloud_session, monkeypatch, capsys):
        run(cloud_session, monkeypatch, ["/route"])
        assert "Usage: /route <text>" in capsys.readouterr().err

    def test_provider_set_show_and_auto(self, cloud_session, monkeypatch, capsys):
        stream = run(cloud_session, monkeypatch, ["/provider", "/provider groq", "hi", "/provider auto", "/provider"])
        out = capsys.readouterr().out
        assert "provider: auto" in out and "provider: groq" in out
        assert stream.calls[0]["provider"] == "groq"
        assert cloud_session.preferred_provider is None

    def test_provider_rejects_unknown(self, cloud_session, monkeypatch, capsys):
        run(cloud_session, monkeypatch, ["/provider mistral"])
        assert "unknown provider" in capsys.readouterr().err
        assert cloud_session.preferred_provider is None

    def test_model_shows_last_reply(self, cloud_session, monkeypatch, capsys):
        run(cloud_session, monkeypatch, ["/model", "hi", "/model"])
        out = capsys.readouterr().out
        assert "No reply yet" in out and "via " in out


class TestLocalCommandAndStatusLine:
    def test_toggle_and_show(self, cloud_session, monkeypatch, capsys):
        run(cloud_session, monkeypatch, ["/local", "/local on", "/local", "/local off", "/local maybe"])
        cap = capsys.readouterr()
        assert cap.out.count("mode: auto") == 2 and cap.out.count("mode: local") == 2
        assert "Usage: /local" in cap.err
        assert cloud_session.local_only is False

    def test_status_line_shows_mode_only_when_local(self, monkeypatch, capsys):
        spies = Spies(monkeypatch)
        with patch.object(ApiKeys, "is_ollama_available", return_value=True):
            session = make_session(local_only=False)
            script_input(monkeypatch, ["/local on", "hi", "/local off", "hi again", "/exit"])
            run_chat(session)
        status = [l for l in capsys.readouterr().err.splitlines() if l.startswith("model:")]
        assert "mode: local" in status[0] and "(ollama)" in status[0]
        assert "mode: local" not in status[1]

    def test_local_error_prints_one_line_and_loop_continues(self, monkeypatch, capsys):
        spies = Spies(monkeypatch)
        with patch.object(ApiKeys, "is_ollama_available", return_value=False):
            session = make_session(local_only=False)
            script_input(monkeypatch, ["/local on", "hi", "/provider", "/exit"])
            assert run_chat(session) == 0
        cap = capsys.readouterr()
        assert "Error: Ollama was not reachable at http://localhost:11434" in cap.err
        assert "Traceback" not in cap.err and spies.cloud_calls == []
        assert session.messages == []

    def test_enabling_with_bad_url_warns_but_stays_on(self, monkeypatch, capsys):
        spies = Spies(monkeypatch)
        session = make_session(url="http://203.0.113.9:11434", local_only=False)
        script_input(monkeypatch, ["/local on", "hi", "/exit"])
        run_chat(session)
        cap = capsys.readouterr()
        assert "not a loopback" in cap.err and session.local_only is True
        assert spies.cloud_calls == [] and spies.ollama_urls == []
