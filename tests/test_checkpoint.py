"""
Unit tests สำหรับ CaseCheckpoint (resume support)
ไม่ต้องการ API key
"""

from __future__ import annotations

import json

import pytest

from openpair.benchmark.checkpoint import CaseCheckpoint, prompt_hash
from openpair.benchmark.dataset import ThaiTestCase
from openpair.benchmark.scorer import score_response


def _case(id_="c1", prompt="เมืองหลวงของไทยคืออะไร?"):
    return ThaiTestCase(
        id=id_,
        category="qa",
        difficulty="easy",
        prompt=prompt,
        expected_keywords=["กรุงเทพ"],
        keyword_threshold=0.5,
        min_thai_ratio=0.2,
        min_length=5,
    )


class TestCaseCheckpoint:
    def test_append_then_reload_returns_matching_score(self, tmp_path):
        path = tmp_path / "ckpt.jsonl"
        case = _case()
        score = score_response("กรุงเทพมหานคร", case)

        ckpt = CaseCheckpoint(path)
        ckpt.append(model_id="m1", model_name="Model 1", provider="google", case=case, score=score)

        # reload from disk
        ckpt2 = CaseCheckpoint(path)
        assert ckpt2.has("m1", case)
        loaded = ckpt2.get("m1", case)
        assert loaded is not None
        assert loaded.final_score == score.final_score
        assert loaded.test_case_id == case.id
        assert loaded.passed == score.passed

    def test_prompt_changed_returns_none(self, tmp_path):
        path = tmp_path / "ckpt.jsonl"
        case = _case(prompt="เมืองหลวงของไทยคืออะไร?")
        score = score_response("กรุงเทพมหานคร", case)

        ckpt = CaseCheckpoint(path)
        ckpt.append(model_id="m1", model_name="Model 1", provider="google", case=case, score=score)

        changed_case = _case(prompt="เมืองหลวงของไทยคือที่ไหน? (คำถามใหม่)")
        ckpt2 = CaseCheckpoint(path)
        assert ckpt2.get("m1", changed_case) is None

    def test_different_model_same_case_has_false(self, tmp_path):
        path = tmp_path / "ckpt.jsonl"
        case = _case()
        score = score_response("กรุงเทพมหานคร", case)

        ckpt = CaseCheckpoint(path)
        ckpt.append(model_id="m1", model_name="Model 1", provider="google", case=case, score=score)

        assert ckpt.has("m1", case)
        assert not ckpt.has("m2", case)
        assert ckpt.get("m2", case) is None

    def test_tolerant_of_corrupt_trailing_line(self, tmp_path):
        path = tmp_path / "ckpt.jsonl"
        case = _case()
        score = score_response("กรุงเทพมหานคร", case)

        good_entry = {
            "model_id": "m1", "model_name": "Model 1", "provider": "google",
            "case_id": case.id, "prompt_hash": prompt_hash(case),
            "category": score.category, "difficulty": score.difficulty,
            "keyword_score": score.keyword_score, "thai_ratio": score.thai_ratio,
            "length_ok": score.length_ok, "final_score": score.final_score,
            "passed": score.passed, "preview": score.response_preview,
            "ts": "2026-01-01T00:00:00",
        }
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(good_entry, ensure_ascii=False) + "\n")
            f.write('{"model_id": "m1", "case_id": "broken", incomplete json\n')  # corrupt line

        ckpt = CaseCheckpoint(path)
        assert ckpt.has("m1", case)
        assert ckpt.get("m1", case) is not None
        assert not ckpt.has("m1", _case(id_="broken"))

    def test_done_count(self, tmp_path):
        path = tmp_path / "ckpt.jsonl"
        ckpt = CaseCheckpoint(path)
        c1, c2 = _case(id_="c1"), _case(id_="c2")
        s1 = score_response("กรุงเทพมหานคร", c1)
        s2 = score_response("กรุงเทพมหานคร", c2)

        ckpt.append(model_id="m1", model_name="M1", provider="google", case=c1, score=s1)
        ckpt.append(model_id="m1", model_name="M1", provider="google", case=c2, score=s2)
        ckpt.append(model_id="m2", model_name="M2", provider="google", case=c1, score=s1)

        assert ckpt.done_count("m1") == 2
        assert ckpt.done_count("m2") == 1
        assert ckpt.done_count("m3") == 0
