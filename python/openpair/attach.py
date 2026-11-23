"""
openpair.attach — read-only file attachments for `openpair chat`
==================================================================
`validate_attachment` is the one gate every attached file passes: /add uses it, and
so does --resume when it re-reads a file named in a saved session. It only ever
READS a file; nothing here writes, edits or executes anything.

A file is refused (AttachError) unless ALL of these hold:
  * it resolves (symlinks and junctions followed) to a regular file inside the
    current folder tree,
  * its name is not secret-looking and it is not under ~/.ssh, ~/.aws or ~/.openpair,
  * it is at most 64 KB (by bytes; never truncated),
  * it is text: no NUL byte and strict UTF-8 (a BOM is accepted and dropped),
  * its text contains no API-key / private-key pattern.
There is no override for any of these.
"""

from __future__ import annotations

import fnmatch
import hashlib
import math
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

MAX_FILE_BYTES = 64 * 1024           # per file
MAX_PENDING_FILES = 5                # at once
MAX_PENDING_BYTES = 128 * 1024       # at once, all files together
TOKEN_WARN = 4000

# Matched case-insensitively against the file name (both as typed and as resolved).
SECRET_NAME_PATTERNS = (
    ".env*", "*.pem", "*.key", "id_rsa*", "id_ed25519*", "*.pfx", "credentials*",
)
# Folders (under the home directory) whose contents are never attached.
SECRET_HOME_DIRS = (".ssh", ".aws", ".openpair")

SECRET_CONTENT_PATTERNS = (
    ("API key (sk-...)", re.compile(r"sk-[A-Za-z0-9_\-]{20,}")),
    ("API key (gsk_...)", re.compile(r"gsk_[A-Za-z0-9]{20,}")),
    ("API key (AIza...)", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
)


class AttachError(Exception):
    """A file cannot be attached. str(e) is a one-line, user-facing reason."""


@dataclass(frozen=True)
class Attachment:
    path: str       # relative to the folder it was added from, forward slashes
    text: str
    sha256: str     # of the raw file bytes
    chars: int
    nbytes: int

    def ref(self) -> dict:
        """What a saved session stores: a reference, never the text."""
        return {"path": self.path, "sha256": self.sha256, "chars": self.chars}


def estimate_tokens(text: str) -> int:
    """Rough token count: ~4 chars/token for ASCII, ~1.5 for everything else (Thai)."""
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    other = len(text) - ascii_chars
    return int(math.ceil(ascii_chars / 4 + other / 1.5))


def is_within(child: Path, parent: Path) -> bool:
    """True if `child` is `parent` or below it. Case-insensitive on Windows, and
    False for a different drive. Both paths should already be resolved."""
    c = os.path.normcase(str(child))
    p = os.path.normcase(str(parent))
    try:
        return os.path.commonpath([c, p]) == p
    except ValueError:  # different drives, or mixed absolute/relative
        return False


def _secret_name(name: str) -> bool:
    low = name.lower().rstrip(". ")
    return any(fnmatch.fnmatchcase(low, pat) for pat in SECRET_NAME_PATTERNS)


def validate_attachment(
    raw_path: str,
    cwd: Optional[Path] = None,
    home: Optional[Path] = None,
) -> Attachment:
    """Return the Attachment for `raw_path`, or raise AttachError saying why not."""
    raw = (raw_path or "").strip().strip('"').strip("'")
    if not raw:
        raise AttachError("no file given")
    if "\x00" in raw:
        raise AttachError("invalid path")
    if os.name == "nt" and ":" in os.path.splitdrive(raw)[1]:
        raise AttachError("refused: NTFS alternate data streams are not allowed")

    try:
        cwd_real = (cwd if cwd is not None else Path.cwd()).resolve()
        home_dir = home if home is not None else Path.home()
    except (OSError, RuntimeError) as e:
        raise AttachError(f"cannot determine the current folder ({type(e).__name__})")

    typed = Path(raw)
    candidate = typed if typed.is_absolute() else cwd_real / typed
    try:
        target = candidate.resolve(strict=True)  # follows symlinks and junctions
    except FileNotFoundError:
        raise AttachError(f"file not found: {raw}")
    except (OSError, RuntimeError) as e:  # symlink loop, bad name, no access ...
        raise AttachError(f"cannot read {raw} ({type(e).__name__})")

    if not is_within(target, cwd_real):
        raise AttachError(
            f"refused: {raw} is outside the current folder ({cwd_real}). "
            "Only files inside the folder you started in can be attached."
        )

    if _secret_name(typed.name) or _secret_name(target.name):
        raise AttachError(f"refused: {target.name} looks like a secrets file")
    for d in SECRET_HOME_DIRS:
        try:
            secret_dir = (Path(home_dir) / d).resolve()
        except (OSError, RuntimeError):
            continue
        if is_within(target, secret_dir):
            raise AttachError(f"refused: files under ~/{d} cannot be attached")

    try:
        st = target.stat()
    except OSError as e:
        raise AttachError(f"cannot read {raw} ({type(e).__name__})")
    if not stat.S_ISREG(st.st_mode):
        raise AttachError(f"refused: {raw} is not a regular file")
    if st.st_size > MAX_FILE_BYTES:
        raise AttachError(
            f"refused: {raw} is {st.st_size:,} bytes; the limit is {MAX_FILE_BYTES:,} "
            "bytes per file (files are never truncated)"
        )

    try:
        with open(target, "rb") as f:
            data = f.read(MAX_FILE_BYTES + 1)
    except OSError as e:
        raise AttachError(f"cannot read {raw} ({type(e).__name__})")
    if len(data) > MAX_FILE_BYTES:
        raise AttachError(f"refused: {raw} is larger than {MAX_FILE_BYTES:,} bytes")
    if b"\x00" in data:
        raise AttachError(f"refused: {raw} is not a text file (contains NUL bytes)")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise AttachError(f"refused: {raw} is not valid UTF-8 text")

    for label, pattern in SECRET_CONTENT_PATTERNS:
        if pattern.search(text):
            raise AttachError(f"refused: {raw} contains what looks like a secret ({label})")

    rel = os.path.relpath(str(target), str(cwd_real)).replace("\\", "/")
    return Attachment(
        path=rel,
        text=text,
        sha256=hashlib.sha256(data).hexdigest(),
        chars=len(text),
        nbytes=len(data),
    )


def check_pending_caps(pending: "list[Attachment]", new: Attachment) -> None:
    """Raise AttachError if adding `new` (replacing a same-path entry) would exceed
    5 files or 128 KB in total."""
    others = [a for a in pending if a.path != new.path]
    files = len(others) + 1
    total = sum(a.nbytes for a in others) + new.nbytes
    if files > MAX_PENDING_FILES or total > MAX_PENDING_BYTES:
        raise AttachError(
            f"refused: at most {MAX_PENDING_FILES} files and {MAX_PENDING_BYTES // 1024} KB "
            f"in total can be attached at once (this would make {files} files, "
            f"{total / 1024:.1f} KB). Send them or use /clear first."
        )


def render_attachments(attachments: "list[Attachment]") -> str:
    """The text block put in front of the user's message (in memory only; it is never
    saved). The fence is longer than any run of `~` inside a file."""
    parts = []
    for a in attachments:
        longest = max((len(m) for m in re.findall(r"~+", a.text)), default=0)
        fence = "~" * max(4, longest + 1)
        parts.append(f"[attached file: {a.path}]\n{fence}\n{a.text}\n{fence}")
    return "\n\n".join(parts) + "\n\n"
