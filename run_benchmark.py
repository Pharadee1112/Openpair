"""
run_benchmark.py — รัน Thai Benchmark กับ Gemini models
=========================================================
Usage:
    python run_benchmark.py
    python run_benchmark.py --models gemini-2.5-flash,gemini-2.5-flash-lite
    python run_benchmark.py --category qa
    python run_benchmark.py --output results.json
"""

import argparse
import sys
from pathlib import Path

# เพิ่ม python/ ใน path เพื่อ import openpair
sys.path.insert(0, str(Path(__file__).parent / "python"))

from openpair import ApiKeys
from openpair.benchmark import (
    run_full_benchmark,
    print_summary,
    print_detail,
    THAI_TEST_CASES,
)
from openpair.benchmark.dataset import get_cases_by_category


# ── Models ที่จะทดสอบ (เปลี่ยนได้) ──────────────────────────────────────────
DEFAULT_MODELS = [
    {
        "model_id":   "gemini-2.5-flash",
        "model_name": "Gemini 2.5 Flash",
        "provider":   "google",
    },
    {
        "model_id":   "gemini-2.5-flash-lite",
        "model_name": "Gemini 2.5 Flash Lite",
        "provider":   "google",
    },
]


def parse_args():
    parser = argparse.ArgumentParser(description="OpenPair — Thai Language Benchmark")
    parser.add_argument(
        "--models", type=str, default=None,
        help="model IDs คั่นด้วย comma เช่น gemini-2.5-flash,gemini-2.5-pro",
    )
    parser.add_argument(
        "--category", type=str, default=None,
        help="รัน test เฉพาะหมวด: qa / translation / summarization / classification / code_thai / creative",
    )
    parser.add_argument(
        "--output", type=str, default="benchmark_results.json",
        help="path สำหรับบันทึก JSON ผลลัพธ์ (default: benchmark_results.json)",
    )
    parser.add_argument(
        "--detail", action="store_true",
        help="แสดงผลแบบละเอียดแต่ละ test case",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # ── เลือก models ──────────────────────────────────────────────
    if args.models:
        model_ids = [m.strip() for m in args.models.split(",")]
        models = [
            {"model_id": mid, "model_name": mid, "provider": "google"}
            for mid in model_ids
        ]
    else:
        models = DEFAULT_MODELS

    # ── เลือก test cases ──────────────────────────────────────────
    if args.category:
        cases = get_cases_by_category(args.category)
        if not cases:
            print(f"❌ ไม่พบ category '{args.category}'")
            print(f"   ตัวเลือก: qa, translation, summarization, classification, code_thai, creative")
            sys.exit(1)
        print(f"📂 รัน category: {args.category} ({len(cases)} cases)")
    else:
        cases = THAI_TEST_CASES
        print(f"📋 รัน benchmark ทั้งหมด ({len(cases)} cases × {len(models)} models)")

    # ── รัน benchmark ─────────────────────────────────────────────
    api_keys = ApiKeys()

    if not api_keys.available_providers():
        print("❌ ไม่พบ API key — ใส่ key ใน .env หรือ environment variable")
        sys.exit(1)

    print(f"🔑 ใช้ provider: {api_keys.available_providers()}")

    results = run_full_benchmark(
        models      = models,
        api_keys    = api_keys,
        cases       = cases,
        output_path = args.output,
        verbose     = True,
    )

    # ── แสดงผล ────────────────────────────────────────────────────
    print_summary(results)

    if args.detail:
        for result in results:
            print_detail(result)

    print(f"✅ เสร็จสิ้น! ผลลัพธ์บันทึกที่ {args.output}")


if __name__ == "__main__":
    main()
