"""
openpair.chat_cli — minimal interactive REPL: `openpair chat`
================================================================
Usage:
    openpair chat
    openpair chat --provider groq --system "Answer in Thai."

Type /exit (or press Ctrl+D / Ctrl+C) to leave. Plain input()/print(), no
streaming and no other slash commands yet.
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

        try:
            result = session.send(line)
        except KeyboardInterrupt:
            print(file=sys.stderr)
            return 0
        except Exception as e:  # noqa: BLE001 - REPL must survive any API failure
            # send() leaves the history untouched on failure, so the user can retry.
            msg = " ".join(str(e).split()) or type(e).__name__
            if len(msg) > 200:
                msg = msg[:197] + "..."
            print(f"Error: {msg}", file=sys.stderr)
            continue

        print(result.response_text)
        print(format_status(result, session.last_fallback_from), file=sys.stderr)


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
