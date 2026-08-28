"""
openpair.benchmark — Thai Language Benchmark System
=====================================================
วัดความสามารถภาษาไทยของ AI model แต่ละตัว

Usage:
    from openpair.benchmark import run_full_benchmark, print_summary
    from openpair import ApiKeys

    results = run_full_benchmark(
        models=[
            {"model_id": "gemini-3.6-flash", "model_name": "Gemini 3.6 Flash", "provider": "google"},
            {"model_id": "gemini-3.1-flash-lite", "model_name": "Gemini 3.1 Flash Lite", "provider": "google"},
        ],
        api_keys=ApiKeys(),
        output_path="benchmark_results.json",
    )
    print_summary(results)
"""

from .runner import run_model_benchmark, run_full_benchmark, QuotaExhausted
from .checkpoint import CaseCheckpoint, prompt_hash
from .reporter import print_summary, print_detail, print_registry_suggestion
from .dataset import THAI_TEST_CASES, ThaiTestCase, CATEGORIES, load_custom_cases
from .scorer import ResponseScore, ModelBenchmarkResult

__all__ = [
    "run_model_benchmark",
    "run_full_benchmark",
    "QuotaExhausted",
    "CaseCheckpoint",
    "prompt_hash",
    "print_summary",
    "print_detail",
    "print_registry_suggestion",
    "THAI_TEST_CASES",
    "ThaiTestCase",
    "CATEGORIES",
    "load_custom_cases",
    "ResponseScore",
    "ModelBenchmarkResult",
]
