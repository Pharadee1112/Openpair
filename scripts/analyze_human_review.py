"""
analyze_human_review.py — เทียบผลตรวจโดยคนกับคะแนนจากเครื่อง (ชุด full เดิม)
==========================================================================
อ่าน paper/review_verdicts_old.tsv (คนตรวจ 462 คำตอบ แบบ blind จากคำตอบ 80 ตัวอักษรแรก)
+ คะแนนเครื่องจาก benchmark_results_*_full.json → paper/HUMAN_REVIEW.md

  python scripts/analyze_human_review.py
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERDICTS = ROOT / "paper" / "review_verdicts_old.tsv"
OUT = ROOT / "paper" / "HUMAN_REVIEW.md"

# ลำดับต้องตรงกับเลขหลัง | ในคอลัมน์ code ของ review_verdicts_old.tsv
MODELS = [
    ("gemini-3.1-flash-lite", "benchmark_results_gemini_full.json", "Gemini 3.1 Flash-Lite"),
    ("openai/gpt-oss-120b",   "benchmark_results_groq_full.json",   "gpt-oss-120b"),
    ("openai/gpt-oss-20b",    "benchmark_results_groq_full.json",   "gpt-oss-20b"),
]
CATEGORIES = ["qa", "translation", "classification", "creative"]


def load_machine() -> list[dict[str, dict]]:
    out = []
    for model_id, fname, _ in MODELS:
        data = json.loads((ROOT / fname).read_text(encoding="utf-8"))
        entry = next(m for m in data["models"] if m["model_id"] == model_id)
        out.append({s["id"]: s for s in entry["scores"]})
    return out


def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({a / b:.0%})" if b else "–"


def main() -> None:
    machine = load_machine()
    rows = []
    with open(VERDICTS, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            case_id, idx = r["code"].split("|")
            m = machine[int(idx)][case_id]
            rows.append({"case": case_id, "cat": m["category"], "model": int(idx),
                         "human": r["verdict"], "passed": m["passed"], "score": m["final_score"],
                         "note": r["note"]})

    md: list[str] = []
    w = md.append
    w("# ผลตรวจโดยคน เทียบกับคะแนนจากเครื่อง\n")
    w("> สร้างโดย `python scripts/analyze_human_review.py` — อย่าแก้มือ")
    w(f"> ผู้ตรวจคนไทย 1 คน ตรวจแบบ blind {len(rows)} คำตอบ (154 เคส × 3 model) จากคำตอบ 80 ตัวอักษรแรกของชุด full")
    w("> `?` = คำตอบถูกตัดก่อนตัดสินได้ — ไม่นับในอัตราถูก/ผิด\n")

    w("## 1. ถูกจริงกี่ข้อ (เฉพาะที่ตัดสินได้)\n")
    w("| Model | ถูก (Y) | ผิด (N) | ตัดสินไม่ได้ (?) | อัตราถูก |")
    w("|---|---:|---:|---:|---:|")
    for i, (_, _, label) in enumerate(MODELS):
        c = Counter(r["human"] for r in rows if r["model"] == i)
        w(f"| {label} | {c['Y']} | {c['N']} | {c['?']} | {pct(c['Y'], c['Y'] + c['N'])} |")
    w("")

    w("## 2. อัตราถูก แยกหมวด\n")
    w("| หมวด | " + " | ".join(l for _, _, l in MODELS) + " |")
    w("|---|" + "---:|" * len(MODELS))
    for cat in CATEGORIES:
        cells = []
        for i in range(len(MODELS)):
            c = Counter(r["human"] for r in rows if r["model"] == i and r["cat"] == cat)
            cells.append(f"{pct(c['Y'], c['Y'] + c['N'])} (? {c['?']})")
        w(f"| {cat} | " + " | ".join(cells) + " |")
    w("")

    judged = [r for r in rows if r["human"] in ("Y", "N")]
    w("## 3. เครื่องให้คะแนนตรงกับคนไหม (เฉพาะที่ตัดสินได้)\n")
    w("| Model | ตรงกัน | เครื่องให้ผ่าน แต่คนบอกผิด | เครื่องให้ไม่ผ่าน แต่คนบอกถูก |")
    w("|---|---:|---:|---:|")
    for i, (_, _, label) in enumerate(MODELS):
        j = [r for r in judged if r["model"] == i]
        agree = sum((r["human"] == "Y") == r["passed"] for r in j)
        fp = sum(r["passed"] and r["human"] == "N" for r in j)
        fn = sum(not r["passed"] and r["human"] == "Y" for r in j)
        w(f"| {label} | {pct(agree, len(j))} | {fp} | {fn} |")
    agree = sum((r["human"] == "Y") == r["passed"] for r in judged)
    fp_all = [r for r in judged if r["passed"] and r["human"] == "N"]
    w(f"| **รวม** | {pct(agree, len(judged))} | {len(fp_all)} | "
      f"{sum(not r['passed'] and r['human'] == 'Y' for r in judged)} |")
    w("")
    ny = [r["score"] for r in judged if r["human"] == "N"]
    yy = [r["score"] for r in judged if r["human"] == "Y"]
    w(f"คะแนนเครื่องเฉลี่ยของคำตอบที่คนบอก **ผิด** = {sum(ny) / len(ny):.2f} / 10, "
      f"ที่คนบอก **ถูก** = {sum(yy) / len(yy):.2f} / 10\n")

    w("## 4. ตัวอย่าง: เครื่องให้ผ่าน แต่คนบอกผิด\n")
    w("| เคส | Model | คะแนนเครื่อง | หมายเหตุผู้ตรวจ |")
    w("|---|---|---:|---|")
    for r in sorted(fp_all, key=lambda r: -r["score"]):
        w(f"| `{r['case']}` | {MODELS[r['model']][2]} | {r['score']:.1f} | {r['note'] or '–'} |")
    w("")

    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
