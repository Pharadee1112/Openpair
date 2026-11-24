"""
First-run setup (`openpair chat` with no key and no Ollama). Everything is mocked and isolated:
HOME/USERPROFILE and the cwd point into tmp_path, input()/getpass are scripted, the key check
and the provider are fakes. No network, no real Ollama, no real home folder.
"""

from __future__ import annotations

import copy
import os
import re
import stat
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

from openpair import ApiKeys, chat_cli, setup_wizard as sw
from openpair.chat_cli import chat_main
from openpair.cli import main as cli_main
from openpair.config import load_user_env

FAKE_KEY = "gsk_FAKEKEY1234567890abcd"
FAKE_KEY_2 = "AIza_FAKEGOOGLE0987654321wxyz"
KEY_VARS = ("GROQ_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
            "OPENROUTER_API_KEY", "OLLAMA_BASE_URL", "OLLAMA_MODEL")
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # setenv-then-delenv so monkeypatch restores the original state even though the wizard
    # (by design) writes os.environ directly.
    for var in KEY_VARS:
        monkeypatch.setenv(var, "x")
        monkeypatch.delenv(var)


@pytest.fixture
def env(tmp_path, monkeypatch):
    proj, home = tmp_path / "proj", tmp_path / "home"
    proj.mkdir()
    home.mkdir()
    monkeypatch.chdir(proj)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return proj, home


class Feed:
    """Scripted input_fn / getpass_fn. An exception instance in the list is raised."""

    def __init__(self, items):
        self._it = iter(items)
        self.prompts = []

    def __call__(self, prompt=""):
        self.prompts.append(prompt)
        try:
            item = next(self._it)
        except StopIteration:
            raise EOFError
        if isinstance(item, BaseException):
            raise item
        return item


def run_wizard(home, inputs, keys=(FAKE_KEY,), verdicts=("ok",), ollama=lambda: False):
    """Run the wizard with scripted answers. Returns (outcome, validate calls)."""
    calls = []
    verdict_it = iter(verdicts)

    def validate(provider, key):
        calls.append((provider, key))
        return next(verdict_it, "ok")

    outcome = sw.run_first_run_setup(
        input_fn=Feed(inputs), getpass_fn=Feed(list(keys)), validate_fn=validate,
        ollama_check=ollama, home=home)
    return outcome, calls


def user_env(home: Path) -> Path:
    return home / ".openpair" / ".env"


def assert_no_secret(capsys, *secrets):
    cap = capsys.readouterr()
    for s in secrets:
        assert s not in cap.out and s not in cap.err
    return cap


# ── A. detection ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("environ, ollama, stdin_tty, stdout_tty, expected", [
    ({},                                True,  True,  True,  False),   # Ollama up
    ({},                                False, True,  True,  True),    # nothing: wizard
    ({"GROQ_API_KEY": "k"},             False, True,  True,  False),   # key only
    ({"GOOGLE_API_KEY": "k"},           False, True,  True,  False),
    ({"GROQ_API_KEY": "k"},             True,  True,  True,  False),   # both
    ({"GROQ_API_KEY": "   "},           False, True,  True,  True),    # blank = missing
    ({"GROQ_API_KEY": ""},              False, True,  True,  True),
    ({"OPENAI_API_KEY": "k",
      "ANTHROPIC_API_KEY": "k",
      "OPENROUTER_API_KEY": "k"},       False, True,  True,  True),     # not routable: don't count
    ({},                                False, False, True,  False),   # piped stdin
    ({},                                False, True,  False, False),   # piped stdout
    ({},                                False, False, False, False),
])
def test_detection_matrix(environ, ollama, stdin_tty, stdout_tty, expected):
    assert sw.setup_needed(stdin_tty=stdin_tty, stdout_tty=stdout_tty,
                           ollama_check=lambda: ollama, environ=environ) is expected


def test_ollama_is_not_probed_when_it_cannot_change_the_answer():
    probes = []

    def check():
        probes.append(1)
        return False
    assert not sw.setup_needed(stdin_tty=True, stdout_tty=True, ollama_check=check,
                               environ={"GROQ_API_KEY": "k"})
    assert not sw.setup_needed(stdin_tty=False, stdout_tty=True, ollama_check=check, environ={})
    assert probes == []


def test_default_environ_is_os_environ_and_sees_a_loaded_user_env(env, monkeypatch):
    _, home = env
    assert sw.has_cloud_key() is False
    user_env(home).parent.mkdir()
    user_env(home).write_text(f"GROQ_API_KEY={FAKE_KEY}\n", encoding="utf-8")
    load_user_env()
    assert sw.has_cloud_key() is True


# ── B. the guided flow ───────────────────────────────────────────────────────

def test_cloud_groq_saved(env, capsys):
    _, home = env
    outcome, calls = run_wizard(home, ["1", "1", ""])        # cloud, groq, save (Enter = Y)
    assert outcome == sw.READY
    assert calls == [("groq", FAKE_KEY)]
    assert user_env(home).read_text(encoding="utf-8") == f"GROQ_API_KEY={FAKE_KEY}\n"
    assert os.environ["GROQ_API_KEY"] == FAKE_KEY
    cap = capsys.readouterr()
    assert FAKE_KEY not in cap.out + cap.err
    assert "ending abcd" in cap.err and "console.groq.com/keys" in cap.err and "groq" in cap.err


def test_cloud_google_saved(env, capsys):
    _, home = env
    outcome, calls = run_wizard(home, ["", "2", "y"], keys=(FAKE_KEY_2,))
    assert outcome == sw.READY and calls == [("google", FAKE_KEY_2)]
    assert user_env(home).read_text(encoding="utf-8") == f"GOOGLE_API_KEY={FAKE_KEY_2}\n"
    cap = capsys.readouterr()
    assert FAKE_KEY_2 not in cap.out + cap.err
    assert "aistudio.google.com/apikey" in cap.err


def test_provider_is_named_before_the_check(env, capsys):
    _, home = env
    run_wizard(home, ["1", "2", "n"], keys=(FAKE_KEY_2,))
    assert "Checking the key with google" in capsys.readouterr().err


def test_use_for_this_chat_only_writes_nothing(env, capsys):
    _, home = env
    outcome, _ = run_wizard(home, ["1", "1", "n"])
    assert outcome == sw.READY
    assert os.environ["GROQ_API_KEY"] == FAKE_KEY
    assert not (home / ".openpair").exists()
    assert_no_secret(capsys, FAKE_KEY)


def test_print_option_shows_templates_not_the_key(env, capsys):
    _, home = env
    outcome, _ = run_wizard(home, ["1", "1", "p"])
    assert outcome == sw.READY
    cap = assert_no_secret(capsys, FAKE_KEY)
    assert '$env:GROQ_API_KEY="<your key>"' in cap.err
    assert "export GROQ_API_KEY=<your key>" in cap.err
    assert os.environ["GROQ_API_KEY"] == FAKE_KEY
    assert not (home / ".openpair").exists()


def test_skip_writes_and_sets_nothing(env, capsys):
    _, home = env
    outcome, calls = run_wizard(home, ["3"])
    assert outcome == sw.SKIPPED and calls == []
    assert "GROQ_API_KEY" not in os.environ and not (home / ".openpair").exists()


def test_bad_menu_answer_asks_again(env, capsys):
    _, home = env
    outcome, _ = run_wizard(home, ["x", "3"])
    assert outcome == sw.SKIPPED
    assert "Please type 1, 2 or 3" in capsys.readouterr().err


@pytest.mark.parametrize("bad", ["tooshrt", "has space in it 12345", 'quo"te1234567', "hash#1234567",
                                 "new\nline1234567"])
def test_badly_formed_key_is_refused_and_never_echoed(env, capsys, bad):
    _, home = env
    outcome, calls = run_wizard(home, ["1", "1", ""], keys=(bad, FAKE_KEY))
    assert outcome == sw.READY and calls == [("groq", FAKE_KEY)]
    cap = capsys.readouterr()
    assert bad.strip() not in cap.out + cap.err
    assert "Not accepted" in cap.err
    assert user_env(home).read_text(encoding="utf-8") == f"GROQ_API_KEY={FAKE_KEY}\n"


def test_three_bad_keys_means_skipped_and_nothing_written(env):
    _, home = env
    outcome, calls = run_wizard(home, ["1", "1"], keys=("a", "b", "c"))
    assert outcome == sw.SKIPPED and calls == []
    assert not (home / ".openpair").exists() and "GROQ_API_KEY" not in os.environ


def test_rejected_key_then_decline_reenters(env, capsys):
    _, home = env
    outcome, calls = run_wizard(home, ["1", "1", "n", "", ], keys=(FAKE_KEY, FAKE_KEY_2),
                                verdicts=("rejected", "ok"))
    assert outcome == sw.READY
    assert [k for _, k in calls] == [FAKE_KEY, FAKE_KEY_2]
    assert os.environ["GROQ_API_KEY"] == FAKE_KEY_2
    assert_no_secret(capsys, FAKE_KEY, FAKE_KEY_2)


def test_rejected_key_can_be_saved_anyway(env):
    _, home = env
    outcome, _ = run_wizard(home, ["1", "1", "y", ""], verdicts=("rejected",))
    assert outcome == sw.READY
    assert FAKE_KEY in user_env(home).read_text(encoding="utf-8")


def test_unknown_check_result_never_blocks(env, capsys):
    _, home = env
    outcome, _ = run_wizard(home, ["1", "1", ""], verdicts=("unknown",))
    assert outcome == sw.READY and os.environ["GROQ_API_KEY"] == FAKE_KEY
    assert "continuing without the check" in capsys.readouterr().err


def test_local_flow_rechecks_ollama(env, capsys):
    _, home = env
    answers = iter([False, True])
    outcome, _ = run_wizard(home, ["2", "", ""], ollama=lambda: next(answers))
    assert outcome == sw.READY
    cap = capsys.readouterr()
    assert "ollama pull llama3.1" in cap.err and "ollama.com/download" in cap.err
    assert "still not reachable" in cap.err
    assert not (home / ".openpair").exists()


def test_local_flow_uses_ollama_model_default_and_writes_nothing(env, monkeypatch, capsys):
    _, home = env
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5-coder")
    outcome, _ = run_wizard(home, ["2", "q"])
    assert outcome == sw.SKIPPED
    assert "ollama pull qwen2.5-coder" in capsys.readouterr().err
    assert not (home / ".openpair").exists()


def test_local_flow_can_switch_to_cloud(env):
    _, home = env
    outcome, _ = run_wizard(home, ["2", "c", "1", ""])
    assert outcome == sw.READY and os.environ["GROQ_API_KEY"] == FAKE_KEY


# ── B. the key check (check_key) ─────────────────────────────────────────────

class FakeUrlopen:
    def __init__(self, result):
        self.result, self.requests, self.timeouts = result, [], []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        self.timeouts.append(timeout)
        if isinstance(self.result, BaseException):
            raise self.result
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(code):
    return urllib.error.HTTPError("https://x", code, "msg", {}, None)


@pytest.mark.parametrize("provider, result, expected", [
    ("groq", None, "ok"),
    ("groq", http_error(401), "rejected"),
    ("groq", http_error(403), "rejected"),
    ("groq", http_error(500), "unknown"),
    ("groq", http_error(429), "unknown"),
    ("google", http_error(400), "rejected"),
    ("google", http_error(403), "rejected"),
    ("google", http_error(503), "unknown"),
    ("groq", urllib.error.URLError(f"dns failure {FAKE_KEY}"), "unknown"),
    ("google", TimeoutError(f"timed out {FAKE_KEY}"), "unknown"),
])
def test_check_key_verdicts(provider, result, expected):
    fake = FakeUrlopen(result)
    with patch("urllib.request.urlopen", fake):
        assert sw.check_key(provider, FAKE_KEY) == expected
    req = fake.requests[0]
    assert fake.timeouts == [5.0]
    assert FAKE_KEY not in req.full_url                          # never in the URL
    assert any(FAKE_KEY in v for v in req.headers.values())      # only in a header
    assert req.get_header("User-agent") == "openpair"


def test_validation_failure_text_never_reaches_the_screen(env, capsys):
    _, home = env
    fake = FakeUrlopen(urllib.error.URLError(f"boom {FAKE_KEY}"))
    with patch("urllib.request.urlopen", fake):
        outcome = sw.run_first_run_setup(
            input_fn=Feed(["1", "1", "n"]), getpass_fn=Feed([FAKE_KEY]), ollama_check=lambda: False,
            home=home)
    assert outcome == sw.READY
    assert_no_secret(capsys, FAKE_KEY)


# ── C. saving ────────────────────────────────────────────────────────────────

def test_existing_file_keeps_other_lines_and_gets_a_bak(env):
    _, home = env
    old = "# my keys\nOPENAI_API_KEY=keep-me\nGROQ_API_KEY=old-value\n\nOLLAMA_MODEL=llama3.1\n"
    user_env(home).parent.mkdir()
    user_env(home).write_text(old, encoding="utf-8", newline="")
    sw.save_key("GROQ_API_KEY", FAKE_KEY, home)
    assert user_env(home).read_text(encoding="utf-8") == (
        f"# my keys\nOPENAI_API_KEY=keep-me\nGROQ_API_KEY={FAKE_KEY}\n\nOLLAMA_MODEL=llama3.1\n")
    assert (home / ".openpair" / ".env.bak").read_text(encoding="utf-8") == old


def test_new_name_is_appended_to_an_existing_file(env):
    _, home = env
    user_env(home).parent.mkdir()
    user_env(home).write_text("GROQ_API_KEY=g-old", encoding="utf-8", newline="")  # no final newline
    sw.save_key("GOOGLE_API_KEY", FAKE_KEY_2, home)
    assert user_env(home).read_text(encoding="utf-8") == f"GROQ_API_KEY=g-old\nGOOGLE_API_KEY={FAKE_KEY_2}\n"


def test_export_prefix_and_crlf_are_preserved(env):
    _, home = env
    user_env(home).parent.mkdir()
    user_env(home).write_bytes(b"export GROQ_API_KEY=old\r\nOTHER=1\r\n")
    sw.save_key("GROQ_API_KEY", FAKE_KEY, home)
    assert user_env(home).read_bytes() == f"export GROQ_API_KEY={FAKE_KEY}\r\nOTHER=1\r\n".encode()


def test_similarly_named_variable_is_not_touched(env):
    _, home = env
    user_env(home).parent.mkdir()
    user_env(home).write_text("MY_GROQ_API_KEY=other\n# GROQ_API_KEY=commented\n", encoding="utf-8", newline="")
    sw.save_key("GROQ_API_KEY", FAKE_KEY, home)
    assert user_env(home).read_text(encoding="utf-8") == (
        f"MY_GROQ_API_KEY=other\n# GROQ_API_KEY=commented\nGROQ_API_KEY={FAKE_KEY}\n")


def test_non_utf8_file_is_left_untouched(env):
    _, home = env
    user_env(home).parent.mkdir()
    user_env(home).write_bytes(b"GROQ_API_KEY=\xff\xfe\x80")
    with pytest.raises(sw.SaveError) as e:
        sw.save_key("GROQ_API_KEY", FAKE_KEY, home)
    assert FAKE_KEY not in str(e.value)
    assert user_env(home).read_bytes() == b"GROQ_API_KEY=\xff\xfe\x80"
    assert not (home / ".openpair" / ".env.bak").exists()


def test_write_failure_is_reported_without_the_key_and_the_chat_can_continue(env, capsys):
    _, home = env
    boom = PermissionError(f"denied while writing {FAKE_KEY}")
    with patch("openpair.setup_wizard.atomic_write_text", side_effect=boom):
        outcome, _ = run_wizard(home, ["1", "1", ""])
    assert outcome == sw.READY and os.environ["GROQ_API_KEY"] == FAKE_KEY
    cap = assert_no_secret(capsys, FAKE_KEY)
    assert "Could not save" in cap.err and "PermissionError" in cap.err


@posix_only
def test_file_and_backup_are_0600_and_dir_0700(env):
    _, home = env
    sw.save_key("GROQ_API_KEY", FAKE_KEY, home)
    sw.save_key("GROQ_API_KEY", FAKE_KEY_2, home)
    for p in (user_env(home), home / ".openpair" / ".env.bak"):
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
    assert stat.S_IMODE((home / ".openpair").stat().st_mode) == 0o700


def test_saved_file_is_read_back_by_load_user_env(env, monkeypatch):
    _, home = env
    sw.save_key("GROQ_API_KEY", FAKE_KEY, home)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    load_user_env()
    assert os.environ["GROQ_API_KEY"] == FAKE_KEY
    monkeypatch.delenv("GROQ_API_KEY")


def test_last4_hides_short_keys():
    assert sw.last4(FAKE_KEY) == "ending abcd"
    assert sw.last4("short-key") == ""


# ── Ctrl+C / EOF: nothing written ────────────────────────────────────────────

@pytest.mark.parametrize("exc", [KeyboardInterrupt(), EOFError()])
@pytest.mark.parametrize("step", ["menu", "provider", "key", "save"])
def test_cancel_at_any_prompt_writes_nothing(env, capsys, exc, step):
    _, home = env
    inputs = {"menu": [exc], "provider": ["1", exc], "key": ["1", "1"], "save": ["1", "1", exc]}[step]
    keys = [exc] if step == "key" else [FAKE_KEY]
    outcome = sw.run_first_run_setup(
        input_fn=Feed(inputs), getpass_fn=Feed(keys), validate_fn=lambda p, k: "ok",
        ollama_check=lambda: False, home=home)
    assert outcome == sw.CANCELLED
    assert not (home / ".openpair").exists()
    assert "GROQ_API_KEY" not in os.environ
    cap = assert_no_secret(capsys, FAKE_KEY)
    assert "nothing was saved" in cap.err


def test_cancel_in_the_local_flow_writes_nothing(env):
    _, home = env
    outcome = sw.run_first_run_setup(input_fn=Feed(["2", KeyboardInterrupt()]),
                                     ollama_check=lambda: False, home=home)
    assert outcome == sw.CANCELLED and not (home / ".openpair").exists()


# ── chat_main wiring: TTY vs not, end to end, the skip path ──────────────────

class FakeStream:
    """Stands in for caller.make_chat_stream; records the api_key the provider receives."""

    def __init__(self):
        self.calls = []

    def __call__(self, *, provider, model_id, messages, api_key, system=None,
                 max_tokens=2048, **kw):
        self.calls.append({"provider": provider, "api_key": api_key,
                           "messages": copy.deepcopy(messages)})
        yield "hello "
        yield "there"
        return 10, 20, 5.0


class ChatScript:
    """Scripted builtins.input for the wizard AND the chat prompt, plus scripted getpass."""

    def __init__(self, monkeypatch, items, keys=()):
        self.prompts = []
        self._it, self._keys = iter(items), iter(keys)
        monkeypatch.setattr("builtins.input", self._input)
        monkeypatch.setattr("getpass.getpass", self._getpass)

    def _input(self, prompt=""):
        self.prompts.append(prompt)
        try:
            item = next(self._it)
        except StopIteration:
            raise EOFError
        if isinstance(item, BaseException):
            raise item
        return item

    def _getpass(self, prompt=""):
        self.prompts.append(prompt)
        item = next(self._keys)
        if isinstance(item, BaseException):
            raise item
        return item


def tty(monkeypatch, value=True):
    monkeypatch.setattr(chat_cli, "_stdin_is_tty", lambda: value)
    monkeypatch.setattr(chat_cli, "_stdout_is_tty", lambda: value)


def all_files(root: Path):
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def test_end_to_end_wizard_key_reaches_the_provider(env, monkeypatch, capsys):
    """The wizard sets a key; chat_main builds its OpenPair afterwards, so the (fake) provider
    receives exactly that key. No OpenPair/ApiKeys patching: the real client reads os.environ."""
    _, home = env
    tty(monkeypatch)
    fake = FakeStream()
    ChatScript(monkeypatch, ["1", "1", "", "hi there", "/exit"], keys=[FAKE_KEY])
    with patch.object(ApiKeys, "is_ollama_available", return_value=False), \
         patch.object(sw, "check_key", return_value="ok"), \
         patch("openpair.session.make_chat_stream", fake):
        code = chat_main([])
    assert code == 0
    assert [c["api_key"] for c in fake.calls] == [FAKE_KEY]
    assert fake.calls[0]["provider"] == "groq"
    assert user_env(home).read_text(encoding="utf-8") == f"GROQ_API_KEY={FAKE_KEY}\n"
    cap = capsys.readouterr()
    assert FAKE_KEY not in cap.out + cap.err
    # ...and the key is in no saved chat session either
    sessions = all_files(home / ".openpair" / "sessions")
    assert sessions
    for p in sessions:
        assert FAKE_KEY not in p.read_text(encoding="utf-8")


def test_end_to_end_key_for_this_chat_only(env, monkeypatch):
    _, home = env
    tty(monkeypatch)
    fake = FakeStream()
    ChatScript(monkeypatch, ["1", "2", "n", "hi", "/exit"], keys=[FAKE_KEY_2])
    with patch.object(ApiKeys, "is_ollama_available", return_value=False), \
         patch.object(sw, "check_key", return_value="unknown"), \
         patch("openpair.session.make_chat_stream", fake):
        assert chat_main(["--no-save"]) == 0
    assert [c["api_key"] for c in fake.calls] == [FAKE_KEY_2]
    assert fake.calls[0]["provider"] == "google"
    assert not (home / ".openpair").exists()


def test_cancel_in_chat_main_exits_130_and_creates_nothing(env, monkeypatch):
    _, home = env
    tty(monkeypatch)
    ChatScript(monkeypatch, [KeyboardInterrupt()])
    with patch.object(ApiKeys, "is_ollama_available", return_value=False):
        assert chat_main([]) == 130
    assert not (home / ".openpair").exists()


@pytest.mark.parametrize("stdin_tty, stdout_tty, expect_wizard", [
    (True, True, True), (False, True, False), (True, False, False), (False, False, False)])
def test_wizard_runs_only_on_a_full_terminal(env, monkeypatch, capsys, stdin_tty, stdout_tty,
                                             expect_wizard):
    monkeypatch.setattr(chat_cli, "_stdin_is_tty", lambda: stdin_tty)
    monkeypatch.setattr(chat_cli, "_stdout_is_tty", lambda: stdout_tty)
    asked = []
    monkeypatch.setattr(sw, "run_first_run_setup", lambda **kw: asked.append(1) or sw.SKIPPED)
    ChatScript(monkeypatch, ["/exit"])
    with patch.object(ApiKeys, "is_ollama_available", return_value=False):
        assert chat_main([]) == 0
    assert bool(asked) is expect_wizard


def test_wizard_not_offered_for_resume_list_or_with_a_key_or_with_ollama(env, monkeypatch):
    tty(monkeypatch)
    asked = []
    monkeypatch.setattr(sw, "run_first_run_setup", lambda **kw: asked.append(1) or sw.SKIPPED)
    ChatScript(monkeypatch, ["/exit", "/exit"])
    with patch.object(ApiKeys, "is_ollama_available", return_value=False):
        assert chat_main(["--resume", "list"]) == 0
    monkeypatch.setenv("GROQ_API_KEY", FAKE_KEY)
    with patch.object(ApiKeys, "is_ollama_available", return_value=False), \
         patch("openpair.session.make_chat_stream", FakeStream()):
        assert chat_main([]) == 0
    monkeypatch.delenv("GROQ_API_KEY")
    with patch.object(ApiKeys, "is_ollama_available", return_value=True):
        assert chat_main([]) == 0
    assert asked == []


def test_one_shot_cli_never_prompts(env, monkeypatch, capsys):
    tty(monkeypatch)
    monkeypatch.setattr(sw, "run_first_run_setup",
                        lambda **kw: pytest.fail("one-shot CLI must not run the wizard"))
    with patch.object(ApiKeys, "is_ollama_available", return_value=False):
        assert cli_main(["Hello!"]) == 1
    assert "No API key" in capsys.readouterr().err


def test_skip_then_first_send_shows_a_friendly_fix_without_a_traceback(env, monkeypatch, capsys):
    _, home = env
    tty(monkeypatch)
    fake = FakeStream()
    ChatScript(monkeypatch, ["3", "hello?", "/exit"])
    with patch.object(ApiKeys, "is_ollama_available", return_value=False), \
         patch("openpair.session.make_chat_stream", fake):
        assert chat_main(["--no-save"]) == 0
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "Error: No API key found for any provider, and Ollama is not running." in err
    assert "openpair chat" in err and "ollama serve" in err
    assert "GROQ_API_KEY" in err and "~/.openpair/.env" in err
    assert "RuntimeError" not in err and "api_keys=" not in err
    assert fake.calls == []                                   # nothing was sent anywhere
    assert not (home / ".openpair").exists()


def test_after_skip_starting_ollama_lets_the_next_send_work(env, monkeypatch, capsys):
    tty(monkeypatch)
    fake = FakeStream()
    state = {"up": False}
    ChatScript(monkeypatch, ["3", "first", "second", "/exit"])
    with patch.object(ApiKeys, "is_ollama_available", side_effect=lambda *a, **k: state["up"]), \
         patch("openpair.session.make_chat_stream", fake):
        # flip Ollama on once the first (failing) send has been answered
        orig = chat_cli._error_text

        def flip(e):
            state["up"] = True
            return orig(e)
        monkeypatch.setattr(chat_cli, "_error_text", flip)
        assert chat_main(["--no-save"]) == 0
    assert [c["provider"] for c in fake.calls] == ["ollama"]
    assert fake.calls[0]["messages"][-1]["content"] == "second"


def test_no_provider_error_in_the_stream_path_is_friendly_too(monkeypatch, capsys):
    from openpair import ChatSession, OpenPair
    from openpair.chat_cli import run_chat
    session = ChatSession(OpenPair(api_keys=ApiKeys()))
    monkeypatch.setattr(ChatSession, "cloud_confirmation_needed", lambda self, text: None)
    ChatScript(monkeypatch, ["hi", "/exit"])
    with patch.object(ApiKeys, "is_ollama_available", return_value=False):
        assert run_chat(session) == 0
    err = capsys.readouterr().err
    assert err.startswith("Error: No API key found") and "Traceback" not in err


def test_other_errors_keep_the_one_line_format():
    assert chat_cli._error_text(RuntimeError("  boom\n  twice ")) == "Error: boom twice"
    assert chat_cli._error_text(ValueError()) == "Error: ValueError"
