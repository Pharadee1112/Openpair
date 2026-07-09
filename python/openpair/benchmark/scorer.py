"""
benchmark.scorer — วัดคุณภาพ response ของ model
=================================================
ไม่ใช้ LLM judge (ประหยัด cost) แต่ใช้ 3 metrics:

  1. keyword_score  (0–1) : มี expected keyword ในคำตอบกี่ fraction
  2. thai_ratio     (0–1) : response เป็นภาษาไทยมากแค่ไหน
  3. length_ok      (bool): response ยาวพอ (ไม่ตอบแค่คำเดียว)

final_score (0–10) = weighted average ของทั้ง 3
"""

from __future__ import annotations
from dataclasses import dataclass
from .dataset import ThaiTestCase


@dataclass
class ResponseScore:
    test_case_id:   str
    category:       str
    difficulty:     str
    keyword_score:  float   # 0.0–1.0
    thai_ratio:     float   # 0.0–1.0 (fraction of Thai chars in response)
    length_ok:      bool    # response length >= case.min_length
    final_score:    float   # 0.0–10.0
    passed:         bool    # ผ่านเกณฑ์ขั้นต่ำไหม
    response_preview: str   # 60 chars แรกของ response


def _thai_ratio(text: str) -> float:
    """Fraction of characters that are Thai Unicode (U+0E00–U+0E7F)."""
    if not text:
        return 0.0
    thai = sum(1 for c in text if '฀' <= c <= '๿')
    return thai / len(text)


def _keyword_score(response: str, keywords: list[str]) -> float:
    """Fraction of expected keywords found in response (case-insensitive for ASCII)."""
    if not keywords:
        return 1.0
    lower = response.lower()
    hits = sum(1 for kw in keywords if kw.lower() in lower or kw in response)
    return hits / len(keywords)


def score_response(response: str, case: ThaiTestCase) -> ResponseScore:
    """
    Score a single model response against a ThaiTestCase.
    Returns a ResponseScore with all metrics.
    """
    response = response.strip()

    kw_score   = _keyword_score(response, case.expected_keywords)
    th_ratio   = _thai_ratio(response)
    length_ok  = len(response) >= case.min_length

    # ── Weighted final score ──────────────────────────────────────
    # keyword: 50% weight  — ตอบถูกต้องไหม
    # thai:    30% weight  — ตอบเป็นภาษาไทยไหม
    # length:  20% weight  — ตอบครบถ้วนไหม
    keyword_contrib = kw_score * 5.0          # 0–5 pts
    thai_contrib    = min(th_ratio * 10, 3.0) # 0–3 pts (cap at 3)
    length_contrib  = 2.0 if length_ok else 0.0  # 0 or 2 pts

    final = keyword_contrib + thai_contrib + length_contrib  # 0–10

    # ── Pass/fail ─────────────────────────────────────────────────
    # ผ่านถ้า: keyword >= threshold AND thai >= min_thai_ratio AND length ok
    passed = (
        kw_score  >= case.keyword_threshold and
        th_ratio  >= case.min_thai_ratio    and
        length_ok
    )

    return ResponseScore(
        test_case_id    = case.id,
        category        = case.category,
        difficulty      = case.difficulty,
        keyword_score   = round(kw_score, 3),
        thai_ratio      = round(th_ratio, 3),
        length_ok       = length_ok,
        final_score     = round(final, 2),
        passed          = passed,
        response_preview= response[:80].replace("\n", " "),
    )


@dataclass
class ModelBenchmarkResult:
    model_id:      str
    model_name:    str
    provider:      str
    scores:        list[ResponseScore]

    @property
    def avg_final_score(self) -> float:
        if not self.scores:
            return 0.0
        return round(sum(s.final_score for s in self.scores) / len(self.scores), 2)

    @property
    def avg_keyword_score(self) -> float:
        if not self.scores:
            return 0.0
        return round(sum(s.keyword_score for s in self.scores) / len(self.scores), 3)

    @property
    def avg_thai_ratio(self) -> float:
        if not self.scores:
            return 0.0
        return round(sum(s.thai_ratio for s in self.scores) / len(self.scores), 3)

    @property
    def pass_rate(self) -> float:
        if not self.scores:
            return 0.0
        return round(sum(1 for s in self.scores if s.passed) / len(self.scores), 3)

    @property
    def suggested_thai_score(self) -> int:
        """Convert avg_final_score (0–10) → thai_score int (1–10) for registry."""
        return max(1, min(10, round(self.avg_final_score)))

    def scores_by_category(self) -> dict[str, list[ResponseScore]]:
        result: dict[str, list[ResponseScore]] = {}
        for s in self.scores:
            result.setdefault(s.category, []).append(s)
        return result

    def category_avg(self, category: str) -> float:
        cat_scores = [s.final_score for s in self.scores if s.category == category]
        if not cat_scores:
            return 0.0
        return round(sum(cat_scores) / len(cat_scores), 2)
