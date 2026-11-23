"""
openpair.session_store — save and resume `openpair chat` sessions
===================================================================
One JSON file per chat in ~/.openpair/sessions/<YYYYmmdd-HHMMSS>-<4hex>.json, written
atomically after every COMPLETED turn (a cancelled or failed turn writes nothing).

    {"version": 1, "created": ..., "updated": ..., "system": str|null,
     "provider_pin": str|null, "local_only": bool,
     "messages": [{"role": "user"|"assistant", "content": str}, ...],
     "attachments": [{"path": str, "sha256": str, "chars": int}, ...]}

`messages` is what the user typed and what the model answered: it never contains the
text of an attached file. `attachments` only references files; on --resume they are
re-read through the same checks as /add (see restore_attachments).

The file holds the whole conversation in plain text. Directory 0700 / files 0600 on
POSIX; on Windows this is best effort (the user-profile ACL applies).
"""

from __future__ import annotations

import json
import re
import secrets
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ._fsutil import atomic_write_text, ensure_private_dir
from .attach import AttachError, validate_attachment

SESSION_VERSION = 1
_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")
_PROVIDERS = ("google", "groq", "ollama")
LIST_LIMIT = 30


class SessionError(Exception):
    """A session file cannot be used. str(e) is a one-line reason."""


class AmbiguousSession(SessionError):
    def __init__(self, spec: str, matches: List[str]) -> None:
        super().__init__(f"{spec!r} matches {len(matches)} sessions")
        self.matches = matches


class NoSuchSession(SessionError):
    pass


def sessions_dir(home: Optional[Path] = None) -> Path:
    return Path(home if home is not None else Path.home()) / ".openpair" / "sessions"


def new_session_id(now: Optional[datetime] = None) -> str:
    return (now or datetime.now()).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# -- validation / loading -----------------------------------------------------


def validate_data(data) -> dict:
    """Return a normalised session dict or raise SessionError (one-line reason)."""
    if not isinstance(data, dict):
        raise SessionError("not a session file")
    version = data.get("version")
    if version != SESSION_VERSION or isinstance(version, bool):
        raise SessionError(f"unsupported session version {version!r}")

    messages = data.get("messages")
    if not isinstance(messages, list):
        raise SessionError("messages is missing or not a list")
    for i, m in enumerate(messages):
        if (not isinstance(m, dict) or not isinstance(m.get("content"), str)
                or m.get("role") != ("user" if i % 2 == 0 else "assistant")):
            raise SessionError("messages do not alternate user/assistant")
    if len(messages) % 2:
        raise SessionError("the last message is a user message without a reply")

    atts = data.get("attachments", [])
    if not isinstance(atts, list):
        raise SessionError("attachments is not a list")
    refs = []
    for a in atts:
        if (not isinstance(a, dict) or not isinstance(a.get("path"), str)
                or not isinstance(a.get("sha256"), str) or not isinstance(a.get("chars"), int)):
            raise SessionError("an attachment entry is malformed")
        refs.append({"path": a["path"], "sha256": a["sha256"], "chars": a["chars"]})

    system = data.get("system")
    if system is not None and not isinstance(system, str):
        raise SessionError("system is not a string")
    pin = data.get("provider_pin")
    if pin is not None and pin not in _PROVIDERS:
        pin = None  # unknown provider name: ignore the pin rather than fail
    local_only = data.get("local_only")
    if not isinstance(local_only, bool):
        local_only = True  # fail closed: missing or garbled means local-only

    return {
        "version": SESSION_VERSION,
        "created": str(data.get("created", "")),
        "updated": str(data.get("updated", "")),
        "system": system,
        "provider_pin": pin,
        "local_only": local_only,
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        "attachments": refs,
    }


def load_session_file(path: Path) -> dict:
    try:
        raw = Path(path).read_bytes()
    except OSError as e:
        raise SessionError(f"cannot read the file ({type(e).__name__})")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise SessionError("not valid JSON")
    return validate_data(data)


# -- listing / finding ----------------------------------------------------------


@dataclass
class SessionInfo:
    id: str
    path: Path
    updated: str = ""
    turns: int = 0
    first_line: str = ""
    error: str = ""


def _session_files(home: Optional[Path]) -> List[Path]:
    d = sessions_dir(home)
    if not d.is_dir():
        return []
    files = [p for p in d.iterdir() if p.suffix == ".json" and _ID_RE.match(p.stem) and p.is_file()]
    return sorted(files, key=lambda p: p.stem, reverse=True)  # newest first


def list_sessions(home: Optional[Path] = None) -> List[SessionInfo]:
    out = []
    for p in _session_files(home):
        try:
            d = load_session_file(p)
        except SessionError as e:
            out.append(SessionInfo(p.stem, p, error=str(e)))
            continue
        first = next((m["content"] for m in d["messages"] if m["role"] == "user"), "")
        out.append(SessionInfo(p.stem, p, d["updated"], len(d["messages"]) // 2,
                               " ".join(first.split())))
    return out


def find_session(spec: str, home: Optional[Path] = None) -> Path:
    """Path of the session named by `spec`: "latest" (the default), an exact id, or a unique
    id prefix. Raises AmbiguousSession (lists matches) or NoSuchSession."""
    files = _session_files(home)
    if spec == "latest":
        if not files:
            raise NoSuchSession("no saved sessions")
        return files[0]
    exact = [p for p in files if p.stem == spec]
    if exact:
        return exact[0]
    matches = [p for p in files if p.stem.startswith(spec)]
    if not matches:
        raise NoSuchSession(f"no saved session matches {spec!r}")
    if len(matches) > 1:
        raise AmbiguousSession(spec, [p.stem for p in matches])
    return matches[0]


def format_listing(infos: List[SessionInfo]) -> str:
    if not infos:
        return "No saved sessions."
    lines = [f"{'ID':<20} {'UPDATED':<20} {'TURNS':>5}  FIRST MESSAGE"]
    for i in infos[:LIST_LIMIT]:
        if i.error:
            lines.append(f"{i.id:<20} {'':<20} {'':>5}  (unusable: {i.error})")
            continue
        first = i.first_line if len(i.first_line) <= 50 else i.first_line[:47] + "..."
        updated = i.updated.replace("T", " ")[:19]
        lines.append(f"{i.id:<20} {updated:<20} {i.turns:>5}  {first}")
    if len(infos) > LIST_LIMIT:
        lines.append(f"... and {len(infos) - LIST_LIMIT} older sessions")
    return "\n".join(lines)


# -- saving ---------------------------------------------------------------------


class SessionRecorder:
    """
    Saves a ChatSession to its file. Call save() after each completed turn. It never
    raises: if the disk write fails it warns once and the chat carries on.
    /clear starts a NEW file (the old one is kept as it was).
    """

    def __init__(self, session, home: Optional[Path] = None,
                 session_id: Optional[str] = None, created: Optional[str] = None) -> None:
        self._home = home
        self.id = session_id or new_session_id()
        self.created = created or _now_iso()
        self._clear_seen = session.clear_count
        self._warned = False

    @property
    def path(self) -> Path:
        return sessions_dir(self._home) / f"{self.id}.json"

    def save(self, session) -> Optional[Path]:
        if session.clear_count != self._clear_seen:
            self._clear_seen = session.clear_count
            self.id = new_session_id()
            self.created = _now_iso()
        refs = {a["path"]: a for a in session.resumed_attachments}
        refs.update({a["path"]: a for a in session.sent_attachments})
        data = {
            "version": SESSION_VERSION,
            "created": self.created,
            "updated": _now_iso(),
            "system": session.system,
            "provider_pin": session.preferred_provider,
            "local_only": session.local_only,
            "messages": session.typed_messages(),
            "attachments": list(refs.values()),
        }
        try:
            ensure_private_dir(sessions_dir(self._home).parent)   # ~/.openpair (mkdir mode only covers the leaf)
            ensure_private_dir(sessions_dir(self._home))
            atomic_write_text(self.path, json.dumps(data, ensure_ascii=False, indent=1))
        except OSError as e:
            if not self._warned:
                self._warned = True
                print(f"Warning: could not save the session ({type(e).__name__}); "
                      "the chat continues but will not be resumable.", file=sys.stderr)
            return None
        return self.path


# -- restoring ------------------------------------------------------------------


def restore_into(session, data: dict, *, keep_system: bool = False, keep_pin: bool = False) -> List[str]:
    """
    Load a validated session dict into `session`. History is plain user/assistant text and
    ends with an assistant message, so the next user turn alternates correctly.
    Returns warnings to show the user. `keep_system` / `keep_pin`: the command line gave
    --system / --provider explicitly, which wins over the saved value.
    """
    warnings: List[str] = []
    session.clear()
    session.messages = list(data["messages"])
    session.local_only = data["local_only"]   # restored as saved; garbled values were already -> True
    if not keep_system:
        session.system = data["system"]
    pin = data["provider_pin"]
    if not keep_pin:
        session.preferred_provider = pin
        if pin in ("google", "groq") and not session._client._keys.for_provider(pin):
            warnings.append(f"Saved provider pin {pin!r} has no API key now; pin dropped.")
            session.preferred_provider = None
    session.resumed_attachments = [dict(a) for a in data["attachments"]]
    return warnings


def restore_attachments(session, refs: List[dict]) -> List[str]:
    """
    Re-read each saved attachment reference through validate_attachment (the SAME checks
    as /add: inside the current folder tree, secret names and patterns, size, text only)
    and buffer it as a pending attachment for the NEXT user turn. A file that fails a
    check, is missing, no longer matches its saved sha256, or would exceed the pending
    caps is skipped with a warning. Returns the warnings and does not raise.

    Pending attachments are only put in front of the next user message when it is sent
    (after the usual cloud confirmation), so history keeps alternating and the saved
    messages never contain the text.
    """
    warnings: List[str] = []
    for ref in refs:
        try:
            att = validate_attachment(ref["path"])
            if att.sha256 != ref["sha256"]:
                raise AttachError("the file changed since it was attached (use /add to attach "
                                  "the current version)")
            session.add_attachment(att)
        except AttachError as e:
            warnings.append(f"Skipped attachment {ref['path']}: {e}")
    return warnings
