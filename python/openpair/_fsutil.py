"""
openpair._fsutil — small filesystem helpers for files that hold user data
===========================================================================
ensure_private_dir: a directory only the owner can use (0700 on POSIX).
atomic_write_text:  write a file so a reader (or a crash) never sees half of it.

Permissions are best effort: on Windows the mode bits are not enforced; the files
rely on the ACL they inherit from the user profile folder (normally owner-only).
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path


def ensure_private_dir(path: Path) -> Path:
    """Create `path` (and parents) with mode 0700 and tighten it if it already exists."""
    path = Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass
    return path


def atomic_write_text(path: Path, text: str, *, mode: int = 0o600, retries: int = 3) -> None:
    """
    Write `text` (UTF-8) to `path` atomically: a temp file in the same directory, flushed to
    disk, then os.replace(). The file is created 0600. On Windows os.replace can fail with
    PermissionError while another program (an antivirus scan, an indexer) has the target
    open; it is retried a few times, then the error is raised and the old file is untouched.
    """
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(text.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        if os.name != "nt":
            os.chmod(tmp, mode)
        for attempt in range(retries):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == retries - 1:
                    raise
                time.sleep(0.05)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
