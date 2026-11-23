"""
/add, /files and the send-time cloud confirmation. Everything is mocked: scripted
input() and a fake make_chat_stream, so there is no network, no API key and no Ollama.
"""

from __future__ import annotations

import copy
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from openpair import ApiKeys, ChatSession, OpenPair
from openpair import chat_cli
from openpair.attach import (
    MAX_FILE_BYTES,
    AttachError,
    check_pending_caps,
    estimate_tokens,
    is_within,
    render_attachments,
    validate_attachment,
)
from openpair.chat_cli import run_chat

WINDOWS = sys.platform == "win32"
windows_only = pytest.mark.skipif(not WINDOWS, reason="Windows path semantics")
posix_only = pytest.mark.skipif(WINDOWS, reason="POSIX only")

# Built by concatenation so this file itself never contains a key-shaped string.
FAKE_SK = "sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2"
FAKE_GSK = "gsk_" + "a1B2c3D4e5F6g7H8i9J0k1L2"
FAKE_AIZA = "AIza" + "SyA1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q"
FAKE_PEM = "-----BEGIN RSA " + "PRIVATE KEY-----"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY",
                "OPENROUTER_API_KEY", "OLLAMA_BASE_URL", "OLLAMA_MODEL"):
        monkeypatch.delenv(var, raising=False)
    # The real "is Ollama up?" probe would hit localhost: pretend it is up everywhere.
    with patch.object(ApiKeys, "is_ollama_available", return_value=True):
        yield


@pytest.fixture
def env(tmp_path, monkeypatch):
    """cwd = tmp/proj, home = tmp/home."""
    proj = tmp_path / "proj"
    home = tmp_path / "home"
    proj.mkdir()
    home.mkdir()
    monkeypatch.chdir(proj)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return proj, home


def put(path: Path, content, mode="w"):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_bytes(content.encode("utf-8"))
    return path


def refused(raw, **kw):
    with pytest.raises(AttachError) as ei:
        validate_attachment(raw, **kw)
    return str(ei.value)


# ── validate_attachment ──────────────────────────────────────────────────────


class TestAccepts:
    def test_plain_file(self, env):
        proj, _ = env
        put(proj / "notes.txt", "hello\nworld")
        a = validate_attachment("notes.txt")
        assert (a.path, a.text, a.chars) == ("notes.txt", "hello\nworld", 11)
        assert len(a.sha256) == 64

    def test_thai_markdown(self, env):
        proj, _ = env
        put(proj / "สรุป.md", "# สวัสดีครับ\nนี่คือไฟล์ทดสอบ")
        a = validate_attachment("สรุป.md")
        assert a.text == "# สวัสดีครับ\nนี่คือไฟล์ทดสอบ"
        assert a.chars == len(a.text) < a.nbytes

    def test_utf8_bom_is_dropped_but_hashed_raw(self, env):
        import hashlib
        proj, _ = env
        raw = b"\xef\xbb\xbfhi there"
        put(proj / "b.txt", raw)
        a = validate_attachment("b.txt")
        assert a.text == "hi there"
        assert a.sha256 == hashlib.sha256(raw).hexdigest()

    def test_subfolder_and_absolute_path(self, env):
        proj, _ = env
        f = put(proj / "sub" / "a.txt", "x")
        assert validate_attachment(str(Path("sub") / "a.txt")).path == "sub/a.txt"
        assert validate_attachment(str(f)).path == "sub/a.txt"

    def test_quotes_are_stripped(self, env):
        proj, _ = env
        put(proj / "a b.txt", "x")
        assert validate_attachment('"a b.txt"').path == "a b.txt"

    def test_size_boundary(self, env):
        proj, _ = env
        put(proj / "ok.txt", b"a" * MAX_FILE_BYTES)
        assert validate_attachment("ok.txt").nbytes == MAX_FILE_BYTES
        put(proj / "big.txt", b"a" * (MAX_FILE_BYTES + 1))
        assert "limit" in refused("big.txt")

    def test_ref_has_no_text(self, env):
        proj, _ = env
        put(proj / "a.txt", "secret-ish body")
        assert set(validate_attachment("a.txt").ref()) == {"path", "sha256", "chars"}


class TestRefuses:
    def test_missing(self, env):
        assert "not found" in refused("nope.txt")

    def test_outside_folder_dotdot_and_absolute(self, env):
        proj, _ = env
        outside = put(proj.parent / "outside.txt", "x")
        assert "outside" in refused("../outside.txt")
        assert "outside" in refused(str(outside))

    def test_directory(self, env):
        proj, _ = env
        (proj / "d").mkdir()
        assert refused("d")

    @pytest.mark.parametrize("name", [
        ".env", ".env.local", ".ENV", ".env.production", "server.pem", "KEY.PEM", "my.key",
        "id_rsa", "id_rsa.pub", "Id_Rsa", "id_ed25519", "cert.pfx", "credentials",
        "credentials.json", "Credentials.txt",
    ])
    def test_secret_names(self, env, name):
        proj, _ = env
        put(proj / name, "harmless text")
        assert "secrets file" in refused(name)

    @pytest.mark.parametrize("d", [".ssh", ".aws", ".openpair"])
    def test_home_secret_dirs(self, env, monkeypatch, d):
        _, home = env
        monkeypatch.chdir(home)  # cwd == home, so these ARE inside the tree
        put(home / d / "notes.txt", "harmless")
        assert f"~/{d}" in refused(f"{d}/notes.txt", home=home)

    @pytest.mark.parametrize("content,label", [
        (f"token = {FAKE_SK}", "sk-"),
        (f"GROQ={FAKE_GSK}", "gsk_"),
        (f"key: {FAKE_AIZA}", "AIza"),
        (f"{FAKE_PEM}\nabc\n", "private key"),
    ])
    def test_secret_content_and_it_is_never_echoed(self, env, content, label):
        proj, _ = env
        put(proj / "notes.txt", "intro\n" + content + "\n")
        msg = refused("notes.txt")
        assert "secret" in msg
        for needle in (FAKE_SK, FAKE_GSK, FAKE_AIZA, "a1B2c3D4"):
            assert needle not in msg

    def test_short_sk_word_is_fine(self, env):
        proj, _ = env
        put(proj / "a.txt", "the sk-learn library and sk-test")
        validate_attachment("a.txt")

    def test_nul_byte(self, env):
        proj, _ = env
        put(proj / "bin.dat", b"abc\x00def")
        assert "not a text file" in refused("bin.dat")

    def test_invalid_utf8(self, env):
        proj, _ = env
        put(proj / "t.txt", "สวัสดี".encode("cp874"))
        assert "UTF-8" in refused("t.txt")

    def test_empty_and_nul_in_path(self, env):
        assert refused("")
        assert refused("a\x00b")

    @posix_only
    def test_posix_symlink_escaping_is_refused(self, env):
        proj, _ = env
        outside = put(proj.parent / "outside.txt", "x")
        (proj / "link.txt").symlink_to(outside)
        assert "outside" in refused("link.txt")

    @posix_only
    def test_posix_symlink_named_innocently_to_secret_name(self, env):
        proj, _ = env
        put(proj / ".env", "A=1")
        (proj / "notes.txt").symlink_to(proj / ".env")
        assert "secrets file" in refused("notes.txt")

    @posix_only
    def test_posix_symlink_loop(self, env):
        proj, _ = env
        (proj / "a").symlink_to(proj / "b")
        (proj / "b").symlink_to(proj / "a")
        assert refused("a")


# ── Windows path semantics (CHANGE 4) ────────────────────────────────────────


class TestWindowsPaths:
    def test_is_within_basics_on_every_platform(self, tmp_path):
        assert is_within(tmp_path / "a" / "b", tmp_path)
        assert is_within(tmp_path, tmp_path)
        assert not is_within(tmp_path.parent, tmp_path)
        assert not is_within(tmp_path.parent / (tmp_path.name + "-evil"), tmp_path)  # prefix trap

    @windows_only
    def test_drive_letters_other_drive_and_case(self):
        assert is_within(Path("C:/work/a.txt"), Path("C:/work"))
        assert is_within(Path("c:/work/a.txt"), Path("C:/WORK"))   # drive + folder case
        assert not is_within(Path("D:/work/a.txt"), Path("C:/work"))  # other drive
        assert not is_within(Path("C:/work"), Path("D:/work"))

    @windows_only
    def test_existing_file_on_a_different_drive_is_outside(self, env):
        winini = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "win.ini"
        if not winini.exists():
            pytest.skip("no win.ini")
        assert "outside" in refused(str(winini))

    @windows_only
    def test_case_insensitive_path_inside_tree(self, env):
        proj, _ = env
        f = put(proj / "Sub" / "Notes.TXT", "x")
        a = validate_attachment(str(f).upper())     # whole path in capitals
        assert a.text == "x" and a.path.lower() == "sub/notes.txt"
        assert validate_attachment("sUb\\nOtEs.txt").text == "x"

    @windows_only
    def test_case_insensitive_secret_names(self, env):
        proj, _ = env
        put(proj / ".env", "A=1")
        assert "secrets file" in refused(".ENV")
        assert "secrets file" in refused(".Env")

    @windows_only
    def test_backslashes_inside_and_dotdot_outside(self, env):
        proj, _ = env
        put(proj / "sub" / "a.txt", "x")
        put(proj.parent / "out.txt", "y")
        a = validate_attachment("sub\\a.txt")
        assert a.path == "sub/a.txt"                  # stored with forward slashes
        assert validate_attachment(str(proj) + "\\sub\\a.txt").path == "sub/a.txt"
        assert "outside" in refused("..\\out.txt")
        assert "outside" in refused("sub\\..\\..\\out.txt")

    @windows_only
    def test_extended_length_and_unc_forms_to_outside_files(self, env):
        proj, _ = env
        out = put(proj.parent / "out.txt", "y")
        assert refused("\\\\?\\" + str(out))                          # fail closed
        unc = "\\\\localhost\\" + str(out).replace(":", "$", 1)       # \\localhost\D$\...
        assert refused(unc)

    @windows_only
    def test_alternate_data_stream_refused(self, env):
        proj, _ = env
        put(proj / "a.txt", "x")
        assert "alternate data" in refused("a.txt:hidden")

    @windows_only
    def test_device_names_refused(self, env):
        assert refused("NUL")
        assert refused("CON")

    @windows_only
    def test_junction_pointing_outside_is_refused(self, env):
        proj, _ = env
        outside = proj.parent / "outside"
        put(outside / "secret.txt", "x")
        _junction(proj / "jct", outside)
        assert "outside" in refused("jct\\secret.txt")
        assert "outside" in refused("jct/secret.txt")

    @windows_only
    def test_junction_pointing_inside_is_allowed(self, env):
        proj, _ = env
        put(proj / "real" / "a.txt", "inside")
        _junction(proj / "jct", proj / "real")
        a = validate_attachment("jct\\a.txt")
        assert a.text == "inside" and a.path == "real/a.txt"   # reported at its real location

    @windows_only
    def test_junction_into_home_secret_dir_is_refused(self, env, monkeypatch):
        proj, home = env
        put(home / ".ssh" / "notes.txt", "x")
        _junction(proj / "jct", home / ".ssh")
        assert refused("jct\\notes.txt")   # outside the tree (and under ~/.ssh)

    @windows_only
    def test_file_symlink_escaping_is_refused(self, env):
        proj, _ = env
        out = put(proj.parent / "out.txt", "x")
        try:
            (proj / "l.txt").symlink_to(out)
        except OSError:
            pytest.skip("symlink needs Developer Mode or admin")
        assert "outside" in refused("l.txt")


def _junction(link: Path, target: Path):
    r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip(f"mklink /J failed: {r.stderr or r.stdout}")


# ── caps, tokens, rendering ──────────────────────────────────────────────────


def _att(env, name, size=10, text=None):
    proj, _ = env
    put(proj / name, text if text is not None else "a" * size)
    return validate_attachment(name)


class TestCaps:
    def test_at_most_five_files(self, env):
        pending = [_att(env, f"f{i}.txt") for i in range(5)]
        with pytest.raises(AttachError, match="5 files"):
            check_pending_caps(pending, _att(env, "f6.txt"))

    def test_replacing_same_path_is_not_a_sixth_file(self, env):
        pending = [_att(env, f"f{i}.txt") for i in range(5)]
        check_pending_caps(pending, _att(env, "f0.txt", size=20))

    def test_total_128_kb(self, env):
        pending = [_att(env, "a.txt", size=60_000), _att(env, "b.txt", size=60_000)]
        with pytest.raises(AttachError, match="128 KB"):
            check_pending_caps(pending, _att(env, "c.txt", size=60_000))
        check_pending_caps(pending, _att(env, "c.txt", size=5_000))

    def test_session_enforces_caps_and_keeps_state_on_refusal(self, env):
        s = ChatSession(OpenPair(api_keys=ApiKeys(groq="gsk-fake")))
        for i in range(5):
            s.add_attachment(_att(env, f"f{i}.txt"))
        with pytest.raises(AttachError):
            s.add_attachment(_att(env, "extra.txt"))
        assert len(s.pending_attachments) == 5


def test_token_estimate_is_higher_for_thai():
    assert estimate_tokens("a" * 400) == 100
    assert estimate_tokens("ก" * 400) > 250


def test_render_uses_a_fence_longer_than_any_in_the_file(env):
    a = _att(env, "f.md", text="x\n~~~~~~\ny")
    block = render_attachments([a])
    fence = block.splitlines()[1]
    assert set(fence) == {"~"} and len(fence) >= 7
    assert block.startswith("[attached file: f.md]")


# ── REPL: /add, /files, /clear ───────────────────────────────────────────────


class FakeChat:
    """Stand-in for make_chat_stream. Accepts local-mode kwargs. Records every call."""

    def __init__(self, handler=None):
        self.calls = []
        self.handler = handler or (lambda provider, n: f"reply {n}")

    def __call__(self, *, provider, model_id, messages, api_key, system=None,
                 max_tokens=2048, **kw):
        self.calls.append({"provider": provider, "messages": copy.deepcopy(messages)})
        out = self.handler(provider, len(self.calls))
        if isinstance(out, str):
            out = re.findall(r"\S+\s*", out)
        for item in out:
            if isinstance(item, BaseException):
                raise item
            yield item
        return 10, 20, 5.0

    def sent_text(self, i=-1):
        return "\n".join(m["content"] for m in self.calls[i]["messages"])


class Script:
    """Feeds input(); records every prompt text so tests can look at the questions."""

    def __init__(self, monkeypatch, items):
        self.prompts = []
        self._it = iter(items)
        monkeypatch.setattr("builtins.input", self._input)

    def _input(self, prompt=""):
        self.prompts.append(prompt)
        try:
            item = next(self._it)
        except StopIteration:
            raise EOFError
        if isinstance(item, BaseException):
            raise item
        return item

    def questions(self):
        return [p for p in self.prompts if "[y/N]" in p]


@pytest.fixture
def tty(monkeypatch):
    monkeypatch.setattr(chat_cli, "_stdin_is_tty", lambda: True)


@pytest.fixture
def session():
    keys = ApiKeys(google="sk-fake-google", groq="gsk-fake-groq", ollama_model="qwen-test")
    return ChatSession(OpenPair(api_keys=keys))


def run(session, fake, monkeypatch, items):
    script = Script(monkeypatch, items + ["/exit"])
    with patch("openpair.session.make_chat_stream", fake):
        assert run_chat(session) == 0
    return script


class TestCommands:
    def test_add_makes_no_model_call_and_reports(self, env, session, monkeypatch, capsys, tty):
        put(env[0] / "notes.md", "สวัสดี")
        fake = FakeChat()
        run(session, fake, monkeypatch, ["/add notes.md"])
        assert fake.calls == []
        assert [a.path for a in session.pending_attachments] == ["notes.md"]
        assert "Attached notes.md" in capsys.readouterr().out

    def test_add_refusal_is_reported_and_nothing_is_attached(self, env, session, monkeypatch, capsys):
        put(env[0] / ".env", "A=1")
        fake = FakeChat()
        run(session, fake, monkeypatch, ["/add .env", "/add", "/add nope.txt"])
        err = capsys.readouterr().err
        assert "secrets file" in err and "Usage: /add" in err and "not found" in err
        assert session.pending_attachments == [] and fake.calls == []

    def test_big_attachment_warns(self, env, session, monkeypatch, capsys):
        put(env[0] / "big.txt", "word " * 5000)  # 25,000 chars -> ~6k tokens
        run(session, FakeChat(), monkeypatch, ["/add big.txt"])
        assert "a lot of context" in capsys.readouterr().err

    def test_files_lists_pending_and_sent(self, env, session, monkeypatch, capsys, tty):
        put(env[0] / "a.txt", "aaa")
        put(env[0] / "b.txt", "bbb")
        session.local_only = True
        run(session, FakeChat(), monkeypatch, ["/files", "/add a.txt", "hi", "/add b.txt", "/files"])
        out = capsys.readouterr().out
        assert "No attached files." in out
        assert "pending  b.txt" in out and "sent     a.txt" in out

    def test_attachment_is_prepended_to_the_next_turn_only(self, env, session, monkeypatch, tty):
        put(env[0] / "a.txt", "FILE BODY")
        fake = FakeChat()
        session.local_only = True
        run(session, fake, monkeypatch, ["/add a.txt", "what is in it?", "and now?"])
        first = fake.calls[0]["messages"]
        assert [m["role"] for m in first] == ["user"]
        assert "FILE BODY" in first[0]["content"] and first[0]["content"].endswith("what is in it?")
        assert session.pending_attachments == []
        assert [m["role"] for m in fake.calls[1]["messages"]] == ["user", "assistant", "user"]

    def test_saved_view_has_no_attachment_text(self, env, session, monkeypatch, tty):
        put(env[0] / "a.txt", "FILE BODY")
        session.local_only = True
        run(session, FakeChat(), monkeypatch, ["/add a.txt", "typed one", "typed two"])
        assert any("FILE BODY" in m["content"] for m in session.messages)  # in memory: yes
        saved = session.typed_messages()
        assert [m["content"] for m in saved if m["role"] == "user"] == ["typed one", "typed two"]
        assert "FILE BODY" not in repr(saved)
        assert session.sent_attachments == [session.sent_attachments[0]]
        assert set(session.sent_attachments[0]) == {"path", "sha256", "chars"}

    def test_clear_drops_everything(self, env, session, monkeypatch, tty):
        put(env[0] / "a.txt", "FILE BODY")
        session.local_only = True
        run(session, FakeChat(), monkeypatch, ["/add a.txt", "hi", "/add a.txt", "/clear"])
        assert session.pending_attachments == [] and session.sent_attachments == []
        assert session.messages == [] and not session.attachment_text_unconfirmed

    def test_failed_send_keeps_the_attachment_pending(self, env, session, monkeypatch, tty):
        put(env[0] / "a.txt", "FILE BODY")
        session.local_only = True
        fake = FakeChat(lambda p, n: [RuntimeError("boom")] if n == 1 else "ok")
        run(session, fake, monkeypatch, ["/add a.txt", "first", "second"])
        assert "FILE BODY" in fake.sent_text(1)     # re-sent on the retry
        assert session.pending_attachments == []


# ── Send-time cloud confirmation (CHANGES 1, 2, 5) ───────────────────────────


class TestCloudConfirmation:
    def test_cloud_send_asks_naming_the_provider(self, env, session, monkeypatch, tty):
        put(env[0] / "a.txt", "FILE BODY")
        fake = FakeChat()
        script = run(session, fake, monkeypatch, ["/add a.txt", "summarise", "n"])
        assert len(script.questions()) == 1
        assert re.search(r"\b(google|groq)\b", script.questions()[0])
        assert fake.calls == []                              # "n": nothing left the machine
        assert [a.path for a in session.pending_attachments] == ["a.txt"]   # still pending

    def test_yes_sends_once_then_no_more_questions_for_that_provider(
            self, env, session, monkeypatch, tty):
        put(env[0] / "a.txt", "FILE BODY")
        fake = FakeChat()
        session.preferred_provider = "groq"
        script = run(session, fake, monkeypatch, ["/add a.txt", "summarise", "y", "and then?"])
        assert len(script.questions()) == 1
        assert [c["provider"] for c in fake.calls] == ["groq", "groq"]
        assert "FILE BODY" in fake.sent_text(0) and "FILE BODY" in fake.sent_text(1)

    @pytest.mark.parametrize("answer", ["", "yes please no", "N", "ok", "yy"])
    def test_anything_but_y_is_no(self, env, session, monkeypatch, tty, answer):
        put(env[0] / "a.txt", "FILE BODY")
        fake = FakeChat()
        run(session, fake, monkeypatch, ["/add a.txt", "hi", answer])
        assert fake.calls == []

    def test_eof_and_ctrl_c_at_the_question_mean_no(self, env, session, monkeypatch, tty):
        put(env[0] / "a.txt", "FILE BODY")
        fake = FakeChat()
        run(session, fake, monkeypatch, ["/add a.txt", "hi", EOFError(), "again", KeyboardInterrupt()])
        assert fake.calls == []

    def test_local_mode_never_asks_and_never_uses_a_cloud_provider(
            self, env, session, monkeypatch, tty):
        put(env[0] / "a.txt", "FILE BODY")
        fake = FakeChat()
        session.local_only = True
        script = run(session, fake, monkeypatch, ["/add a.txt", "hi"])
        assert script.questions() == []
        assert [c["provider"] for c in fake.calls] == ["ollama"]

    def test_no_files_means_no_questions(self, env, session, monkeypatch, tty):
        fake = FakeChat()
        script = run(session, fake, monkeypatch, ["hello", "again"])
        assert script.questions() == [] and len(fake.calls) == 2

    def test_LEAK_SEQUENCE_add_local_send_then_local_off(self, env, session, monkeypatch, tty):
        """/add in local mode, send to Ollama, /local off, then a PLAIN message: the file
        text is still in the history, so it must be asked about before every cloud send."""
        put(env[0] / "a.txt", "FILE BODY")
        fake = FakeChat()
        session.local_only = True
        script = run(session, fake, monkeypatch, [
            "/add a.txt", "summarise it",        # 1: to Ollama, no question
            "/local off",
            "plain follow-up", "n",               # 2: asked -> n: nothing sent
            "plain follow-up", "n",               # 3: asked again -> n
            "plain follow-up", "y",               # 4: asked -> y: sent to ONE cloud provider
            "and another",                        # 5: same provider confirmed: no question
        ])
        assert [c["provider"] for c in fake.calls][0] == "ollama"
        assert len(fake.calls) == 3               # ollama + the two sends after "y"
        assert len(script.questions()) == 3
        cloud = {c["provider"] for c in fake.calls[1:]}
        assert len(cloud) == 1 and cloud <= {"google", "groq"}
        (provider,) = cloud
        assert all(provider in q for q in script.questions())   # each names the provider
        assert "FILE BODY" in fake.sent_text(1)   # it did go, after the "y"

    def test_leak_sequence_unconfirmed_flag_and_clear_resets_it(
            self, env, session, monkeypatch, tty):
        put(env[0] / "a.txt", "FILE BODY")
        fake = FakeChat()
        session.local_only = True
        run(session, fake, monkeypatch, ["/add a.txt", "hi", "/local off", "x", "n"])
        assert session.attachment_text_unconfirmed is True
        # /clear ends the questions: no file text is left to send
        script = run(session, FakeChat(), monkeypatch, ["/clear", "plain again"])
        assert script.questions() == [] and not session.attachment_text_unconfirmed

    def test_a_new_file_needs_a_new_confirmation(self, env, session, monkeypatch, tty):
        put(env[0] / "a.txt", "AAA")
        put(env[0] / "b.txt", "BBB")
        fake = FakeChat()
        session.preferred_provider = "groq"
        script = run(session, fake, monkeypatch,
                     ["/add a.txt", "one", "y", "/add b.txt", "two", "y"])
        assert len(script.questions()) == 2 and len(fake.calls) == 2

    def test_question_names_the_provider_that_actually_gets_the_call(
            self, env, monkeypatch, tty):
        put(env[0] / "a.txt", "FILE BODY")
        only_google = ChatSession(OpenPair(api_keys=ApiKeys(google="sk-fake-google")),
                                  preferred_provider="groq")   # routed to groq, but no groq key
        fake = FakeChat()
        script = run(only_google, fake, monkeypatch, ["/add a.txt", "hi", "y"])
        assert "google" in script.questions()[0]
        assert [c["provider"] for c in fake.calls] == ["google"]

    def test_pinned_call_has_no_fallback_to_another_cloud_provider(
            self, env, session, monkeypatch, tty, capsys):
        """The confirmed provider fails with a retryable error (429): the file must NOT be
        retried on the other cloud provider, and Ollama must not be tried either."""
        put(env[0] / "a.txt", "FILE BODY")
        session.preferred_provider = "groq"
        fake = FakeChat(lambda p, n: [RuntimeError("429 rate limit")])
        run(session, fake, monkeypatch, ["/add a.txt", "hi", "y"])
        assert [c["provider"] for c in fake.calls] == ["groq"]
        assert "429" in capsys.readouterr().err
        assert session.messages == []                       # failed turn: history unchanged
        assert [a.path for a in session.pending_attachments] == ["a.txt"]

    def test_history_with_file_text_also_has_no_fallback(self, env, session, monkeypatch, tty):
        put(env[0] / "a.txt", "FILE BODY")
        session.preferred_provider = "groq"
        fake = FakeChat(lambda p, n: "ok" if n == 1 else [RuntimeError("503 overloaded")])
        run(session, fake, monkeypatch, ["/add a.txt", "one", "y", "two"])
        assert [c["provider"] for c in fake.calls] == ["groq", "groq"]   # never google/ollama

    def test_without_attachments_fallback_still_works(self, env, session, monkeypatch, tty):
        session.preferred_provider = "groq"
        fake = FakeChat(lambda p, n: [RuntimeError("429 rate limit")] if p == "groq" else "ok")
        run(session, fake, monkeypatch, ["hello"])
        assert [c["provider"] for c in fake.calls][:2] == ["groq", "google"]

    def test_remote_ollama_url_counts_as_cloud(self, env, monkeypatch, tty):
        put(env[0] / "a.txt", "FILE BODY")
        s = ChatSession(OpenPair(api_keys=ApiKeys(
            ollama_base_url="http://203.0.113.9:11434", ollama_model="m")))
        fake = FakeChat()
        script = run(s, fake, monkeypatch, ["/add a.txt", "hi", "n"])
        assert script.questions() and "203.0.113.9" in script.questions()[0]
        assert fake.calls == []

    def test_loopback_ollama_in_cloud_mode_needs_no_question(self, env, monkeypatch, tty):
        put(env[0] / "a.txt", "FILE BODY")
        s = ChatSession(OpenPair(api_keys=ApiKeys(ollama_model="m")))   # no cloud keys
        fake = FakeChat()
        script = run(s, fake, monkeypatch, ["/add a.txt", "hi"])
        assert script.questions() == [] and [c["provider"] for c in fake.calls] == ["ollama"]
        assert s.attachment_text_unconfirmed is True   # still never approved for cloud

    # CHANGE 5
    def test_non_tty_stdin_counts_as_no(self, env, session, monkeypatch, capsys):
        put(env[0] / "a.txt", "FILE BODY")
        monkeypatch.setattr(chat_cli, "_stdin_is_tty", lambda: False)
        fake = FakeChat()
        script = run(session, fake, monkeypatch, ["/add a.txt", "hi"])
        assert script.questions() == []                       # never even asked
        assert fake.calls == []
        assert "not a terminal" in capsys.readouterr().err

    def test_stdin_is_tty_is_false_when_stdin_is_broken(self, monkeypatch):
        class Broken:
            def isatty(self):
                raise ValueError("closed")
        monkeypatch.setattr(sys, "stdin", Broken())
        assert chat_cli._stdin_is_tty() is False

    def test_session_refuses_without_confirmation_even_if_the_repl_is_bypassed(
            self, env, session):
        put(env[0] / "a.txt", "FILE BODY")
        from openpair.session import ConfirmationRequired
        session.add_attachment(validate_attachment("a.txt"))
        with patch("openpair.session.make_chat_stream", FakeChat()) as fake_stream:
            with pytest.raises(ConfirmationRequired):
                list(session.stream("hi"))
            with pytest.raises(ConfirmationRequired):
                session.send("hi")
        assert session.messages == []

    def test_send_path_also_commits_and_pins(self, env, session):
        put(env[0] / "a.txt", "FILE BODY")
        session.add_attachment(validate_attachment("a.txt"))
        session.confirm_cloud("groq")
        session.preferred_provider = "groq"
        seen = []

        def fake_call(*, provider, model_id, messages, api_key, system=None, max_tokens=2048, **kw):
            seen.append((provider, copy.deepcopy(messages)))
            return "answer", 1, 1, 1.0

        with patch("openpair.session.make_chat_call", fake_call):
            session.send("hi")
        assert seen[0][0] == "groq" and "FILE BODY" in seen[0][1][0]["content"]
        assert session.typed_messages()[0]["content"] == "hi"
