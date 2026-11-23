"""
openpair.chat_cli — minimal interactive REPL: `openpair chat`
================================================================
Usage:
    openpair chat
    openpair chat --provider groq --system "Answer in Thai."

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
from .session import ChatSession, ConfirmationRequired

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


def run_chat(session: ChatSession) -> int:
    """Read lines until /exit, EOF or Ctrl+C. Always returns 0 on a normal exit."""
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

        print(format_status(session.last_result, session.last_fallback_from, session.local_only),
              file=sys.stderr)


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
        print(f"Error: {' '.join(str(e).split()) or type(e).__name__}", file=sys.stderr)
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
        msg = " ".join(str(e).split()) or type(e).__name__
        if len(msg) > 200:
            msg = msg[:197] + "..."
        if printed:
            print(flush=True)  # end the partial line
        print(f"Error: {msg}", file=sys.stderr)
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
    # The pin lives only on the session (so /provider auto can really unpin).
    session = ChatSession(
        OpenPair(),
        system=args.system,
        preferred_provider=args.provider,
        max_tokens=args.max_tokens,
    )
    return run_chat(session)
