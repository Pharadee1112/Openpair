"""
benchmark.runner — รัน benchmark กับ model จริงๆ
==================================================
ส่ง ThaiTestCase แต่ละชุดไปให้ model ตอบ แล้วเก็บผลลัพธ์

Auto-retry:
  เมื่อ API ตอบ 429 (rate limit) หรือ 503 (overloaded/unavailable) จะอ่านค่า retryDelay จาก error
  แล้วรอตามที่ API บอก จากนั้นส่งใหม่อัตโนมัติ (สูงสุด 3 ครั้ง)
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..caller import make_call
from ..config import ApiKeys
from ..errors import is_retryable_error as _is_retryable
from .dataset import ThaiTestCase, THAI_TEST_CASES
from .scorer import score_response, ResponseScore, ModelBenchmarkResult


# ── Retry helpers ─────────────────────────────────────────────────────────────


def _extract_retry_delay(error: Exception, default: float = 60.0) -> float:
    """
    อ่านวินาทีที่ต้องรอจาก error message
    รองรับทั้ง Google ("retryDelay": "44s") และ OpenAI ("Please try again in 20s")
    """
    msg = str(error)

    # Google format: "retryDelay": "44.5s"
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+))s"', msg)
    if m:
        return float(m.group(1))

    # Generic: "retry in 44.5s" / "Please retry in 20s"
    m = re.search(r'retry\s+in\s+(\d+(?:\.\d+)?)\s*s', msg, re.IGNORECASE)
    if m:
        return float(m.group(1))

    return default


def _call_with_retry(
    *,
    max_retries: int = 3,
    verbose: bool = True,
    **call_kwargs,
) -> tuple[str, int, int, float]:
    """
    make_call() พร้อม auto-retry เมื่อเจอ 429 หรือ 503

    ถ้า API บอกว่า "retry in 44s" จะรอ 44 วิแล้วส่งใหม่
    ถ้าไม่มีข้อมูล retry delay จะรอ 60 วิ
    ทำซ้ำสูงสุด max_retries ครั้ง
    """
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return make_call(**call_kwargs)

        except Exception as e:
            last_error = e

            if _is_retryable(e) and attempt < max_retries:
                delay = _extract_retry_delay(e)
                delay = min(delay + 2, 180)  # buffer 2 วิ, cap ที่ 3 นาที

                if verbose:
                    print(
                        f"\n    ⏳ Rate limit/overloaded — รอ {delay:.0f}s "
                        f"แล้วลองใหม่ ({attempt + 1}/{max_retries})",
                        end="", flush=True,
                    )
                time.sleep(delay)
                if verbose:
                    print(f" → ลองใหม่...", end=" ", flush=True)

            else:
                # error ประเภทอื่น หรือ retry หมดแล้ว
                raise

    raise last_error  # type: ignore[misc]


# ── Core benchmark functions ──────────────────────────────────────────────────

def run_model_benchmark(
    *,
    model_id:    str,
    model_name:  str,
    provider:    str,
    api_key:     str,
    cases:       Optional[list[ThaiTestCase]] = None,
    max_tokens:  int = 512,
    max_retries: int = 3,
    verbose:     bool = True,
) -> ModelBenchmarkResult:
    """
    รัน benchmark ทุก test case กับ model ที่ระบุ
    เมื่อเจอ rate limit จะรอและลองใหม่อัตโนมัติ

    Args:
        model_id:    model ID เช่น "gemini-2.5-flash"
        model_name:  ชื่อสวยงาม เช่น "Gemini 2.5 Flash"
        provider:    "google" | "openai" | "anthropic"
        api_key:     API key สำหรับ provider นั้น
        cases:       ชุดข้อสอบ (ถ้าไม่ระบุจะใช้ทั้งหมด)
        max_tokens:  token สูงสุดของคำตอบ
        max_retries: จำนวนครั้งสูงสุดที่จะ retry เมื่อเจอ rate limit
        verbose:     แสดงผลระหว่างรันไหม
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
            print(
                f"  [{i:02d}/{len(test_cases)}] {case.id} "
                f"({case.category}/{case.difficulty})",
                end=" ", flush=True,
            )

        try:
            text, in_tok, out_tok, latency_ms = _call_with_retry(
                provider    = provider,
                model_id    = model_id,
                prompt      = case.prompt,
                api_key     = api_key,
                max_tokens  = max_tokens,
                max_retries = max_retries,
                verbose     = verbose,
            )

            score = score_response(text, case)
            scores.append(score)

            if verbose:
                status = "✅" if score.passed else "❌"
                print(
                    f"{status} score={score.final_score:.1f} "
                    f"kw={score.keyword_score:.0%} "
                    f"th={score.thai_ratio:.0%} "
                    f"({latency_ms:.0f}ms)"
                )

        except Exception as e:
            if verbose:
                print(f"💥 ERROR: {str(e)[:120]}")
            scores.append(ResponseScore(
                test_case_id     = case.id,
                category         = case.category,
                difficulty       = case.difficulty,
                keyword_score    = 0.0,
                thai_ratio       = 0.0,
                length_ok        = False,
                final_score      = 0.0,
                passed           = False,
                response_preview = f"ERROR: {str(e)[:60]}",
            ))

        # หน่วงเล็กน้อยระหว่าง case เพื่อลด rate limit
        time.sleep(1.0)

    result = ModelBenchmarkResult(
        model_id   = model_id,
        model_name = model_name,
        provider   = provider,
        scores     = scores,
    )

    if verbose:
        print(
            f"\n  📊 ผลรวม: avg={result.avg_final_score}/10 "
            f"| pass={result.pass_rate:.0%} "
            f"| thai={result.avg_thai_ratio:.0%}"
        )

    return result


def run_full_benchmark(
    models:      list[dict],
    api_keys:    ApiKeys,
    cases:       Optional[list[ThaiTestCase]] = None,
    output_path: Optional[str] = None,
    max_retries: int = 3,
    verbose:     bool = True,
) -> list[ModelBenchmarkResult]:
    """
    รัน benchmark กับหลาย model พร้อมกัน

    Args:
        models: list of dicts เช่น:
            [{"model_id": "gemini-2.5-flash", "model_name": "Gemini 2.5 Flash", "provider": "google"}]
        api_keys:    ApiKeys object ที่มี key สำหรับ provider ที่ต้องการ
        cases:       ชุดข้อสอบ (ถ้าไม่ระบุใช้ทั้งหมด)
        output_path: path สำหรับบันทึก JSON ผลลัพธ์
        max_retries: จำนวนครั้งสูงสุดที่จะ retry ต่อ request
        verbose:     แสดงผลระหว่างรันไหม

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
            model_id    = m["model_id"],
            model_name  = m["model_name"],
            provider    = provider,
            api_key     = key,
            cases       = cases,
            max_retries = max_retries,
            verbose     = verbose,
        )
        results.append(result)

    results.sort(key=lambda r: r.avg_final_score, reverse=True)

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
