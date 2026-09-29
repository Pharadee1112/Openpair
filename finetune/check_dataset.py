"""
ตรวจ training dataset สำหรับ fine-tuning (finetune/data/*.jsonl)

1. รูปแบบถูกต้อง — field ครบ, category ถูก, messages จบด้วย assistant, id ไม่ซ้ำ
2. ไม่รั่วข้อสอบ — prompt ต้องไม่ซ้ำ/คล้ายเคสใน benchmark ชุด full (character n-gram overlap)

รัน:
    python finetune/check_dataset.py                        # ทุกไฟล์ใน finetune/data/
    python finetune/check_dataset.py finetune/data/x.jsonl  # เฉพาะไฟล์ที่ระบุ
exit code 0 = ผ่าน, 1 = มีปัญหา
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from openpair.benchmark.dataset import CATEGORIES, get_suite  # noqa: E402

DATA_DIR = ROOT / "finetune" / "data"

NGRAM = 5
# สัดส่วน n-gram ของ prompt ที่ไปซ้ำกับเคส benchmark เคสเดียว — เกินนี้ถือว่ารั่ว
OVERLAP_THRESHOLD = 0.5
VALID_ROLES = {"system", "user", "assistant"}
INVISIBLE_CHARS = re.compile("[​‌‍﻿]")


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def ngrams(text: str) -> set[str]:
    t = normalize(text)
    if len(t) < NGRAM:
        return {t} if t else set()
    return {t[i:i + NGRAM] for i in range(len(t) - NGRAM + 1)}


def build_benchmark_index() -> tuple[dict[str, set[str]], dict[str, str]]:
    """n-gram → set ของ case id ที่มี n-gram นั้น, และ prompt ที่ normalize แล้ว → case id"""
    index: dict[str, set[str]] = defaultdict(set)
    exact: dict[str, str] = {}
    for case in get_suite("full"):
        exact[normalize(case.prompt)] = case.id
        for g in ngrams(case.prompt):
            index[g].add(case.id)
    return index, exact


def validate_record(rec: dict) -> list[str]:
    errors = []
    for field in ("id", "category", "source", "messages"):
        if field not in rec:
            errors.append(f"ขาด field '{field}'")
    if errors:
        return errors

    if not str(rec["id"]).startswith("train_"):
        errors.append("id ต้องขึ้นต้นด้วย 'train_'")
    if rec["category"] not in CATEGORIES:
        errors.append(f"category '{rec['category']}' ไม่อยู่ใน {CATEGORIES}")

    msgs = rec["messages"]
    if not isinstance(msgs, list) or not msgs:
        return errors + ["messages ต้องเป็น list ที่ไม่ว่าง"]
    for i, m in enumerate(msgs):
        if m.get("role") not in VALID_ROLES:
            errors.append(f"messages[{i}] role '{m.get('role')}' ไม่ถูกต้อง")
        content = m.get("content")
        if not isinstance(content, str) or not content.strip():
            errors.append(f"messages[{i}] content ว่าง")
        elif INVISIBLE_CHARS.search(content):
            errors.append(f"messages[{i}] มีอักขระล่องหน (zero-width)")
    if not any(m.get("role") == "user" for m in msgs):
        errors.append("ไม่มี message role 'user'")
    if msgs[-1].get("role") != "assistant":
        errors.append("message สุดท้ายต้องเป็น 'assistant'")
    return errors


def find_leak(prompt: str, index, exact) -> str | None:
    if normalize(prompt) in exact:
        return f"prompt ซ้ำเคส benchmark '{exact[normalize(prompt)]}' ทุกตัวอักษร"
    grams = ngrams(prompt)
    if not grams:
        return None
    hits: dict[str, int] = defaultdict(int)
    for g in grams:
        for case_id in index.get(g, ()):
            hits[case_id] += 1
    if not hits:
        return None
    case_id, count = max(hits.items(), key=lambda kv: kv[1])
    ratio = count / len(grams)
    if ratio >= OVERLAP_THRESHOLD:
        return f"prompt คล้ายเคส benchmark '{case_id}' ({ratio:.0%} ของ {NGRAM}-gram ซ้ำ)"
    return None


def check_files(paths: list[Path]) -> int:
    index, exact = build_benchmark_index()
    seen_ids: dict[str, str] = {}
    problems = 0
    counts: dict[str, int] = defaultdict(int)

    for path in paths:
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if not line.strip():
                    continue
                where = f"{path.name}:{lineno}"
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"❌ {where} JSON ไม่ถูกต้อง: {e}")
                    problems += 1
                    continue

                errors = validate_record(rec)
                rid = rec.get("id")
                if rid in seen_ids:
                    errors.append(f"id '{rid}' ซ้ำกับ {seen_ids[rid]}")
                elif rid:
                    seen_ids[rid] = where

                user_text = "\n".join(
                    m.get("content", "") for m in rec.get("messages", [])
                    if isinstance(m, dict) and m.get("role") == "user"
                )
                leak = find_leak(user_text, index, exact) if user_text else None
                if leak:
                    errors.append(f"รั่วข้อสอบ: {leak}")

                for err in errors:
                    print(f"❌ {where} [{rid}] {err}")
                problems += len(errors)
                if not errors:
                    counts[rec["category"]] += 1

    total = sum(counts.values())
    print(f"\nตัวอย่างที่ผ่าน: {total}  " + "  ".join(f"{c}={counts[c]}" for c in CATEGORIES))
    if problems:
        print(f"❌ พบปัญหา {problems} จุด")
        return 1
    print("✅ ผ่านทั้งหมด — ไม่มีเคสรั่วจาก benchmark")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    paths = [Path(p).resolve() for p in sys.argv[1:]] or sorted(DATA_DIR.glob("*.jsonl"))
    if not paths:
        print(f"ไม่พบไฟล์ .jsonl ใน {DATA_DIR}")
        return 1
    return check_files(paths)


if __name__ == "__main__":
    sys.exit(main())
