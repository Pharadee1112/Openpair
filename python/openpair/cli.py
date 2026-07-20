"""
openpair.cli — Command-line interface
=========================================
Usage:
    openpair "What is Python?"
    openpair "สวัสดีครับ" --provider groq
    openpair "Explain black holes" --route-only
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from .client import OpenPair


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openpair",
        description="Route a prompt to the best AI model, and (unless --route-only) call it.",
    )
    parser.add_argument("prompt", help="The prompt to route/send.")
    parser.add_argument(
        "--provider",
        default=None,
        help="Pin to a specific provider: openai | anthropic | google | groq | ollama",
    )
    parser.add_argument(
        "--route-only",
        action="store_true",
        help="Only print the routing decision, don't make an API call.",
    )
    parser.add_argument(
        "--system",
        default=None,
        help="Optional system prompt.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=2048,
        help="Maximum tokens in the response (default: 2048).",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    # Windows consoles often default to a legacy codepage (cp874, cp1252, ...)
    # that can't encode routing-reason characters like "→" or Thai text —
    # replace instead of crashing.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    parser = build_parser()
    args = parser.parse_args(argv)

    client = OpenPair(preferred_provider=args.provider)

    if args.route_only:
        decision = client.route(args.prompt, preferred_provider=args.provider)
        print(f"Model:    {decision.model_name} ({decision.model_id})")
        print(f"Provider: {decision.provider}")
        print(f"Tier:     {decision.tier}")
        print(f"Score:    {decision.complexity_score}/10")
        print(f"Reason:   {decision.reason}")
        return 0

    try:
        result = client.call(
            args.prompt,
            preferred_provider=args.provider,
            system=args.system,
            max_tokens=args.max_tokens,
        )
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(result.response_text)
    print(
        f"\n— {result.model_name} via {result.provider} "
        f"| {result.input_tokens}+{result.output_tokens} tok "
        f"| ${result.estimated_cost:.5f} | {result.latency_ms:.0f}ms",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
