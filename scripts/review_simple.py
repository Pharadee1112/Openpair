"""
review_simple.py — simple human-review sheet (one line = one full answer)
=====================================================================
  python scripts/review_simple.py make    write paper/review_simple.csv
  python scripts/review_simple.py merge   collect verdicts → paper/human_review.csv

Answers come from the 2026-10-17 rerun of the 154 cases in paper/slang_review.csv, which stores full text:
  benchmark_results_gemini_review.json, benchmark_results_groq_review.json
(the original full-suite run kept only 80 characters). These are NEW answers, so the paper's
verdicts in review_verdicts_old.tsv do not carry over to them.

Blind review: model names and machine scores are hidden and answer order is shuffled per question (fixed seed).
The code column maps answers back to models — reviewers must not edit it.
Column headers are Thai on purpose: the sheet is filled in by native Thai reviewers.
"""

from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYS = ROOT / "paper" / "slang_review.csv"      # case list + confirmed answer keys
SIMPLE = ROOT / "paper" / "review_simple.csv"   # the sheet reviewers fill in
OUT = ROOT / "paper" / "human_review.csv"       # merged: case × model × verdict × machine score

MODELS = [
    ("gemini-3.1-flash-lite", "benchmark_results_gemini_review.json", "Gemini 3.1 Flash-Lite"),
    ("openai/gpt-oss-120b",   "benchmark_results_groq_review.json",   "gpt-oss-120b"),
    ("openai/gpt-oss-20b",    "benchmark_results_groq_review.json",   "gpt-oss-20b"),
]
CATEGORY_ORDER = ["qa", "translation", "classification", "creative"]  # qa first — the most important
VERDICT = "ถูกไหม (Y/N/?)"
NOTE = "หมายเหตุ"
CODE = "รหัส (ห้ามแก้)"
SEED = 20261017


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def load_answers() -> dict[str, dict[str, dict]]:
    """model_id -> case_id -> score row (with full response)"""
    out: dict[str, dict[str, dict]] = {}
    for model_id, fname, _ in MODELS:
        data = json.loads((ROOT / fname).read_text(encoding="utf-8"))
        entry = next(m for m in data["models"] if m["model_id"] == model_id)
        out[model_id] = {s["id"]: s for s in entry["scores"]}
    return out


def make() -> None:
    if SIMPLE.exists() and any(r[VERDICT].strip() for r in read_csv(SIMPLE)):
        sys.exit(f"{SIMPLE} already has verdicts — merge first, or delete it yourself to start over")
    cases = sorted(read_csv(KEYS), key=lambda x: CATEGORY_ORDER.index(x["category"]))
    answers = load_answers()
    rng = random.Random(SEED)
    out, missing, n = [], [], 0
    for c in cases:
        n += 1
        order = list(range(len(MODELS)))
        rng.shuffle(order)
        for idx in order:
            model_id = MODELS[idx][0]
            s = answers[model_id].get(c["case_id"])
            if s is None or not s.get("response"):
                missing.append(f"{c['case_id']}/{model_id}")
                continue
            out.append({
                "ข้อ": n,
                "หมวด": c["category"],
                "คำถาม": c["prompt"],
                "เฉลย (คำที่ควรมี)": c["expected_keywords"],
                "คำตอบ": s["response"].strip(),
                VERDICT: "",
                NOTE: "",
                CODE: f"{c['case_id']}|{idx}",
            })
    write_csv(SIMPLE, out)
    print(f"wrote {SIMPLE} ({n} questions, {len(out)} answers)")
    if missing:
        print(f"{len(missing)} answers missing (left out of the sheet): {', '.join(missing)}")


def merge() -> None:
    answers = load_answers()
    rows = []
    for s in read_csv(SIMPLE):
        case_id, idx = s[CODE].split("|")
        model_id, _, label = MODELS[int(idx)]
        a = answers[model_id][case_id]
        rows.append({
            "case_id": case_id,
            "category": s["หมวด"],
            "model": label,
            "human": s[VERDICT].strip().upper(),
            "machine_score": a["final_score"],
            "machine_passed": a["passed"],
            "note": s[NOTE].strip(),
        })
    rows.sort(key=lambda r: (CATEGORY_ORDER.index(r["category"]), r["case_id"], r["model"]))
    write_csv(OUT, rows)
    done = sum(1 for r in rows if r["human"])
    print(f"wrote {OUT} ({done}/{len(rows)} answers reviewed)")


if __name__ == "__main__":
    {"make": make, "merge": merge}[sys.argv[1] if len(sys.argv) > 1 else "make"]()
