"""
review_simple.py — แบบฟอร์มตรวจแบบง่าย (1 บรรทัด = 1 คำตอบ) ↔ paper/slang_review.csv
=====================================================================================
  python scripts/review_simple.py make    สร้าง paper/review_simple.csv จาก slang_review.csv
  python scripts/review_simple.py merge   เอาช่อง "ถูกไหม" ที่กรอกแล้วกลับเข้า slang_review.csv

ตรวจแบบ blind: ไม่บอกชื่อ model และสลับลำดับคำตอบในแต่ละข้อ (seed คงที่) เพื่อไม่ให้ผู้ตรวจลำเอียง
คอลัมน์ "รหัส" ใช้จับคู่กลับ — ผู้ตรวจไม่ต้องแก้
"""

from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FULL = ROOT / "paper" / "slang_review.csv"
SIMPLE = ROOT / "paper" / "review_simple.csv"

MODELS = ["Gemini 3.1 Flash-Lite", "gpt-oss-120b", "gpt-oss-20b"]
CATEGORY_ORDER = ["qa", "translation", "classification", "creative"]  # qa ก่อน — สำคัญที่สุด
VERDICT = "ถูกไหม (Y/N/?)"
NOTE = "หมายเหตุ"
SEED = 20261017


def answer_col(m: str) -> str:
    return f"{m} (score / คำตอบ 80 ตัวแรก)"


def verdict_col(m: str) -> str:
    return f"{m} ถูกไหม (Y/N/?)"


def read(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def make() -> None:
    _, rows = read(FULL)
    rows.sort(key=lambda x: CATEGORY_ORDER.index(x["category"]))
    rng = random.Random(SEED)
    out, n = [], 0
    for x in rows:
        n += 1
        order = MODELS[:]
        rng.shuffle(order)
        for m in order:
            answer = x[answer_col(m)].split(" | ", 1)[-1]  # ตัดคะแนนออก ไม่ให้เห็นว่าเครื่องให้เท่าไร
            out.append({
                "ข้อ": n,
                "หมวด": x["category"],
                "คำถาม": x["prompt"],
                "เฉลย (คำที่ควรมี)": x["expected_keywords"],
                "คำตอบ": answer,
                VERDICT: x[verdict_col(m)],
                NOTE: "",
                "รหัส (ห้ามแก้)": f"{x['case_id']}|{MODELS.index(m)}",
            })
    if SIMPLE.exists():
        print(f"{SIMPLE} มีอยู่แล้ว — ไม่เขียนทับ (merge ก่อน หรือลบไฟล์เองถ้าต้องการสร้างใหม่)")
        return
    with open(SIMPLE, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f"wrote {SIMPLE} ({n} ข้อ, {len(out)} คำตอบ)")


def merge() -> None:
    header, rows = read(FULL)
    by_id = {x["case_id"]: x for x in rows}
    _, simple = read(SIMPLE)
    filled = 0
    for s in simple:
        v = s[VERDICT].strip().upper()
        if not v:
            continue
        case_id, idx = s["รหัส (ห้ามแก้)"].split("|")
        m = MODELS[int(idx)]
        row = by_id[case_id]
        row[verdict_col(m)] = v
        if s[NOTE].strip():
            note = f"{m}: {s[NOTE].strip()}"
            if note not in row[NOTE]:
                row[NOTE] = f"{row[NOTE]}; {note}" if row[NOTE] else note
        filled += 1
    with open(FULL, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)
    print(f"merged {filled}/{len(simple)} คำตอบ เข้า {FULL}")


if __name__ == "__main__":
    {"make": make, "merge": merge}[sys.argv[1] if len(sys.argv) > 1 else "make"]()
