"""
openpair.chat_cli — minimal interactive REPL: `openpair chat`
================================================================
Usage:
    openpair chat
    openpair chat --provider groq --system "Answer in Thai."

Type /exit (or press Ctrl+D / Ctrl+C) to leave. Replies are streamed token by token
(Ctrl+C while a reply is streaming cancels just that reply). Plain input()/print().
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from .client import OpenPair
from .session import ChatSession

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


def format_status(result, fallback_from: Optional[str]) -> str:
    fallback = f"from {fallback_from}" if fallback_from else "none"
    return (
        f"model: {result.model_name} ({result.provider}) | tier {result.tier} "
        f"| fallback: {fallback} "
        f"| {result.input_tokens}+{result.output_tokens} tok "
        f"| {result.latency_ms:.0f}ms"
    )


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
        if line == "/exit":
            return 0

        if not _stream_reply(session, line):
            continue

        print(format_status(session.last_result, session.last_fallback_from), file=sys.stderr)


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
    session = ChatSession(
        OpenPair(preferred_provider=args.provider),
        system=args.system,
        preferred_provider=args.provider,
        max_tokens=args.max_tokens,
    )
    return run_chat(session)
