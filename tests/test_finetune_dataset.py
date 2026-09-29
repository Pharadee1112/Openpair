"""
Unit tests สำหรับ finetune/check_dataset.py — ตรวจรูปแบบ training data และการรั่วของข้อสอบ benchmark
"""

import importlib.util
import json
from pathlib import Path

import pytest

from openpair.benchmark.dataset import get_suite

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check_dataset", ROOT / "finetune" / "check_dataset.py")
check_dataset = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_dataset)


def _record(user: str, rid: str = "train_t_001", assistant: str = "คำตอบ") -> dict:
    return {
        "id": rid, "category": "qa", "source": "test",
        "messages": [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}],
    }


def _write(tmp_path: Path, records: list[dict]) -> Path:
    p = tmp_path / "data.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
    return p


@pytest.fixture(scope="module")
def bench_index():
    return check_dataset.build_benchmark_index()


def test_seed_dataset_passes():
    assert check_dataset.check_files([ROOT / "finetune" / "data" / "train_seed.jsonl"]) == 0


def test_exact_benchmark_prompt_is_leak(bench_index):
    case = get_suite("full")[0]
    assert "ซ้ำเคส benchmark" in check_dataset.find_leak(case.prompt, *bench_index)


def test_benchmark_prompt_with_prefix_is_leak(bench_index):
    case = get_suite("full")[300]
    leak = check_dataset.find_leak("ช่วยตอบหน่อยนะ " + case.prompt, *bench_index)
    assert leak is not None and case.id in leak


def test_unrelated_prompt_is_not_leak(bench_index):
    assert check_dataset.find_leak("แมวชอบนอนตอนบ่ายเพราะอากาศร้อน จริงไหม", *bench_index) is None


def test_missing_assistant_fails():
    rec = _record("สวัสดี")
    rec["messages"] = rec["messages"][:1]
    assert "message สุดท้ายต้องเป็น 'assistant'" in check_dataset.validate_record(rec)


def test_invalid_category_and_id_prefix():
    rec = _record("สวัสดี", rid="x_1")
    rec["category"] = "poetry"
    errors = check_dataset.validate_record(rec)
    assert any("train_" in e for e in errors)
    assert any("poetry" in e for e in errors)


def test_zero_width_char_fails():
    errors = check_dataset.validate_record(_record("สวัส​ดี"))
    assert any("zero-width" in e for e in errors)


def test_duplicate_id_fails(tmp_path):
    p = _write(tmp_path, [_record("คำถามหนึ่งเรื่องแมว"), _record("คำถามสองเรื่องหมา")])
    assert check_dataset.check_files([p]) == 1
