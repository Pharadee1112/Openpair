"""
scripts/update_registry_scores.py
===================================
Read benchmark results JSON and auto-patch thai_score in src/registry.rs.

Usage:
    python scripts/update_registry_scores.py
    python scripts/update_registry_scores.py --results benchmark_results.json
    python scripts/update_registry_scores.py --results my_results.json --dry-run
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path


def patch_registry(
    results_path: str,
    registry_path: str,
    dry_run: bool = False,
) -> dict[str, tuple[int, int]]:
    """
    Read suggested_thai_score from results JSON and patch registry.rs.

    Returns:
        dict of model_id -> (old_score, new_score)
    """
    results_file  = Path(results_path)
    registry_file = Path(registry_path)

    if not results_file.exists():
        print(f"ERROR: results file not found: {results_path}", file=sys.stderr)
        sys.exit(1)
    if not registry_file.exists():
        print(f"ERROR: registry file not found: {registry_path}", file=sys.stderr)
        sys.exit(1)

    data    = json.loads(results_file.read_text(encoding="utf-8"))
    content = registry_file.read_text(encoding="utf-8")
    changes: dict[str, tuple[int, int]] = {}

    for model in data.get("models", []):
        model_id  = model["model_id"]
        new_score = int(model["suggested_thai_score"])

        # Match ModelMeta line containing id: "model_id" and update thai_score: N
        pattern = rf'(ModelMeta\s*\{{[^}}]*id:\s*"{re.escape(model_id)}"[^}}]*thai_score:\s*)(\d+)'

        def replacer(m, _new=new_score, _mid=model_id):
            old = int(m.group(2))
            changes[_mid] = (old, _new)
            return f"{m.group(1)}{_new}"

        new_content = re.sub(pattern, replacer, content)
        if new_content != content:
            content = new_content
        elif model_id not in changes:
            print(f"  WARNING: {model_id!r} not found in registry -- skipped")

    if changes and not dry_run:
        registry_file.write_text(content, encoding="utf-8")

    return changes


def main() -> None:
    # Force UTF-8 output so Thai text prints correctly on Windows
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Update thai_score in registry.rs from benchmark results"
    )
    parser.add_argument(
        "--results",  default="benchmark_results.json",
        help="path to benchmark results JSON (default: benchmark_results.json)",
    )
    parser.add_argument(
        "--registry", default="src/registry.rs",
        help="path to registry.rs (default: src/registry.rs)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="show planned changes without writing to disk",
    )
    args = parser.parse_args()

    mode = " [dry-run]" if args.dry_run else ""
    print(f"\n=== update_registry_scores{mode} ===")
    print(f"  results:  {args.results}")
    print(f"  registry: {args.registry}\n")

    changes = patch_registry(args.results, args.registry, dry_run=args.dry_run)

    if not changes:
        print("No matching models found in registry -- nothing updated.")
        return

    print(f"  {'Model ID':<45} {'old':>5}  {'new':>4}")
    print("  " + "-" * 58)
    for model_id, (old, new) in sorted(changes.items()):
        tag = "<-- changed" if old != new else "(no change)"
        print(f"  {model_id:<45} {old:>5}  {new:<4}  {tag}")

    changed_count = sum(1 for old, new in changes.values() if old != new)

    if args.dry_run:
        print(f"\n[dry-run] Would update {changed_count} model(s). Run without --dry-run to apply.")
    else:
        print(f"\nDone: updated {changed_count} model(s) in {args.registry}")
        if changed_count > 0:
            print("Next step: run `maturin develop` to rebuild the Rust core.")


if __name__ == "__main__":
    main()
