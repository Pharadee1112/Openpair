"""
run_benchmark.py — รัน Thai Benchmark กับ Gemini models
=========================================================
Usage:
    python run_benchmark.py
    python run_benchmark.py --models gemini-2.5-flash,gemini-2.5-flash-lite
    python run_benchmark.py --category qa
    python run_benchmark.py --suite full          # 600 เคส (100 ต่อหมวด)
    python run_benchmark.py --output results.json
    python run_benchmark.py --models openrouter:meta-llama/llama-3.3-70b-instruct   # OpenRouter ต้องใส่ prefix
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
    SUITES,
    get_suite,
)
from openpair.benchmark.dataset import get_cases_by_category

# Windows console ภาษาไทย (cp874) พิมพ์ emoji ไม่ได้ → บังคับ stdout เป็น UTF-8
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


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


def parse_model_spec(spec: str) -> dict:
    """
    แปลง model spec จาก --models เป็น dict สำหรับ runner
    OpenRouter ใช้ชื่อแบบ org/model เหมือน Groq จึงเดาไม่ได้ ต้องระบุ prefix "openrouter:" เอง
    เช่น openrouter:meta-llama/llama-3.3-70b-instruct
    """
    if spec.startswith("openrouter:"):
        model_id = spec[len("openrouter:"):]
        return {"model_id": model_id, "model_name": model_id, "provider": "openrouter"}
    return {"model_id": spec, "model_name": spec, "provider": infer_provider(spec)}


def infer_provider(model_id: str) -> str:
    """เดา provider จาก model ID — Groq ใช้ชื่อแบบ org/model (เช่น openai/gpt-oss-120b)"""
    if model_id.startswith("gemini-"):
        return "google"
    if model_id.startswith("claude-"):
        return "anthropic"
    if model_id.startswith("gpt-"):
        return "openai"
    if "/" in model_id or model_id.startswith(("llama", "qwen", "mixtral")):
        return "groq"
    return "google"


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
        "--suite", choices=SUITES, default="core",
        help="ชุดข้อสอบ: core = 20 เคสเดิม (default) / full = 600 เคส (100 ต่อหมวด รวมข่าวปัจจุบัน + สแลง)",
    )
    parser.add_argument(
        "--output", type=str, default="benchmark_results.json",
        help="path สำหรับบันทึก JSON ผลลัพธ์ (default: benchmark_results.json)",
    )
    parser.add_argument(
        "--detail", action="store_true",
        help="แสดงผลแบบละเอียดแต่ละ test case",
    )
    parser.add_argument(
        "--fresh", action="store_true",
        help="รันใหม่ทั้งหมด ไม่ resume จาก checkpoint เดิม (default คือ resume)",
    )
    parser.add_argument(
        "--checkpoint", type=str, default=None,
        help="path ของ checkpoint file (default: <output ตัดนามสกุล>.checkpoint.jsonl)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # ── เลือก models ──────────────────────────────────────────────
    if args.models:
        model_ids = [m.strip() for m in args.models.split(",")]
        models = [parse_model_spec(mid) for mid in model_ids]
    else:
        models = DEFAULT_MODELS

    # ── เลือก test cases ──────────────────────────────────────────
    if args.category:
        cases = get_cases_by_category(args.category, suite=args.suite)
        if not cases:
            print(f"❌ ไม่พบ category '{args.category}'")
            print(f"   ตัวเลือก: qa, translation, summarization, classification, code_thai, creative")
            sys.exit(1)
        print(f"📂 รัน category: {args.category} ({len(cases)} cases)")
    else:
        cases = get_suite(args.suite)
        print(f"📋 รัน benchmark ทั้งหมด [{args.suite}] ({len(cases)} cases × {len(models)} models)")

    # ── รัน benchmark ─────────────────────────────────────────────
    api_keys = ApiKeys()

    if not api_keys.available_providers():
        print("❌ ไม่พบ API key — ใส่ key ใน .env หรือ environment variable")
        sys.exit(1)

    print(f"🔑 ใช้ provider: {api_keys.available_providers()}")

    results = run_full_benchmark(
        models          = models,
        api_keys        = api_keys,
        cases           = cases,
        output_path     = args.output,
        verbose         = True,
        resume          = not args.fresh,
        checkpoint_path = args.checkpoint,
    )

    # ── แสดงผล ────────────────────────────────────────────────────
    print_summary(results)

    if args.detail:
        for result in results:
            print_detail(result)

    print(f"✅ เสร็จสิ้น! ผลลัพธ์บันทึกที่ {args.output}")


if __name__ == "__main__":
    main()
