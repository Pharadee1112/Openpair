"""
analyze_stability.py — ความแปรปรวนระหว่างรอบ (run-to-run stability)
=====================================================================
เทียบชุด full เดิม (2026-10-01/02) กับการรันซ้ำ 154 เคส (2026-10-17, `--cases @paper/review_case_ids.txt`)
บนเคสที่ทั้งสองรอบมีคำตอบ → paper/STABILITY.md (ไม่เรียก API)

  python scripts/analyze_stability.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "paper" / "STABILITY.md"

# model_id, ไฟล์รอบเดิม, ไฟล์รอบซ้ำ, ชื่อในตาราง
MODELS = [
    ("gemini-3.1-flash-lite", "benchmark_results_gemini_full.json", "benchmark_results_gemini_review.json", "Gemini 3.1 Flash-Lite"),
    ("openai/gpt-oss-120b",   "benchmark_results_groq_full.json",   "benchmark_results_groq_review.json",   "gpt-oss-120b"),
    ("openai/gpt-oss-20b",    "benchmark_results_groq_full.json",   "benchmark_results_groq_review.json",   "gpt-oss-20b"),
]


def scores(fname: str, model_id: str) -> dict[str, dict]:
    data = json.loads((ROOT / fname).read_text(encoding="utf-8"))
    entry = next(m for m in data["models"] if m["model_id"] == model_id)
    return {s["id"]: s for s in entry["scores"]}


def main() -> None:
    md: list[str] = []
    w = md.append
    w("# ความแปรปรวนระหว่างรอบ (run-to-run stability)\n")
    w("> สร้างโดย `python scripts/analyze_stability.py` — อย่าแก้มือ")
    w("> รอบ 1 = ชุด full (2026-10-01/02), รอบ 2 = รันซ้ำ 154 เคสที่ใช้ตรวจโดยคน (2026-10-17) — prompt และการตั้งค่าเหมือนเดิม")
    w("> นับเฉพาะเคสที่ทั้งสองรอบมีคำตอบ\n")
    w("| Model | n | เฉลี่ยรอบ 1 | เฉลี่ยรอบ 2 | ผลต่าง | คะแนนเท่าเดิม | ผ่าน/ไม่ผ่าน กลับข้าง |")
    w("|---|---:|---:|---:|---:|---:|---:|")
    flips_by_model = []
    for model_id, f1, f2, label in MODELS:
        a, b = scores(f1, model_id), scores(f2, model_id)
        ids = sorted(set(a) & set(b))
        m1 = sum(a[i]["final_score"] for i in ids) / len(ids)
        m2 = sum(b[i]["final_score"] for i in ids) / len(ids)
        same = sum(a[i]["final_score"] == b[i]["final_score"] for i in ids)
        flips = [i for i in ids if a[i]["passed"] != b[i]["passed"]]
        flips_by_model.append((label, flips, a, b))
        w(f"| {label} | {len(ids)} | {m1:.2f} | {m2:.2f} | {m2 - m1:+.2f} | {same} ({same / len(ids):.0%}) "
          f"| {len(flips)} ({len(flips) / len(ids):.0%}) |")
    w("")
    w("## เคสที่ผ่าน/ไม่ผ่าน กลับข้าง\n")
    for label, flips, a, b in flips_by_model:
        cells = ", ".join(f"`{i}` {a[i]['final_score']:.1f}→{b[i]['final_score']:.1f}" for i in flips) or "–"
        w(f"- **{label}**: {cells}")
    w("")
    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
