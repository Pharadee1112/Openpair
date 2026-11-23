"""
openpair.chat_cli — minimal interactive REPL: `openpair chat`
================================================================
Usage:
    openpair chat
    openpair chat --provider groq --system "Answer in Thai."
    openpair chat --resume              # continue the latest saved session
    openpair chat --resume list         # list saved sessions
    openpair chat --no-save             # write nothing to ~/.openpair/sessions/
    openpair chat --resume 20261123     # continue the session whose id starts with this

Replies are streamed token by token (Ctrl+C while a reply is streaming cancels just
that reply; Ctrl+C or Ctrl+D at the prompt leaves). Lines starting with "/" are
commands and are never sent to the model - type /help. To send a message that starts
with "/", start it with "//" (the first slash is dropped).
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from .attach import AttachError, TOKEN_WARN, estimate_tokens, validate_attachment
from .caller import is_loopback_url
from .client import OpenPair
from .errors import NoProviderError
from .session import ChatSession, ConfirmationRequired
from . import setup_wizard
from .session_store import (
    AmbiguousSession,
    NoSuchSession,
    SessionError,
    SessionRecorder,
    find_session,
    format_listing,
    list_sessions,
    load_session_file,
    restore_attachments,
    restore_into,
)

PROMPT = "you> "


def build_chat_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openpair chat",
        description="Interactive multi-turn chat with automatic model routing.",
    )
    parser.add_argument("--provider", default=None,
                        help="Pin to a specific provider: google | groq | ollama")
    parser.add_argument("--system", default=None, help="Optional system prompt.")
    parser.add_argument("--max-tokens", type=int, default=2048,
                        help="Maximum tokens per response (default: 2048).")
    parser.add_argument("--no-save", action="store_true",
                        help="Do not save this chat: nothing is written to ~/.openpair/sessions/. "
                             "Cannot be combined with --resume.")
    parser.add_argument("--resume", nargs="?", const="latest", default=None, metavar="ID",
                        help="Continue a saved session from ~/.openpair/sessions/: no value = "
                             "the latest, an id or unique id prefix = that one, 'list' = show "
                             "the saved sessions. Sessions are saved as plain text after every reply.")
    return parser


def format_status(result, fallback_from: Optional[str], local_only: bool = False) -> str:
    fallback = f"from {fallback_from}" if fallback_from else "none"
    mode = " | mode: local" if local_only else ""
    return (
        f"model: {result.model_name} ({result.provider}) | tier {result.tier} "
        f"| fallback: {fallback} "
        f"| {result.input_tokens}+{result.output_tokens} tok "
        f"| {result.latency_ms:.0f}ms{mode}"
    )


# ── Slash commands ───────────────────────────────────────────────────────────

PROVIDERS = ("google", "groq", "ollama")

HELP_TEXT = """Commands (lines starting with "/" are never sent to the model):
  /help                  show this list
  /exit                  quit (Ctrl+D / Ctrl+C at the prompt also work)
  /clear                 forget the conversation, attached files and cloud approvals
  /add <file>            attach a text file (read-only) to your NEXT message. Only files
                         inside the current folder; secrets files and keys are refused;
                         max 64 KB per file, 5 files / 128 KB at once. Cloud: you are
                         asked y/N, naming the provider, before the text is sent.
  /files                 list attached files
  /route <text>          dry run: show which model would answer <text>; no API call
  /provider [name]       pin the provider: google | groq | ollama | auto (no argument: show)
  /model                 show the model used in the last reply. Display only: the router
                         chooses the model and an exact model id cannot be pinned
                         (for Ollama set OLLAMA_MODEL)
  /local [on|off]        local-only mode: requests go only to Ollama on this machine,
                         never to a cloud provider (no argument: show)
Start a message with // to send text that begins with "/"."""


def _cmd_help(session, arg):
    print(HELP_TEXT)


def _cmd_clear(session, arg):
    session.clear()
    print("History cleared.")


def _cmd_add(session, arg):
    if not arg:
        print("Usage: /add <file>", file=sys.stderr)
        return
    try:
        att = validate_attachment(arg)
        session.add_attachment(att)
    except AttachError as e:
        print(f"Error: {e}", file=sys.stderr)
        return
    tokens = estimate_tokens(att.text)
    print(f"Attached {att.path} ({att.chars:,} chars, ~{tokens:,} tokens). "
          "It is sent with your next message.")
    if tokens > TOKEN_WARN:
        print(f"Warning: that is a lot of context (~{tokens:,} tokens, over {TOKEN_WARN:,}); "
              "it is re-sent with every later turn and may exceed a small model's limit.",
              file=sys.stderr)
    if not session.local_only:
        print("Cloud mode: you will be asked before the file leaves this machine.")


def _cmd_files(session, arg):
    if not session.pending_attachments and not session.sent_attachments:
        print("No attached files.")
        return
    for a in session.pending_attachments:
        print(f"  pending  {a.path}  ({a.chars:,} chars, ~{estimate_tokens(a.text):,} tokens)")
    pending = {a.path for a in session.pending_attachments}
    for ref in session.sent_attachments:
        if ref["path"] not in pending:
            print(f"  sent     {ref['path']}  ({ref['chars']:,} chars; still in the history)")


def _cmd_route(session, arg):
    if not arg:
        print("Usage: /route <text>", file=sys.stderr)
        return
    d = session.route(arg)  # no API call, history untouched
    print(f"Model:    {d.model_name} ({d.model_id})")
    print(f"Provider: {d.provider}")
    print(f"Tier:     {d.tier}")
    print(f"Score:    {d.complexity_score}/10")
    print(f"Reason:   {d.reason}")
    if session.local_only:
        print("Local mode is on: the request would run on Ollama instead "
              f"({session._client._keys.ollama_model}).")


def _cmd_provider(session, arg):
    if not arg:
        print(f"provider: {session.preferred_provider or 'auto'}"
              + (" (ignored: local mode is on)" if session.local_only else ""))
        return
    name = arg.lower()
    if name == "auto":
        session.preferred_provider = None
    elif name in PROVIDERS:
        session.preferred_provider = name
    else:
        print(f"Error: unknown provider {arg!r}. Use google, groq, ollama or auto.", file=sys.stderr)
        return
    print(f"provider: {session.preferred_provider or 'auto'}"
          + (" (ignored: local mode is on)" if session.local_only else ""))


def _cmd_model(session, arg):
    r = session.last_result
    if r is None:
        print("No reply yet in this session.")
    else:
        print(f"model: {r.model_name} ({r.model_id}) via {r.provider}")


def _cmd_local(session, arg):
    if arg:
        value = arg.lower()
        if value not in ("on", "off"):
            print("Usage: /local [on|off]", file=sys.stderr)
            return
        session.local_only = value == "on"
        if session.local_only:
            url = session._client.local_ollama_url()
            if not is_loopback_url(url):
                print(f"Warning: Ollama URL {url!r} is not a loopback address; local mode "
                      f"stays on and requests will be refused until it is fixed.", file=sys.stderr)
    print(f"mode: {'local (Ollama only, no cloud)' if session.local_only else 'auto (cloud and local)'}")


COMMANDS = {
    "help": _cmd_help,
    "clear": _cmd_clear,
    "add": _cmd_add,
    "files": _cmd_files,
    "route": _cmd_route,
    "provider": _cmd_provider,
    "model": _cmd_model,
    "local": _cmd_local,
}


def handle_command(session: ChatSession, line: str) -> bool:
    """Run one "/command". Returns True if the REPL should exit."""
    name, _, arg = line[1:].partition(" ")
    name = name.lower()
    if name == "exit":
        return True
    handler = COMMANDS.get(name)
    if handler is None:
        print(f"Error: unknown command /{name}", file=sys.stderr)
        print(HELP_TEXT, file=sys.stderr)
        return False
    handler(session, arg.strip())
    return False


def run_chat(session: ChatSession, recorder: Optional[SessionRecorder] = None) -> int:
    """Read lines until /exit, EOF or Ctrl+C. Always returns 0 on a normal exit.
    With a `recorder`, the session is saved after every COMPLETED turn."""
    while True:
        try:
            line = input(PROMPT)
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)  # finish the prompt line
            return 0

        line = line.strip()
        if not line:
            continue
        if line.startswith("//"):
            line = line[1:]  # escape: send "/text" to the model
        elif line.startswith("/"):
            if handle_command(session, line):
                return 0
            continue

        if not _confirm_cloud_send(session, line):
            continue

        if not _stream_reply(session, line):
            continue

        if recorder is not None:
            recorder.save(session)

        print(format_status(session.last_result, session.last_fallback_from, session.local_only),
              file=sys.stderr)


NO_PROVIDER_HELP = (
    "Error: No API key found for any provider, and Ollama is not running.\n"
    "  To fix it, do one of these:\n"
    "    - quit (/exit) and run `openpair chat` again: it offers a guided setup\n"
    "    - start Ollama (ollama serve), then send your message again\n"
    "    - put GROQ_API_KEY=... or GOOGLE_API_KEY=... in ~/.openpair/.env or the environment"
)


def _error_text(e: Exception) -> str:
    """One-line (or, for 'no provider at all', a short how-to-fix) text for a failed send."""
    if isinstance(e, NoProviderError):
        return NO_PROVIDER_HELP
    msg = " ".join(str(e).split()) or type(e).__name__
    return f"Error: {msg}"


def _stdout_is_tty() -> bool:
    try:
        return bool(sys.stdout.isatty())
    except Exception:  # noqa: BLE001 - closed or replaced stdout
        return False


def _stdin_is_tty() -> bool:
    try:
        return bool(sys.stdin.isatty())
    except Exception:  # noqa: BLE001 - closed or replaced stdin
        return False


def _ask_yes_no(question: str) -> bool:
    """y/N. Anything but y/yes is no. Without a terminal there is nobody to ask: no."""
    if not _stdin_is_tty():
        print("stdin is not a terminal, so the question counts as 'n': nothing was sent.",
              file=sys.stderr)
        return False
    try:
        return input(question).strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print(file=sys.stderr)
        return False


def _confirm_cloud_send(session: ChatSession, line: str) -> bool:
    """
    Before every send that would put attached-file text in front of a cloud provider
    the user has not confirmed yet (a pending file, or file text already in the history
    from an earlier turn, e.g. one sent in local mode before /local off). Returns False
    if the send must not happen; in that case nothing was sent and attachments stay.
    """
    try:
        need = session.cloud_confirmation_needed(line)
    except Exception as e:  # noqa: BLE001 - e.g. no usable provider at all
        print(_error_text(e), file=sys.stderr)
        return False
    if need is None:
        return True
    provider, label = need
    what = "attached file text" + (" (already in this conversation)"
                                   if session.messages and not session.pending_attachments else "")
    if _ask_yes_no(f"This request includes {what} and would be sent to {label}, "
                   f"which is not on this machine. Send it? [y/N] "):
        session.confirm_cloud(provider)
        return True
    print("Not sent. Use /local on to keep it on this machine, or /clear to drop the files.",
          file=sys.stderr)
    return False


def _stream_reply(session: ChatSession, line: str) -> bool:
    """
    Print one streamed reply as it arrives. Returns True if it completed.
    On cancel (Ctrl+C) or error the partial text stays on screen and the session
    history is unchanged (ChatSession.stream only commits on success).
    """
    stream = session.stream(line)
    printed = False
    try:
        for chunk in stream:
            print(chunk, end="", flush=True)
            printed = True
    except KeyboardInterrupt:
        stream.close()  # closes the provider stream too
        if printed:
            print(flush=True)  # end the partial line
        print("[cancelled]", file=sys.stderr)
        return False
    except ConfirmationRequired as e:  # safety net: _confirm_cloud_send should have caught it
        print(f"Error: not sent; {e}", file=sys.stderr)
        return False
    except Exception as e:  # noqa: BLE001 - REPL must survive any API failure
        text = _error_text(e)
        if len(text) > 200 and not isinstance(e, NoProviderError):
            text = text[:197] + "..."
        if printed:
            print(flush=True)  # end the partial line
        print(text, file=sys.stderr)
        return False
    print(flush=True)  # end the reply line before the status line goes to stderr
    return True


def chat_main(argv: Optional[Sequence[str]] = None) -> int:
    # Same Windows console fix as the one-shot CLI: replace unencodable chars
    # (e.g. Thai on cp1252) instead of crashing.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    args = build_chat_parser().parse_args(argv)

    if args.no_save and args.resume is not None:
        print("Error: --no-save cannot be used with --resume (resuming means saving).",
              file=sys.stderr)
        return 2

    if args.resume == "list":
        print(format_listing(list_sessions()))
        return 0

    # First run: no key and no Ollama, on a terminal. Runs BEFORE OpenPair() is built, so the
    # key it puts in os.environ is what ApiKeys reads. Never runs for piped input or output.
    if setup_wizard.setup_needed(stdin_tty=_stdin_is_tty(), stdout_tty=_stdout_is_tty()):
        if setup_wizard.run_first_run_setup() == setup_wizard.CANCELLED:
            return 130

    # The pin lives only on the session (so /provider auto can really unpin).
    session = ChatSession(
        OpenPair(),
        system=args.system,
        preferred_provider=args.provider,
        max_tokens=args.max_tokens,
    )

    recorder_args: dict = {}
    if args.resume is not None:
        code = _resume(session, args, recorder_args)
        if code is not None:
            return code
    if args.no_save:
        print("not saving this chat (--no-save)", file=sys.stderr)
        return run_chat(session, None)   # no recorder: nothing is ever written
    recorder = SessionRecorder(session, **recorder_args)
    print(f"session {recorder.id} (saved as plain text after each reply; "
          f"'openpair chat --resume' continues it)", file=sys.stderr)
    return run_chat(session, recorder)


def _resume(session: ChatSession, args, recorder_args: dict) -> Optional[int]:
    """
    Load the saved session named by --resume into `session`. Returns an exit code if the
    program should stop (ambiguous or unknown id), or None to go on (resumed, or a fresh
    chat after a one-line explanation). A bad session file is never deleted or changed.
    """
    try:
        path = find_session(args.resume)
    except AmbiguousSession as e:
        print(f"Error: {e}. Use a longer prefix:", file=sys.stderr)
        for sid in e.matches:
            print(f"  {sid}", file=sys.stderr)
        return 2
    except NoSuchSession as e:
        if args.resume == "latest":
            print("No saved sessions; starting a new chat.", file=sys.stderr)
            return None
        print(f"Error: {e}. Run 'openpair chat --resume list' to see them.", file=sys.stderr)
        return 2

    try:
        data = load_session_file(path)
    except SessionError as e:
        print(f"Could not resume {path.name}: {e}. Starting a new chat (the file was left as it "
              f"is). Run 'openpair chat --resume list' to see other sessions.", file=sys.stderr)
        return None

    warnings = restore_into(session, data,
                            keep_system=args.system is not None,
                            keep_pin=args.provider is not None)
    warnings += restore_attachments(session, data["attachments"])
    for w in warnings:
        print(f"Warning: {w}", file=sys.stderr)
    turns = len(data["messages"]) // 2
    print(f"Resumed {path.stem}: {turns} turn{'s' if turns != 1 else ''}"
          + (", local mode on" if session.local_only else "")
          + (f", {len(session.pending_attachments)} file(s) re-attached to your next message"
             if session.pending_attachments else "") + ".")
    recorder_args.update(session_id=path.stem, created=data["created"] or None)
    return None
