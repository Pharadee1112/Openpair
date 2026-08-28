"""
benchmark.checkpoint — resume support สำหรับ benchmark ที่รันค้าง
=====================================================================
เก็บผลของแต่ละ (model_id, case_id) ที่ทำสำเร็จแล้วลงไฟล์ JSONL
(1 บรรทัด = 1 เคส) เพื่อให้รันต่อได้โดยไม่ต้องยิง API ซ้ำ เมื่อ process
ถูก kill กลางคัน (เช่น quota หมด) — โหลดไฟล์แบบ tolerant คือข้าม
บรรทัดที่เขียนไม่สมบูรณ์ (ถูก kill ระหว่างเขียนบรรทัดสุดท้ายพอดี)
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .dataset import ThaiTestCase
from .scorer import ResponseScore


def prompt_hash(case: ThaiTestCase) -> str:
    """sha256 ของ case.prompt ตัดเหลือ 12 ตัวอักษรแรก ใช้ตรวจว่า prompt เปลี่ยนไปหรือไม่"""
    return hashlib.sha256(case.prompt.encode("utf-8")).hexdigest()[:12]


class CaseCheckpoint:
    """
    อ่าน/เขียน checkpoint file แบบ JSONL คีย์ = (model_id, case_id)

    Usage:
        ckpt = CaseCheckpoint("results.checkpoint.jsonl")
        if ckpt.has("gemini-2.5-flash", case):
            score = ckpt.get("gemini-2.5-flash", case)
        else:
            ...
            ckpt.append(model_id=..., model_name=..., provider=..., case=case, score=score)
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._entries: dict[tuple[str, str], dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return

        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    # บรรทัดเสีย (เช่นโดน kill ตอนเขียน) — ข้ามไป
                    continue

                if "model_id" not in entry or "case_id" not in entry:
                    continue

                key = (entry["model_id"], entry["case_id"])
                self._entries[key] = entry

    def has(self, model_id: str, case: ThaiTestCase) -> bool:
        return (model_id, case.id) in self._entries

    def get(self, model_id: str, case: ThaiTestCase) -> Optional[ResponseScore]:
        entry = self._entries.get((model_id, case.id))
        if entry is None:
            return None

        if entry.get("prompt_hash") != prompt_hash(case):
            # prompt เปลี่ยนไปจากตอนที่บันทึกไว้ — ผลเก่าใช้ไม่ได้แล้ว
            return None

        return ResponseScore(
            test_case_id     = entry["case_id"],
            category         = entry["category"],
            difficulty       = entry["difficulty"],
            keyword_score    = entry["keyword_score"],
            thai_ratio       = entry["thai_ratio"],
            length_ok        = entry["length_ok"],
            final_score      = entry["final_score"],
            passed           = entry["passed"],
            response_preview = entry["preview"],
        )

    def append(
        self,
        *,
        model_id:   str,
        model_name: str,
        provider:   str,
        case:       ThaiTestCase,
        score:      ResponseScore,
    ) -> None:
        entry = {
            "model_id":      model_id,
            "model_name":    model_name,
            "provider":      provider,
            "case_id":       case.id,
            "prompt_hash":   prompt_hash(case),
            "category":      score.category,
            "difficulty":    score.difficulty,
            "keyword_score": score.keyword_score,
            "thai_ratio":    score.thai_ratio,
            "length_ok":     score.length_ok,
            "final_score":   score.final_score,
            "passed":        score.passed,
            "preview":       score.response_preview,
            "ts":            datetime.now().isoformat(),
        }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()

        self._entries[(model_id, case.id)] = entry

    def done_count(self, model_id: str) -> int:
        return sum(1 for (mid, _cid) in self._entries if mid == model_id)
