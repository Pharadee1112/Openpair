"""
review_simple.py — แบบฟอร์มตรวจโดยคนแบบง่าย (1 บรรทัด = 1 คำตอบเต็ม)
=====================================================================
  python scripts/review_simple.py make    สร้าง paper/review_simple.csv
  python scripts/review_simple.py merge   รวมผลตรวจ → paper/human_review.csv (ใช้วิเคราะห์ใน paper)

คำตอบมาจากการรันซ้ำเฉพาะ 154 เคสใน paper/slang_review.csv (2026-10-17) ซึ่งเก็บคำตอบเต็ม:
  benchmark_results_gemini_review.json, benchmark_results_groq_review.json
(ผลชุด full เดิมเก็บแค่ 80 ตัวอักษรแรก ตรวจความหมายไม่ได้)

ตรวจแบบ blind: ไม่บอกชื่อ model / คะแนนจากเครื่อง และสลับลำดับคำตอบในแต่ละข้อ (seed คงที่)
คอลัมน์ "รหัส" ใช้จับคู่กลับ — ผู้ตรวจไม่ต้องแก้
"""

from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYS = ROOT / "paper" / "slang_review.csv"      # รายการเคส + เฉลยที่ยืนยันแล้ว
SIMPLE = ROOT / "paper" / "review_simple.csv"   # ผู้ตรวจกรอกไฟล์นี้
OUT = ROOT / "paper" / "human_review.csv"       # ผลรวม: เคส × model × คำตัดสิน × คะแนนเครื่อง

MODELS = [
    ("gemini-3.1-flash-lite", "benchmark_results_gemini_review.json", "Gemini 3.1 Flash-Lite"),
    ("openai/gpt-oss-120b",   "benchmark_results_groq_review.json",   "gpt-oss-120b"),
    ("openai/gpt-oss-20b",    "benchmark_results_groq_review.json",   "gpt-oss-20b"),
]
CATEGORY_ORDER = ["qa", "translation", "classification", "creative"]  # qa ก่อน — สำคัญที่สุด
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
    """model_id -> case_id -> score row (มี response เต็ม)"""
    out: dict[str, dict[str, dict]] = {}
    for model_id, fname, _ in MODELS:
        data = json.loads((ROOT / fname).read_text(encoding="utf-8"))
        entry = next(m for m in data["models"] if m["model_id"] == model_id)
        out[model_id] = {s["id"]: s for s in entry["scores"]}
    return out


def make() -> None:
    if SIMPLE.exists() and any(r[VERDICT].strip() for r in read_csv(SIMPLE)):
        sys.exit(f"{SIMPLE} มีผลตรวจอยู่แล้ว — merge ก่อน หรือลบไฟล์เองถ้าต้องการสร้างใหม่")
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
    print(f"wrote {SIMPLE} ({n} ข้อ, {len(out)} คำตอบ)")
    if missing:
        print(f"ไม่มีคำตอบ {len(missing)} รายการ (ไม่ได้ใส่ในฟอร์ม): {', '.join(missing)}")


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
    print(f"wrote {OUT} ({done}/{len(rows)} คำตอบตรวจแล้ว)")


if __name__ == "__main__":
    {"make": make, "merge": merge}[sys.argv[1] if len(sys.argv) > 1 else "make"]()
