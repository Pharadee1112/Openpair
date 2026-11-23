"""
openpair.setup_wizard — first-run setup for `openpair chat`
=============================================================
Runs only when `openpair chat` starts on a terminal with no GOOGLE_API_KEY / GROQ_API_KEY
(environment or a loaded .env) and no reachable Ollama. It helps the user either start Ollama
or paste a cloud key, and (optionally) saves the key to ~/.openpair/.env.

Rules this module keeps:
  * A key value is never printed, logged, echoed or put in an error message. After saving, at
    most the last 4 characters are shown. Exceptions from the network check are reported by
    class name only.
  * Nothing is written until the user answers the final "save?" question; Ctrl+C / Ctrl+D /
    Ctrl+Z at any prompt leaves everything untouched.
  * The key file is plain text (like any .env), created owner-only (0600) where the OS
    supports it; on Windows it relies on the permissions of the user-profile folder.
  * Piped or scripted runs never get here (see setup_needed).
"""

from __future__ import annotations

import getpass
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from ._fsutil import atomic_write_text, ensure_private_dir
from .config import ApiKeys, user_env_path

CLOUD_KEY_VARS = {"google": "GOOGLE_API_KEY", "groq": "GROQ_API_KEY"}
KEY_PAGES = {"google": "https://aistudio.google.com/apikey",
             "groq": "https://console.groq.com/keys"}
OLLAMA_DOWNLOAD = "https://ollama.com/download"
VALIDATE_TIMEOUT = 5.0
MAX_KEY_ATTEMPTS = 3

# Outcomes of run_first_run_setup
READY, SKIPPED, CANCELLED = "ready", "skipped", "cancelled"


class SaveError(Exception):
    """The key file could not be saved. The message never contains the key."""


# ── detection ────────────────────────────────────────────────────────────────

def has_cloud_key(environ=None) -> bool:
    """True if GOOGLE_API_KEY or GROQ_API_KEY is set to something other than blanks."""
    environ = os.environ if environ is None else environ
    return any((environ.get(name) or "").strip() for name in CLOUD_KEY_VARS.values())


def setup_needed(*, stdin_tty: bool, stdout_tty: bool,
                 ollama_check: Optional[Callable[[], bool]] = None, environ=None) -> bool:
    """
    True only on a real terminal, with no cloud key and no reachable Ollama. The Ollama probe
    (1 s timeout, honours OLLAMA_BASE_URL) is the last test, so it is skipped when it cannot
    change the answer.
    """
    if not (stdin_tty and stdout_tty):
        return False
    if has_cloud_key(environ):
        return False
    check = ollama_check or (lambda: ApiKeys().is_ollama_available(timeout=1.0))
    return not check()


# ── key handling ─────────────────────────────────────────────────────────────

def key_problem(key: str) -> Optional[str]:
    """Why `key` cannot be stored as a .env value (None if it is fine). Never echoes the key."""
    if len(key) < 8:
        return "that looks too short for an API key"
    if re.search(r"[\s'\"#\\]", key) or any(ord(ch) < 32 or ord(ch) == 127 for ch in key):
        return "a key has no spaces, quotes, # or backslashes; check what you pasted"
    return None


def last4(key: str) -> str:
    """'ending abcd' for a long enough key, '' otherwise (a short key reveals too much).
    Plain ASCII: some Windows consoles cannot show an ellipsis."""
    return f"ending {key[-4:]}" if len(key) >= 12 else ""


def check_key(provider: str, key: str, timeout: float = VALIDATE_TIMEOUT) -> str:
    """
    One GET to the provider's model list. Returns "ok", "rejected" (the provider said the key
    is bad) or "unknown" (timeout, network error, any other answer: never blocks the setup).
    The key travels in a header, never in the URL.
    """
    if provider == "groq":
        url, headers = "https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {key}"}
        bad = (401, 403)
    else:
        url, headers = ("https://generativelanguage.googleapis.com/v1beta/models",
                        {"x-goog-api-key": key})
        bad = (400, 401, 403)           # Google answers 400 for a malformed or unknown key
    headers["User-Agent"] = "openpair"  # the default python-urllib agent is blocked by some CDNs
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout):
            return "ok"
    except urllib.error.HTTPError as e:
        return "rejected" if e.code in bad else "unknown"
    except Exception:  # noqa: BLE001 - timeout, DNS, TLS, anything: skip the check
        return "unknown"


# ── saving ───────────────────────────────────────────────────────────────────

def save_key(env_var: str, key: str, home: Optional[Path] = None) -> Path:
    """
    Write `env_var=key` to ~/.openpair/.env. An existing file keeps every other line, comment
    and line ending; the old content is first copied to .env.bak (0600). Atomic, 0600 where
    supported. Raises SaveError (message without the key) if the file cannot be read or written.
    """
    path = user_env_path(home)
    try:
        ensure_private_dir(path.parent)
        old = None
        if path.exists():
            try:
                old = path.read_bytes().decode("utf-8-sig")
            except UnicodeDecodeError:
                raise SaveError(f"{path} is not UTF-8 text, so it was left untouched") from None
            atomic_write_text(path.with_name(path.name + ".bak"), old)
        atomic_write_text(path, _with_key(old, env_var, key))
    except SaveError:
        raise
    except OSError as e:
        raise SaveError(f"could not write {path} ({type(e).__name__})") from None
    return path


def _with_key(old: Optional[str], env_var: str, key: str) -> str:
    """`old` (or an empty file) with `env_var=key` replaced in place or appended."""
    if not old:
        return f"{env_var}={key}\n"
    pattern = re.compile(rf"^(\s*(?:export\s+)?){re.escape(env_var)}\s*=[^\r\n]*", re.MULTILINE)
    new, n = pattern.subn(lambda m: f"{m.group(1)}{env_var}={key}", old)
    if n:
        return new
    eol = "\r\n" if "\r\n" in old else "\n"
    return old + ("" if old.endswith(("\n", "\r")) else eol) + f"{env_var}={key}{eol}"


# ── the guided flow ──────────────────────────────────────────────────────────

def run_first_run_setup(*, input_fn: Optional[Callable[[str], str]] = None,
                        getpass_fn: Optional[Callable[[str], str]] = None,
                        validate_fn: Optional[Callable[[str, str], str]] = None,
                        ollama_check: Optional[Callable[[], bool]] = None,
                        home: Optional[Path] = None) -> str:
    """
    Guide the user to a working setup. Returns READY (a key was set for this run, or Ollama
    answers), SKIPPED (the user chose to go on without) or CANCELLED (Ctrl+C / EOF; nothing
    was written). On READY with a key, the key is also in os.environ, so an OpenPair() built
    afterwards sees it.
    """
    # Resolved at call time (not as default arguments) so tests can replace them.
    input_fn = input_fn or input
    getpass_fn = getpass_fn or getpass.getpass
    validate_fn = validate_fn or check_key
    check = ollama_check or (lambda: ApiKeys().is_ollama_available(timeout=1.0))
    try:
        print("\nNo model is set up yet: no GROQ_API_KEY / GOOGLE_API_KEY and no Ollama found.\n"
              "Let's fix that (about a minute).  Ctrl+C cancels and saves nothing.\n",
              file=sys.stderr)
        while True:
            answer = input_fn("  [1] paste a cloud API key (free tier)   [2] use local Ollama   "
                              "[3] skip   (Enter = 1): ").strip().lower()
            if answer in ("", "1"):
                outcome = _cloud_flow(input_fn, getpass_fn, validate_fn, home)
            elif answer == "2":
                outcome = _local_flow(input_fn, check)
            elif answer in ("3", "s", "skip"):
                outcome = SKIPPED
            else:
                print("  Please type 1, 2 or 3.", file=sys.stderr)
                continue
            if outcome == "cloud":           # "c" typed inside the local flow
                outcome = _cloud_flow(input_fn, getpass_fn, validate_fn, home)
            break
    except (KeyboardInterrupt, EOFError):
        print("\nSetup cancelled; nothing was saved.", file=sys.stderr)
        return CANCELLED
    if outcome == SKIPPED:
        print("Skipped. Your first message will say what is missing; start Ollama or run "
              "`openpair chat` again to set up.", file=sys.stderr)
    return outcome


def _local_flow(input_fn, check) -> str:
    model = ApiKeys().ollama_model
    print(f"\n  1. Install Ollama: {OLLAMA_DOWNLOAD}\n"
          f"  2. Download a model (a few GB):  ollama pull {model}\n"
          f"     (it uses OLLAMA_MODEL; the default is llama3.1)\n"
          f"  3. Make sure Ollama is running.\n", file=sys.stderr)
    while True:
        answer = input_fn("  Press Enter to check again, c = use a cloud key instead, "
                          "q = skip: ").strip().lower()
        if answer in ("c", "cloud"):
            return "cloud"
        if answer in ("q", "quit", "s", "skip"):
            return SKIPPED
        if check():
            print("  Ollama is running. Ready.", file=sys.stderr)
            return READY
        print("  Ollama is still not reachable.", file=sys.stderr)


def _cloud_flow(input_fn, getpass_fn, validate_fn, home) -> str:
    while True:
        p = input_fn("\n  Provider: [1] groq (fast signup)   [2] google (Gemini)   "
                     "(Enter = 1): ").strip().lower()
        if p in ("", "1", "groq"):
            provider = "groq"
        elif p in ("2", "google"):
            provider = "google"
        else:
            print("  Please type 1 or 2.", file=sys.stderr)
            continue
        break
    env_var = CLOUD_KEY_VARS[provider]
    print(f"\n  Create a free {provider} key here: {KEY_PAGES[provider]}\n"
          f"  Paste it below. Nothing is shown while you type or paste; press Enter.",
          file=sys.stderr)

    key = None
    for _ in range(MAX_KEY_ATTEMPTS):
        candidate = (getpass_fn(f"  {env_var}: ") or "").strip()
        problem = key_problem(candidate)
        if problem:
            print(f"  Not accepted: {problem}.", file=sys.stderr)
            continue
        print(f"  Checking the key with {provider} (up to {int(VALIDATE_TIMEOUT)} s)...",
              file=sys.stderr)
        verdict = validate_fn(provider, candidate)
        if verdict == "unknown":
            print("  Could not check the key (no answer); continuing without the check.",
                  file=sys.stderr)
        elif verdict == "rejected":
            print(f"  {provider} rejected this key.", file=sys.stderr)
            if input_fn("  Save it anyway? [y/N] ").strip().lower() not in ("y", "yes"):
                continue
        else:
            print("  The key works.", file=sys.stderr)
        key = candidate
        break
    if key is None:
        print("  No usable key entered.", file=sys.stderr)
        return SKIPPED

    path = user_env_path(home)
    where = ("Plain text, owner-only (0600)." if os.name != "nt" else
             "Plain text; Windows protects it with the permissions of your user-profile folder.")
    choice = input_fn(f"\n  Save to {path}? {where}\n"
                      f"  [Y] save   [n] use for this chat only   [p] print export commands: "
                      ).strip().lower()
    if choice in ("p", "print"):
        print("  To set it yourself (replace <your key>):\n"
              f"    PowerShell:  $env:{env_var}=\"<your key>\"\n"
              f"    bash/zsh:    export {env_var}=<your key>\n"
              "  Using the key you just entered for this chat only.", file=sys.stderr)
    elif choice in ("", "y", "yes"):
        try:
            saved = save_key(env_var, key, home)
            print(f"  Saved to {saved}.", file=sys.stderr)
        except SaveError as e:
            print(f"  Could not save: {e}. Using the key for this chat only.", file=sys.stderr)
    else:
        print("  Not saved. Using the key for this chat only.", file=sys.stderr)

    os.environ[env_var] = key
    print(f"  Ready: {provider} key {last4(key)}".rstrip(), file=sys.stderr)
    return READY
