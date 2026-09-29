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
from .checkpoint import CaseCheckpoint
from .dataset import ThaiTestCase, THAI_TEST_CASES
from .scorer import score_response, ResponseScore, ModelBenchmarkResult


class QuotaExhausted(Exception):
    """Daily quota (ไม่ใช่ rate limit รายนาที) หมด — ไม่ควรรอแล้วลองใหม่ ต้องหยุด"""


QUOTA_STOP_THRESHOLD_S = 300.0


# ── Retry helpers ─────────────────────────────────────────────────────────────


def _extract_retry_delay(error: Exception, default: float = 60.0) -> float:
    """
    อ่านวินาทีที่ต้องรอจาก error message
    รองรับทั้ง Google ("retryDelay": "44s") และ OpenAI ("Please try again in 20s")
    """
    msg = str(error)

    # Google format: "retryDelay": "44.5s"
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', msg)
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

                if delay >= QUOTA_STOP_THRESHOLD_S or "perday" in str(e).lower() or "per day" in str(e).lower():
                    raise QuotaExhausted(f"quota รายวันหมด: {str(e)[:120]}") from e

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


class EmptyResponse(Exception):
    """model ตอบกลับมาเป็นข้อความว่าง — นับเป็น error (retry รอบหน้า) ไม่ใช่คะแนน 0"""


# ── Core benchmark functions ──────────────────────────────────────────────────

def run_model_benchmark(
    *,
    model_id:    str,
    model_name:  str,
    provider:    str,
    api_key:     str,
    cases:       Optional[list[ThaiTestCase]] = None,
    max_tokens:  int = 2048,
    max_retries: int = 3,
    verbose:     bool = True,
    checkpoint:  Optional[CaseCheckpoint] = None,
) -> ModelBenchmarkResult:
    """
    รัน benchmark ทุก test case กับ model ที่ระบุ
    เมื่อเจอ rate limit จะรอและลองใหม่อัตโนมัติ

    Args:
        model_id:    model ID เช่น "gemini-3.6-flash"
        model_name:  ชื่อสวยงาม เช่น "Gemini 3.6 Flash"
        provider:    "google" | "openai" | "anthropic"
        api_key:     API key สำหรับ provider นั้น
        cases:       ชุดข้อสอบ (ถ้าไม่ระบุจะใช้ทั้งหมด)
        max_tokens:  token สูงสุดของคำตอบ — reasoning model (gpt-oss, Gemini thinking) นับ token
                     ที่ใช้คิดรวมในนี้ด้วย ตั้งต่ำไป (512) คิดจนหมดแล้วได้คำตอบว่างเปล่า
        max_retries: จำนวนครั้งสูงสุดที่จะ retry เมื่อเจอ rate limit
        verbose:     แสดงผลระหว่างรันไหม
    """
    test_cases = cases or THAI_TEST_CASES
    scores: list[ResponseScore] = []
    error_count = 0
    quota_stopped = False

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

        if checkpoint is not None:
            cached = checkpoint.get(model_id, case)
            if cached is not None:
                scores.append(cached)
                if verbose:
                    print("⏭️  ข้าม (ทำแล้ว)")
                continue

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

            if not (text or "").strip():
                # คำตอบว่าง = ไม่ได้คำตอบ ไม่ใช่คำตอบที่แย่ — ไม่ให้คะแนน 0 และไม่ลง checkpoint
                raise EmptyResponse(
                    f"คำตอบว่าง (out_tok={out_tok}) — มักเกิดจาก reasoning ใช้ max_tokens={max_tokens} หมด"
                )

            score = score_response(text, case)
            scores.append(score)

            if checkpoint is not None:
                checkpoint.append(
                    model_id   = model_id,
                    model_name = model_name,
                    provider   = provider,
                    case       = case,
                    score      = score,
                )

            if verbose:
                status = "✅" if score.passed else "❌"
                print(
                    f"{status} score={score.final_score:.1f} "
                    f"kw={score.keyword_score:.0%} "
                    f"th={score.thai_ratio:.0%} "
                    f"({latency_ms:.0f}ms)"
                )

        except QuotaExhausted as e:
            if verbose:
                print(f"\n  🛑 quota หมด — หยุดรัน {model_name} (ผลที่ทำได้ถูกเซฟไว้แล้ว): {str(e)[:120]}")
            quota_stopped = True
            break

        except Exception as e:
            error_count += 1
            if verbose:
                print(f"💥 ERROR (จะลองใหม่รอบหน้า): {str(e)[:120]}")

        # หน่วงเล็กน้อยระหว่าง case เพื่อลด rate limit
        time.sleep(1.0)

    if verbose:
        done = len(scores)
        total = len(test_cases)
        pending = total - done
        print(
            f"\n  📌 สรุป: สำเร็จ {done}/{total} เคส"
            + (f" | ค้าง {pending} เคส" if pending else "")
            + (f" | error {error_count} เคส" if error_count else "")
            + (" | หยุดเพราะ quota หมด" if quota_stopped else "")
        )

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
    models:          list[dict],
    api_keys:        ApiKeys,
    cases:           Optional[list[ThaiTestCase]] = None,
    output_path:     Optional[str] = None,
    max_retries:     int = 3,
    verbose:         bool = True,
    resume:          bool = True,
    checkpoint_path: Optional[str] = None,
) -> list[ModelBenchmarkResult]:
    """
    รัน benchmark กับหลาย model พร้อมกัน

    Args:
        models: list of dicts เช่น:
            [{"model_id": "gemini-3.6-flash", "model_name": "Gemini 3.6 Flash", "provider": "google"}]
        api_keys:    ApiKeys object ที่มี key สำหรับ provider ที่ต้องการ
        cases:       ชุดข้อสอบ (ถ้าไม่ระบุใช้ทั้งหมด)
        output_path: path สำหรับบันทึก JSON ผลลัพธ์
        max_retries: จำนวนครั้งสูงสุดที่จะ retry ต่อ request
        verbose:     แสดงผลระหว่างรันไหม

    Returns:
        list ของ ModelBenchmarkResult เรียงตาม avg_final_score (สูง→ต่ำ)
    """
    results: list[ModelBenchmarkResult] = []

    if checkpoint_path is None and output_path:
        checkpoint_path = str(Path(output_path).with_suffix("")) + ".checkpoint.jsonl"

    checkpoint: Optional[CaseCheckpoint] = None
    if checkpoint_path:
        if not resume:
            Path(checkpoint_path).unlink(missing_ok=True)
        checkpoint = CaseCheckpoint(checkpoint_path)

    total_cases = len(cases) if cases is not None else len(THAI_TEST_CASES)

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
            checkpoint  = checkpoint,
        )
        results.append(result)

    results.sort(key=lambda r: r.avg_final_score, reverse=True)

    if output_path:
        _save_results(results, output_path, total_cases=total_cases)
        if verbose:
            print(f"\n💾 บันทึกผลลัพธ์ที่: {output_path}")

    return results


def _save_results(
    results: list[ModelBenchmarkResult],
    path: str,
    total_cases: Optional[int] = None,
) -> None:
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
                "completed_cases":      len(r.scores),
                "total_cases":          total_cases,
                "pending_cases":        (total_cases - len(r.scores)) if total_cases is not None else None,
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
