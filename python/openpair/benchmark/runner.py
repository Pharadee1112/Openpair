"""
benchmark.runner — รัน benchmark กับ model จริงๆ
==================================================
ส่ง ThaiTestCase แต่ละชุดไปให้ model ตอบ แล้วเก็บผลลัพธ์
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..caller import make_call
from ..config import ApiKeys
from .dataset import ThaiTestCase, THAI_TEST_CASES
from .scorer import score_response, ResponseScore, ModelBenchmarkResult


def run_model_benchmark(
    *,
    model_id:   str,
    model_name: str,
    provider:   str,
    api_key:    str,
    cases:      Optional[list[ThaiTestCase]] = None,
    max_tokens: int = 512,
    verbose:    bool = True,
) -> ModelBenchmarkResult:
    """
    รัน benchmark ทุก test case กับ model ที่ระบุ

    Args:
        model_id:   model ID เช่น "gemini-2.5-flash"
        model_name: ชื่อสวยงาม เช่น "Gemini 2.5 Flash"
        provider:   "google" | "openai" | "anthropic"
        api_key:    API key สำหรับ provider นั้น
        cases:      ชุดข้อสอบ (ถ้าไม่ระบุจะใช้ทั้งหมด)
        max_tokens: จำนวน token สูงสุดของคำตอบ
        verbose:    แสดงผลระหว่างรันไหม
    """
    test_cases = cases or THAI_TEST_CASES
    scores: list[ResponseScore] = []

    if verbose:
        print(f"\n{'═'*60}")
        print(f"  🧪 กำลังทดสอบ: {model_name} ({model_id})")
        print(f"  📋 จำนวน test cases: {len(test_cases)}")
        print(f"{'═'*60}")

    for i, case in enumerate(test_cases, 1):
        if verbose:
            print(f"  [{i:02d}/{len(test_cases)}] {case.id} ({case.category}/{case.difficulty})", end=" ", flush=True)

        try:
            text, in_tok, out_tok, latency_ms = make_call(
                provider   = provider,
                model_id   = model_id,
                prompt     = case.prompt,
                api_key    = api_key,
                max_tokens = max_tokens,
            )

            score = score_response(text, case)
            scores.append(score)

            if verbose:
                status = "✅" if score.passed else "❌"
                print(f"{status} score={score.final_score:.1f} kw={score.keyword_score:.0%} th={score.thai_ratio:.0%} ({latency_ms:.0f}ms)")

        except Exception as e:
            if verbose:
                print(f"💥 ERROR: {e}")
            # เพิ่ม score 0 เมื่อ error ไม่ให้หยุด benchmark
            scores.append(ResponseScore(
                test_case_id    = case.id,
                category        = case.category,
                difficulty      = case.difficulty,
                keyword_score   = 0.0,
                thai_ratio      = 0.0,
                length_ok       = False,
                final_score     = 0.0,
                passed          = False,
                response_preview= f"ERROR: {str(e)[:60]}",
            ))

        # หน่วงเล็กน้อยเพื่อไม่ให้ชน rate limit
        time.sleep(0.5)

    result = ModelBenchmarkResult(
        model_id   = model_id,
        model_name = model_name,
        provider   = provider,
        scores     = scores,
    )

    if verbose:
        print(f"\n  📊 ผลรวม: avg={result.avg_final_score}/10 | pass={result.pass_rate:.0%} | thai={result.avg_thai_ratio:.0%}")

    return result


def run_full_benchmark(
    models: list[dict],
    api_keys: ApiKeys,
    cases: Optional[list[ThaiTestCase]] = None,
    output_path: Optional[str] = None,
    verbose: bool = True,
) -> list[ModelBenchmarkResult]:
    """
    รัน benchmark กับหลาย model พร้อมกัน

    Args:
        models: list of dicts เช่น:
            [{"model_id": "gemini-2.5-flash", "model_name": "Gemini 2.5 Flash", "provider": "google"}]
        api_keys: ApiKeys object ที่มี key สำหรับ provider ที่ต้องการ
        cases:   ชุดข้อสอบ (ถ้าไม่ระบุใช้ทั้งหมด)
        output_path: path สำหรับบันทึก JSON ผลลัพธ์
        verbose: แสดงผลระหว่างรันไหม

    Returns:
        list ของ ModelBenchmarkResult เรียงตาม avg_final_score (สูง→ต่ำ)
    """
    results: list[ModelBenchmarkResult] = []

    for m in models:
        provider = m["provider"]
        key = api_keys.for_provider(provider)
        if not key:
            print(f"⚠️  ไม่มี API key สำหรับ {provider} — ข้าม {m['model_id']}")
            continue

        result = run_model_benchmark(
            model_id   = m["model_id"],
            model_name = m["model_name"],
            provider   = provider,
            api_key    = key,
            cases      = cases,
            verbose    = verbose,
        )
        results.append(result)

    # เรียงตาม score สูงสุด
    results.sort(key=lambda r: r.avg_final_score, reverse=True)

    # บันทึก JSON ถ้าระบุ path
    if output_path:
        _save_results(results, output_path)
        if verbose:
            print(f"\n💾 บันทึกผลลัพธ์ที่: {output_path}")

    return results


def _save_results(results: list[ModelBenchmarkResult], path: str) -> None:
    """บันทึกผลลัพธ์เป็น JSON"""
    data = {
        "run_at": datetime.now().isoformat(),
        "models": [
            {
                "model_id":             r.model_id,
                "model_name":           r.model_name,
                "provider":             r.provider,
                "avg_final_score":      r.avg_final_score,
                "avg_keyword_score":    r.avg_keyword_score,
                "avg_thai_ratio":       r.avg_thai_ratio,
                "pass_rate":            r.pass_rate,
                "suggested_thai_score": r.suggested_thai_score,
                "scores": [
                    {
                        "id":            s.test_case_id,
                        "category":      s.category,
                        "difficulty":    s.difficulty,
                        "final_score":   s.final_score,
                        "keyword_score": s.keyword_score,
                        "thai_ratio":    s.thai_ratio,
                        "passed":        s.passed,
                        "preview":       s.response_preview,
                    }
                    for s in r.scores
                ],
            }
            for r in results
        ],
    }
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
