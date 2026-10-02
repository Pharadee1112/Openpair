"""
compare_results.py — เทียบผล Thai benchmark ข้าม model แยกตามหมวดงาน
=====================================================================
อ่านไฟล์ benchmark_results_*.json แล้วเขียนตารางเทียบเป็น Markdown
บอกว่าแต่ละหมวดงาน (qa / translation / ...) model ไหนได้คะแนนดีที่สุด

Usage:
    python scripts/compare_results.py                     # เขียน BENCHMARK_COMPARISON.md
    python scripts/compare_results.py --output other.md

เทียบ 2 แบบ เพราะแต่ละ model รันชุดข้อสอบไม่เท่ากัน:
  1. ชุด core (20 เคสเดียวกันทุก model) — ยุติธรรมที่สุด เทียบได้ทุกตัว
  2. ชุด full (600 เคส) — เฉพาะ model ที่รันครบชุด full
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from openpair.benchmark.dataset import get_suite  # noqa: E402

CATEGORIES = ["qa", "translation", "summarization", "classification", "code_thai", "creative"]

# แหล่งผลของแต่ละ model — ใช้ไฟล์ล่าสุดที่วัด model นั้น
# (model_id, ไฟล์, ป้ายบอกที่มา)
SOURCES = [
    ("gemini-3.1-flash-lite",                  "benchmark_results_gemini_full.json",      "Gemini"),
    ("gemini-3.6-flash",                       "benchmark_results_gemini_2026_part2.json", "Gemini"),
    ("openai/gpt-oss-20b",                     "benchmark_results_groq_full.json",        "Groq"),
    ("openai/gpt-oss-120b",                    "benchmark_results_groq_full.json",        "Groq"),
    ("nvidia/nemotron-3-super-120b-a12b:free", "benchmark_results_openrouter_core.json",  "OpenRouter (ไม่อยู่ใน registry)"),
]


def load_scores() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for model_id, fname, _ in SOURCES:
        path = ROOT / fname
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for m in data["models"]:
            if m["model_id"] == model_id:
                out[model_id] = m["scores"]
    return out


def category_table(scores: dict[str, list[dict]], case_ids: set[str] | None) -> tuple[list[str], dict, dict]:
    """คืน (models, avg[model][cat], n[model]) — ถ้า case_ids ไม่ใช่ None ใช้เฉพาะเคสในเซ็ตนั้น"""
    avg: dict[str, dict[str, float]] = {}
    count: dict[str, int] = {}
    for model, rows in scores.items():
        rows = [r for r in rows if case_ids is None or r["id"] in case_ids]
        if not rows:
            continue
        by_cat: dict[str, list[float]] = defaultdict(list)
        for r in rows:
            by_cat[r["category"]].append(r["final_score"])
        avg[model] = {c: sum(v) / len(v) for c, v in by_cat.items()}
        avg[model]["_all"] = sum(r["final_score"] for r in rows) / len(rows)
        count[model] = len(rows)
    return list(avg), avg, count


def render(models: list[str], avg: dict, count: dict) -> str:
    cols = CATEGORIES + ["_all"]
    head = "| Model | เคส | " + " | ".join("รวม" if c == "_all" else c for c in cols) + " |"
    sep = "|---|---:|" + "---:|" * len(cols)
    best = {c: max((avg[m].get(c, -1) for m in models), default=-1) for c in cols}
    lines = [head, sep]
    for m in sorted(models, key=lambda m: -avg[m]["_all"]):
        cells = []
        for c in cols:
            v = avg[m].get(c)
            if v is None:
                cells.append("–")
            else:
                cells.append(f"**{v:.2f}**" if abs(v - best[c]) < 1e-9 else f"{v:.2f}")
        lines.append(f"| `{m}` | {count[m]} | " + " | ".join(cells) + " |")
    winners = []
    for c in CATEGORIES:
        top = [m for m in models if abs(avg[m].get(c, -1) - best[c]) < 1e-9]
        winners.append(f"- **{c}**: " + ", ".join(f"`{m}`" for m in top) + f" ({best[c]:.2f})")
    return "\n".join(lines) + "\n\nดีที่สุดในแต่ละหมวด:\n" + "\n".join(winners) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="เทียบผล Thai benchmark แยกตามหมวดงาน")
    parser.add_argument("--output", default=str(ROOT / "BENCHMARK_COMPARISON.md"))
    args = parser.parse_args()

    scores = load_scores()
    core_ids = {c.id for c in get_suite("core")}
    full_total = len(get_suite("full"))

    core_models, core_avg, core_n = category_table(scores, core_ids)
    full_scores = {m: s for m, s in scores.items() if len(s) >= full_total * 0.95}
    full_models, full_avg, full_n = category_table(full_scores, None)

    origin = "\n".join(f"- `{m}` — {label}, จาก `{f}`" for m, f, label in SOURCES if m in scores)

    md = f"""# Thai Benchmark — เทียบ model แยกตามหมวดงาน

> สร้างโดย `python scripts/compare_results.py` — อย่าแก้มือ รันสคริปต์ใหม่เมื่อมีผล benchmark ใหม่
> คะแนน 0–10 ต่อเคส (keyword 50% + สัดส่วนภาษาไทย 30% + ความยาว 20%) — ตัวหนา = ดีที่สุดในคอลัมน์นั้น

## 1. ชุด core — 20 เคสเดียวกันทุก model (เทียบได้ยุติธรรมที่สุด)

{render(core_models, core_avg, core_n)}
หมายเหตุ: 20 เคสคือ 3–4 เคสต่อหมวด ต่างกันไม่กี่ทศนิยมยังถือว่าสูสี ใช้ดูแนวโน้ม ไม่ใช่ตัดสินเด็ดขาด
`gemini-3.6-flash` วัดเมื่อ 2026-07-28 ด้วย runner รุ่นเก่า (ก่อนแก้ปัญหาคำตอบว่าง) คะแนนอาจต่ำกว่าความจริงเล็กน้อย

## 2. ชุด full — 600 เคส (100 ต่อหมวด) เฉพาะ model ที่รันครบ

{render(full_models, full_avg, full_n)}
## ที่มาของผล

{origin}
"""
    Path(args.output).write_text(md, encoding="utf-8")
    print(f"เขียน {args.output}")


if __name__ == "__main__":
    main()
