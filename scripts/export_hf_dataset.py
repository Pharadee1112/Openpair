"""
export_hf_dataset.py — export the benchmark and human review as a Hugging Face dataset
======================================================================================
Writes JSON Lines files next to the dataset card (hf_dataset/README.md). No API calls.

  hf_dataset/data/benchmark.jsonl     600 cases of the full suite
  hf_dataset/data/human_review.jsonl  462 blind human verdicts (154 cases × 3 models)

  python scripts/export_hf_dataset.py

Prompts, answers and expected keywords stay in Thai — they are what the benchmark measures.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "scripts"))

from openpair.benchmark.dataset import get_suite  # noqa: E402
from analyze_behavior import group_of  # noqa: E402
from analyze_human_review import MODELS, load_machine  # noqa: E402

OUT = ROOT / "hf_dataset" / "data"


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {path} ({len(rows)} rows)")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    cases = get_suite("full")
    write_jsonl(OUT / "benchmark.jsonl", [{
        "id": c.id,
        "category": c.category,
        "difficulty": c.difficulty,
        "content_type": group_of(c.notes or ""),
        "prompt": c.prompt,
        "expected_keywords": c.expected_keywords,
        "keyword_threshold": c.keyword_threshold,
        "min_thai_ratio": c.min_thai_ratio,
        "min_length": c.min_length,
        "notes": c.notes,
    } for c in cases])

    machine = load_machine()
    rows = []
    with open(ROOT / "paper" / "review_verdicts_old.tsv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            case_id, idx = r["code"].split("|")
            model_id = MODELS[int(idx)][0]
            m = machine[int(idx)][case_id]
            rows.append({
                "case_id": case_id,
                "category": m["category"],
                "model": model_id,
                "answer_preview": m["preview"],
                "human_verdict": r["verdict"],
                "reviewer_note_th": r["note"],
                "reviewer_note_en": r["note_en"],
                "machine_score": m["final_score"],
                "machine_passed": m["passed"],
            })
    write_jsonl(OUT / "human_review.jsonl", rows)


if __name__ == "__main__":
    main()
