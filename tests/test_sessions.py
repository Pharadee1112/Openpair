"""
Saved sessions and `openpair chat --resume`. Everything is mocked and isolated: HOME /
USERPROFILE and the cwd point into tmp_path, input() is scripted, the provider is fake.
"""

from __future__ import annotations

import copy
import json
import os
import re
import stat
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from openpair import ApiKeys, ChatSession, OpenPair
from openpair import _fsutil, chat_cli
from openpair import session_store as store
from openpair.chat_cli import chat_main

CLOUD_KEYS = dict(google="sk-fake-google", groq="gsk-fake-groq", ollama_model="qwen-test")
ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}\.json$")
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY",
                "OPENROUTER_API_KEY", "OLLAMA_BASE_URL", "OLLAMA_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(chat_cli, "_stdin_is_tty", lambda: True)
    with patch.object(ApiKeys, "is_ollama_available", return_value=True):
        yield


@pytest.fixture
def env(tmp_path, monkeypatch):
    proj, home = tmp_path / "proj", tmp_path / "home"
    proj.mkdir()
    home.mkdir()
    monkeypatch.chdir(proj)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return proj, home


class FakeChat:
    def __init__(self, handler=None):
        self.calls = []
        self.handler = handler or (lambda provider, n: f"reply {n}")

    def __call__(self, *, provider, model_id, messages, api_key, system=None,
                 max_tokens=2048, **kw):
        self.calls.append({"provider": provider, "messages": copy.deepcopy(messages),
                           "system": system})
        out = self.handler(provider, len(self.calls))
        if isinstance(out, str):
            out = re.findall(r"\S+\s*", out)
        for item in out:
            if isinstance(item, BaseException):
                raise item
            yield item
        return 10, 20, 5.0


class Script:
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


def chat(monkeypatch, argv, items, fake=None, keys=None):
    """Run `openpair chat <argv>` with scripted input. Returns (exit code, fake, script)."""
    fake = fake or FakeChat()
    script = Script(monkeypatch, list(items) + ["/exit"])
    with patch("openpair.chat_cli.OpenPair",
               lambda: OpenPair(api_keys=ApiKeys(**(keys or CLOUD_KEYS)))), \
         patch("openpair.session.make_chat_stream", fake):
        code = chat_main(argv)
    return code, fake, script


def sdir(home: Path) -> Path:
    return home / ".openpair" / "sessions"


def files(home: Path):
    d = sdir(home)
    return sorted(p for p in d.glob("*.json")) if d.is_dir() else []


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def craft(home: Path, sid: str, messages=None, **over) -> Path:
    data = {"version": 1, "created": "2026-01-01T10:00:00+07:00",
            "updated": "2026-01-01T10:05:00+07:00", "system": None, "provider_pin": None,
            "local_only": False,
            "messages": messages if messages is not None else [
                {"role": "user", "content": f"first of {sid}"},
                {"role": "assistant", "content": "ok"}],
            "attachments": []}
    data.update(over)
    d = sdir(home)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{sid}.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def put(path: Path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    return path


# ── saving ───────────────────────────────────────────────────────────────────


class TestSaving:
    def test_file_written_after_a_completed_turn(self, env, monkeypatch):
        _, home = env
        chat(monkeypatch, [], ["สวัสดี", "two"])
        (f,) = files(home)
        assert ID_RE.match(f.name) and ":" not in f.name
        d = read(f)
        assert d["version"] == 1 and d["local_only"] is False
        assert set(d) == {"version", "created", "updated", "system", "provider_pin",
                          "local_only", "messages", "attachments"}
        assert [m["role"] for m in d["messages"]] == ["user", "assistant", "user", "assistant"]
        assert d["messages"][0]["content"] == "สวัสดี"          # Thai kept as text, not \u escapes
        assert "สวัสดี" in f.read_text(encoding="utf-8")

    def test_nothing_is_written_without_a_completed_turn(self, env, monkeypatch):
        _, home = env
        chat(monkeypatch, [], ["/help", "/local on", "/files"])
        assert files(home) == []

    def test_failed_and_cancelled_turns_write_nothing(self, env, monkeypatch):
        _, home = env
        fake = FakeChat(lambda p, n: [RuntimeError("boom")])
        chat(monkeypatch, [], ["hi"], fake)
        assert files(home) == []
        fake = FakeChat(lambda p, n: ["partial ", KeyboardInterrupt()])
        chat(monkeypatch, [], ["hi"], fake)
        assert files(home) == []

    def test_a_later_failed_turn_leaves_the_last_good_file(self, env, monkeypatch):
        _, home = env
        fake = FakeChat(lambda p, n: "fine" if n == 1 else [RuntimeError("boom")])
        chat(monkeypatch, [], ["one", "two"], fake)
        (f,) = files(home)
        assert [m["content"] for m in read(f)["messages"] if m["role"] == "user"] == ["one"]

    def test_settings_are_saved(self, env, monkeypatch):
        _, home = env
        chat(monkeypatch, ["--system", "Answer in Thai.", "--provider", "groq"], ["/local on", "hi"])
        d = read(files(home)[0])
        assert (d["system"], d["provider_pin"], d["local_only"]) == ("Answer in Thai.", "groq", True)

    def test_clear_starts_a_new_file_and_keeps_the_old_one(self, env, monkeypatch):
        _, home = env
        chat(monkeypatch, [], ["old one", "/clear", "new one"])
        a, b = files(home)
        assert a != b
        contents = {tuple(m["content"] for m in read(p)["messages"] if m["role"] == "user")
                    for p in (a, b)}
        assert contents == {("old one",), ("new one",)}

    def test_session_save_failure_warns_once_and_chat_continues(self, env, monkeypatch, capsys):
        _, home = env
        (home / ".openpair").write_text("i am a file, not a folder")   # mkdir will fail
        fake = FakeChat()
        code, fake, _ = chat(monkeypatch, [], ["one", "two"], fake)
        err = capsys.readouterr().err
        assert code == 0 and len(fake.calls) == 2
        assert err.count("could not save the session") == 1

    def test_no_temp_files_are_left_behind(self, env, monkeypatch):
        _, home = env
        chat(monkeypatch, [], ["a", "b", "c"])
        assert [p.name for p in sdir(home).iterdir() if not ID_RE.match(p.name)] == []

    @posix_only
    def test_posix_permissions(self, env, monkeypatch):
        _, home = env
        chat(monkeypatch, [], ["hi"])
        assert stat.S_IMODE(os.stat(sdir(home)).st_mode) == 0o700
        assert stat.S_IMODE(os.stat(home / ".openpair").st_mode) == 0o700
        assert stat.S_IMODE(os.stat(files(home)[0]).st_mode) == 0o600


class TestSavedAttachments:
    def test_file_text_is_never_saved_only_a_reference(self, env, monkeypatch):
        proj, home = env
        put(proj / "a.md", "# FILE BODY สวัสดี")
        fake = FakeChat()
        chat(monkeypatch, [], ["/local on", "/add a.md", "typed text", "second"], fake)
        assert "FILE BODY" in fake.calls[0]["messages"][0]["content"]   # model got it
        raw = files(home)[0].read_text(encoding="utf-8")
        assert "FILE BODY" not in raw
        d = json.loads(raw)
        assert [m["content"] for m in d["messages"] if m["role"] == "user"] == ["typed text", "second"]
        (ref,) = d["attachments"]
        assert set(ref) == {"path", "sha256", "chars"} and ref["path"] == "a.md"

    def test_saved_messages_alternate(self, env, monkeypatch):
        proj, home = env
        put(proj / "a.md", "x")
        chat(monkeypatch, [], ["/local on", "/add a.md", "one", "two", "three"])
        roles = [m["role"] for m in read(files(home)[0])["messages"]]
        assert roles == ["user", "assistant"] * 3


# ── resume: choosing a session ───────────────────────────────────────────────


class TestResumeSelection:
    def test_latest_is_the_highest_id_and_history_is_restored(self, env, monkeypatch):
        _, home = env
        craft(home, "20260101-100000-aaaa")
        craft(home, "20260301-100000-bbbb",
              messages=[{"role": "user", "content": "my name is Mali"},
                        {"role": "assistant", "content": "Hi Mali"}])
        craft(home, "20260201-100000-cccc")
        code, fake, _ = chat(monkeypatch, ["--resume"], ["what is my name?"])
        sent = fake.calls[0]["messages"]
        assert [m["content"] for m in sent] == ["my name is Mali", "Hi Mali", "what is my name?"]
        # the resumed session is continued in the SAME file
        assert len(files(home)) == 3
        d = read(sdir(home) / "20260301-100000-bbbb.json")
        assert len(d["messages"]) == 4 and d["created"] == "2026-01-01T10:00:00+07:00"

    def test_exact_id_and_unique_prefix(self, env, monkeypatch):
        _, home = env
        craft(home, "20260101-100000-aaaa")
        craft(home, "20260201-100000-bbbb")
        _, fake, _ = chat(monkeypatch, ["--resume", "20260101-100000-aaaa"], ["go"])
        assert fake.calls[0]["messages"][0]["content"] == "first of 20260101-100000-aaaa"
        _, fake, _ = chat(monkeypatch, ["--resume", "202602"], ["go"])
        assert fake.calls[0]["messages"][0]["content"] == "first of 20260201-100000-bbbb"

    def test_ambiguous_prefix_lists_matches_and_exits(self, env, monkeypatch, capsys):
        _, home = env
        craft(home, "20260101-100000-aaaa")
        craft(home, "20260102-100000-bbbb")
        code, fake, _ = chat(monkeypatch, ["--resume", "202601"], ["go"])
        err = capsys.readouterr().err
        assert code == 2 and fake.calls == []
        assert "20260101-100000-aaaa" in err and "20260102-100000-bbbb" in err

    def test_unknown_id_exits_with_an_error(self, env, monkeypatch, capsys):
        _, home = env
        craft(home, "20260101-100000-aaaa")
        code, fake, _ = chat(monkeypatch, ["--resume", "zzz"], ["go"])
        assert code == 2 and fake.calls == [] and "no saved session matches" in capsys.readouterr().err

    def test_resume_with_no_sessions_starts_fresh(self, env, monkeypatch, capsys):
        code, fake, _ = chat(monkeypatch, ["--resume"], ["hello"])
        assert code == 0 and len(fake.calls) == 1
        assert "No saved sessions" in capsys.readouterr().err

    def test_list(self, env, monkeypatch, capsys):
        _, home = env
        craft(home, "20260101-100000-aaaa",
              messages=[{"role": "user", "content": "x" * 80}, {"role": "assistant", "content": "ok"}])
        craft(home, "20260301-100000-bbbb")
        (sdir(home) / "20260201-100000-cccc.json").write_text("{nope", encoding="utf-8")
        (sdir(home) / "notes.txt").write_text("ignored", encoding="utf-8")
        code, fake, _ = chat(monkeypatch, ["--resume", "list"], [])
        out = capsys.readouterr().out
        assert code == 0 and fake.calls == []
        assert out.index("20260301-100000-bbbb") < out.index("20260201") < out.index("20260101")
        assert "first of 20260301-100000-bbbb" in out and "2026-01-01 10:05:00" in out
        assert "(unusable: not valid JSON)" in out
        assert "x" * 47 + "..." in out and "notes.txt" not in out
        row = [l for l in out.splitlines() if "20260101-100000-aaaa" in l][0]
        assert re.search(r"\s1\s+x{47}\.\.\.$", row)               # turns column

    def test_list_when_empty(self, env, monkeypatch, capsys):
        chat(monkeypatch, ["--resume", "list"], [])
        assert "No saved sessions." in capsys.readouterr().out


# ── resume: restoring settings ───────────────────────────────────────────────


class TestResumeSettings:
    def test_local_only_is_restored_and_really_enforced(self, env, monkeypatch):
        _, home = env
        craft(home, "20260101-100000-aaaa", local_only=True)
        _, fake, _ = chat(monkeypatch, ["--resume"], ["hi"])
        assert [c["provider"] for c in fake.calls] == ["ollama"]
        assert read(files(home)[0])["local_only"] is True

    @pytest.mark.parametrize("bad", [None, "false", 0, [], "no"])
    def test_garbled_local_only_fails_closed(self, env, monkeypatch, bad):
        _, home = env
        craft(home, "20260101-100000-aaaa", local_only=bad)
        _, fake, _ = chat(monkeypatch, ["--resume"], ["hi"])
        assert [c["provider"] for c in fake.calls] == ["ollama"]

    def test_missing_local_only_fails_closed(self, env, monkeypatch):
        _, home = env
        p = craft(home, "20260101-100000-aaaa")
        d = read(p)
        del d["local_only"]
        p.write_text(json.dumps(d), encoding="utf-8")
        _, fake, _ = chat(monkeypatch, ["--resume"], ["hi"])
        assert [c["provider"] for c in fake.calls] == ["ollama"]

    def test_system_and_pin_restored_and_overridable(self, env, monkeypatch):
        _, home = env
        craft(home, "20260101-100000-aaaa", system="Answer in Thai.", provider_pin="groq")
        _, fake, _ = chat(monkeypatch, ["--resume"], ["hi"])
        assert fake.calls[0]["system"] == "Answer in Thai." and fake.calls[0]["provider"] == "groq"
        _, fake, _ = chat(monkeypatch, ["--resume", "--system", "Be brief.", "--provider", "google"], ["hi"])
        assert fake.calls[0]["system"] == "Be brief." and fake.calls[0]["provider"] == "google"

    def test_pin_without_a_key_is_dropped_with_a_warning(self, env, monkeypatch, capsys):
        _, home = env
        craft(home, "20260101-100000-aaaa", provider_pin="groq")
        _, fake, _ = chat(monkeypatch, ["--resume"], ["hi"], keys=dict(google="sk-fake-google"))
        assert "pin dropped" in capsys.readouterr().err
        assert fake.calls[0]["provider"] == "google"


# ── resume: bad files ────────────────────────────────────────────────────────

BAD_FILES = {
    "invalid json": b"{not json",
    "empty file": b"",
    "binary": b"\xff\xfe\x00\x01",
    "not an object": b"[1, 2]",
    "unknown version": json.dumps({"version": 2, "messages": []}).encode(),
    "bool version": json.dumps({"version": True, "messages": []}).encode(),
    "no version": json.dumps({"messages": []}).encode(),
    "messages not a list": json.dumps({"version": 1, "messages": "x"}).encode(),
    "does not alternate": json.dumps({"version": 1, "messages": [
        {"role": "user", "content": "a"}, {"role": "user", "content": "b"}]}).encode(),
    "starts with assistant": json.dumps({"version": 1, "messages": [
        {"role": "assistant", "content": "a"}, {"role": "user", "content": "b"}]}).encode(),
    "ends with user": json.dumps({"version": 1, "messages": [
        {"role": "user", "content": "a"}]}).encode(),
    "content not a string": json.dumps({"version": 1, "messages": [
        {"role": "user", "content": 5}, {"role": "assistant", "content": "x"}]}).encode(),
    "bad attachment entry": json.dumps({"version": 1, "messages": [], "attachments": [{"path": 1}]}).encode(),
}


class TestResumeBadFiles:
    @pytest.mark.parametrize("name", sorted(BAD_FILES))
    def test_bad_file_starts_fresh_names_the_file_and_is_never_touched(
            self, env, monkeypatch, capsys, name):
        _, home = env
        bad = sdir(home) / "20260301-100000-bbbb.json"
        sdir(home).mkdir(parents=True)
        bad.write_bytes(BAD_FILES[name])
        before = bad.read_bytes()
        code, fake, _ = chat(monkeypatch, ["--resume"], ["hello"])
        err = capsys.readouterr().err
        assert code == 0 and len(fake.calls) == 1
        assert fake.calls[0]["messages"] == [{"role": "user", "content": "hello"}]   # fresh
        assert "20260301-100000-bbbb.json" in err and "--resume list" in err
        assert bad.read_bytes() == before and bad.exists()
        assert len(files(home)) == 2            # the fresh chat got its own new file

    def test_newest_corrupt_does_not_fall_back_to_an_older_session(self, env, monkeypatch):
        _, home = env
        craft(home, "20260101-100000-aaaa")
        (sdir(home) / "20260301-100000-bbbb.json").write_text("{", encoding="utf-8")
        _, fake, _ = chat(monkeypatch, ["--resume"], ["hello"])
        assert fake.calls[0]["messages"] == [{"role": "user", "content": "hello"}]

    def test_unknown_provider_pin_is_ignored_not_fatal(self, env, monkeypatch):
        _, home = env
        craft(home, "20260101-100000-aaaa", provider_pin="martian")
        _, fake, _ = chat(monkeypatch, ["--resume"], ["hi"])
        assert len(fake.calls[0]["messages"]) == 3


# ── resume: re-reading attached files (CHANGES 2 and 3) ──────────────────────


def session_with_attachment(proj, home, monkeypatch, name="a.md", body="FILE BODY"):
    """Make a real saved session that references `name`; returns its path."""
    put(proj / name, body)
    chat(monkeypatch, [], ["/local on", f"/add {name}", "describe it"])
    (f,) = files(home)
    return f


class TestResumeAttachments:
    def test_valid_file_is_reattached_and_injected_into_the_next_turn_only(self, env, monkeypatch):
        proj, home = env
        session_with_attachment(proj, home, monkeypatch)
        fake = FakeChat()
        _, fake, script = chat(monkeypatch, ["--resume"], ["follow up", "and again"], fake)
        # resumed session is local_only, so no question and it went to Ollama
        assert script.questions() == []
        first, second = (c["messages"] for c in fake.calls)
        assert [m["role"] for m in first] == ["user", "assistant", "user"]   # alternation intact
        assert "FILE BODY" in first[-1]["content"] and first[-1]["content"].endswith("follow up")
        assert "FILE BODY" in second[-3]["content"]                          # kept in memory
        assert "FILE BODY" not in first[0]["content"] and "FILE BODY" not in first[1]["content"]
        saved = files(home)[0].read_text(encoding="utf-8")
        assert "FILE BODY" not in saved
        d = json.loads(saved)
        assert [m["role"] for m in d["messages"]] == ["user", "assistant"] * 3
        assert [m["content"] for m in d["messages"] if m["role"] == "user"][1:] == ["follow up", "and again"]

    def test_reattached_file_in_cloud_mode_asks_before_it_is_sent(self, env, monkeypatch):
        proj, home = env
        f = session_with_attachment(proj, home, monkeypatch)
        d = read(f)
        d["local_only"] = False
        f.write_text(json.dumps(d), encoding="utf-8")
        fake = FakeChat()
        _, fake, script = chat(monkeypatch, ["--resume"], ["follow up", "n"], fake)
        assert len(script.questions()) == 1 and fake.calls == []
        _, fake, script = chat(monkeypatch, ["--resume"], ["follow up", "y"], FakeChat())
        assert len(script.questions()) == 1 and "FILE BODY" in fake.calls[0]["messages"][-1]["content"]
        assert fake.calls[0]["provider"] in ("google", "groq")

    def test_changed_file_is_skipped_with_a_warning(self, env, monkeypatch, capsys):
        proj, home = env
        session_with_attachment(proj, home, monkeypatch)
        put(proj / "a.md", "EDITED BODY")
        _, fake, _ = chat(monkeypatch, ["--resume"], ["follow up"])
        assert "changed since" in capsys.readouterr().err
        assert "EDITED BODY" not in fake.calls[0]["messages"][-1]["content"]
        assert fake.calls[0]["messages"][-1]["content"] == "follow up"

    def test_missing_file_is_skipped(self, env, monkeypatch, capsys):
        proj, home = env
        session_with_attachment(proj, home, monkeypatch)
        (proj / "a.md").unlink()
        _, fake, _ = chat(monkeypatch, ["--resume"], ["follow up"])
        assert "not found" in capsys.readouterr().err
        assert fake.calls[0]["messages"][-1]["content"] == "follow up"

    def test_resume_from_a_different_folder_skips_the_file(self, env, monkeypatch, capsys, tmp_path):
        proj, home = env
        session_with_attachment(proj, home, monkeypatch)
        other = tmp_path / "elsewhere"
        other.mkdir()
        monkeypatch.chdir(other)
        _, fake, _ = chat(monkeypatch, ["--resume"], ["follow up"])
        assert "Skipped attachment a.md" in capsys.readouterr().err
        assert fake.calls[0]["messages"][-1]["content"] == "follow up"

    def test_same_relative_path_with_different_content_elsewhere_is_skipped(
            self, env, monkeypatch, capsys, tmp_path):
        proj, home = env
        session_with_attachment(proj, home, monkeypatch)
        other = tmp_path / "other"
        put(other / "a.md", "A DIFFERENT FILE")
        monkeypatch.chdir(other)
        _, fake, _ = chat(monkeypatch, ["--resume"], ["follow up"])
        assert "changed since" in capsys.readouterr().err
        assert "A DIFFERENT FILE" not in fake.calls[0]["messages"][-1]["content"]

    @pytest.mark.parametrize("ref_path,why", [
        ("../outside.txt", "outside"),
        (".env", "secrets file"),
        ("sub/.ENV.local", "secrets file"),
        ("server.pem", "secrets file"),
        ("nope.txt", "not found"),
    ])
    def test_tampered_references_fail_the_same_checks_as_add(
            self, env, monkeypatch, capsys, ref_path, why):
        proj, home = env
        put(proj.parent / "outside.txt", "x")
        for n in (".env", "sub/.ENV.local", "server.pem"):
            put(proj / n, "harmless")
        craft(home, "20260101-100000-aaaa", local_only=True,
              attachments=[{"path": ref_path, "sha256": "0" * 64, "chars": 1}])
        _, fake, _ = chat(monkeypatch, ["--resume"], ["follow up"])
        assert why in capsys.readouterr().err
        assert fake.calls[0]["messages"][-1]["content"] == "follow up"

    def test_file_that_now_contains_a_key_is_skipped(self, env, monkeypatch, capsys):
        proj, home = env
        session_with_attachment(proj, home, monkeypatch)
        put(proj / "a.md", "FILE BODY\nkey = sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2")
        _, fake, _ = chat(monkeypatch, ["--resume"], ["follow up"])
        assert "secret" in capsys.readouterr().err
        assert "sk-" not in fake.calls[0]["messages"][-1]["content"]

    def test_oversized_file_is_skipped(self, env, monkeypatch, capsys):
        proj, home = env
        session_with_attachment(proj, home, monkeypatch)
        put(proj / "a.md", b"a" * (64 * 1024 + 1))
        chat(monkeypatch, ["--resume"], ["follow up"])
        assert "limit" in capsys.readouterr().err

    def test_binary_file_is_skipped(self, env, monkeypatch, capsys):
        proj, home = env
        session_with_attachment(proj, home, monkeypatch)
        put(proj / "a.md", b"abc\x00def")
        chat(monkeypatch, ["--resume"], ["follow up"])
        assert "not a text file" in capsys.readouterr().err

    def test_skipped_references_are_kept_when_the_session_is_saved_again(self, env, monkeypatch):
        proj, home = env
        f = session_with_attachment(proj, home, monkeypatch)
        before = read(f)["attachments"]
        (proj / "a.md").unlink()
        chat(monkeypatch, ["--resume"], ["follow up"])
        assert read(f)["attachments"] == before        # not lost just because it was skipped

    def test_clear_after_resume_forgets_the_references(self, env, monkeypatch):
        proj, home = env
        f = session_with_attachment(proj, home, monkeypatch)
        chat(monkeypatch, ["--resume"], ["/clear", "fresh"])
        assert read(f)["attachments"]                   # old file untouched
        newest = files(home)[-1]
        assert newest != f and read(newest)["attachments"] == []

    def test_thai_file_round_trips_through_resume(self, env, monkeypatch):
        proj, home = env
        session_with_attachment(proj, home, monkeypatch, name="สรุป.md", body="# สวัสดีครับ")
        _, fake, _ = chat(monkeypatch, ["--resume"], ["ต่อ"])
        assert "# สวัสดีครับ" in fake.calls[0]["messages"][-1]["content"]

    def test_subfolder_reference_uses_forward_slashes_and_resolves(self, env, monkeypatch):
        proj, home = env
        f = session_with_attachment(proj, home, monkeypatch, name="docs/a.md")
        assert read(f)["attachments"][0]["path"] == "docs/a.md"
        _, fake, _ = chat(monkeypatch, ["--resume"], ["follow up"])
        assert "FILE BODY" in fake.calls[0]["messages"][-1]["content"]


# ── validate_data / helpers ──────────────────────────────────────────────────


class TestValidateAndHelpers:
    def test_valid_empty_session(self):
        d = store.validate_data({"version": 1, "messages": []})
        assert d["messages"] == [] and d["local_only"] is True and d["attachments"] == []

    def test_unknown_extra_keys_are_ignored(self):
        assert store.validate_data({"version": 1, "messages": [], "future": 1})["version"] == 1

    def test_new_session_id_format(self):
        sid = store.new_session_id()
        assert ID_RE.match(sid + ".json") and sid != store.new_session_id()

    def test_atomic_write_replaces_and_leaves_no_temp(self, tmp_path):
        p = tmp_path / "x.json"
        _fsutil.atomic_write_text(p, "one")
        _fsutil.atomic_write_text(p, "two ไทย")
        assert p.read_text(encoding="utf-8") == "two ไทย" and [q.name for q in tmp_path.iterdir()] == ["x.json"]

    def test_failed_replace_keeps_the_old_file_and_cleans_up(self, tmp_path, monkeypatch):
        p = tmp_path / "x.json"
        _fsutil.atomic_write_text(p, "old")
        monkeypatch.setattr(_fsutil.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("disk")))
        with pytest.raises(OSError):
            _fsutil.atomic_write_text(p, "new")
        assert p.read_text() == "old" and [q.name for q in tmp_path.iterdir()] == ["x.json"]

    def test_permission_error_on_replace_is_retried(self, tmp_path, monkeypatch):
        p = tmp_path / "x.json"
        real, calls = os.replace, {"n": 0}

        def flaky(src, dst):
            calls["n"] += 1
            if calls["n"] < 3:
                raise PermissionError("locked by an antivirus scan")
            return real(src, dst)

        monkeypatch.setattr(_fsutil.os, "replace", flaky)
        monkeypatch.setattr(_fsutil.time, "sleep", lambda s: None)
        _fsutil.atomic_write_text(p, "ok")
        assert calls["n"] == 3 and p.read_text() == "ok"

    def test_permission_error_forever_is_raised_after_retries(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_fsutil.os, "replace", lambda *a: (_ for _ in ()).throw(PermissionError("x")))
        monkeypatch.setattr(_fsutil.time, "sleep", lambda s: None)
        with pytest.raises(PermissionError):
            _fsutil.atomic_write_text(tmp_path / "x.json", "ok")
        assert list(tmp_path.iterdir()) == []

    def test_ensure_private_dir_creates_parents(self, tmp_path):
        d = _fsutil.ensure_private_dir(tmp_path / "a" / "b")
        assert d.is_dir()

    @posix_only
    def test_ensure_private_dir_tightens_an_existing_dir(self, tmp_path):
        d = tmp_path / "loose"
        d.mkdir(mode=0o755)
        _fsutil.ensure_private_dir(d)
        assert stat.S_IMODE(os.stat(d).st_mode) == 0o700


class TestWindowsHome:
    @pytest.mark.skipif(sys.platform != "win32", reason="Windows")
    def test_sessions_dir_follows_userprofile(self, env):
        _, home = env
        assert store.sessions_dir() == home / ".openpair" / "sessions"
        assert "\\" in str(store.sessions_dir())          # native separators, no colons in names
