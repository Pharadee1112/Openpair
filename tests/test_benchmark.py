"""
Unit tests สำหรับ Thai Benchmark System
ไม่ต้องการ API key — test เฉพาะ scorer, dataset, และ retry logic
"""

import pytest
from unittest.mock import patch, MagicMock
from openpair.benchmark.checkpoint import CaseCheckpoint
from openpair.benchmark.dataset import (
    THAI_TEST_CASES, ThaiTestCase, CATEGORIES, get_suite, get_cases_by_category,
)
from openpair.benchmark.scorer import score_response, _thai_ratio, _keyword_score
from openpair.benchmark.runner import (
    _is_retryable, _extract_retry_delay, _call_with_retry,
    run_model_benchmark, QuotaExhausted,
)


# ── Dataset tests ─────────────────────────────────────────────────────────────

class TestDataset:
    def test_has_enough_cases(self):
        assert len(THAI_TEST_CASES) >= 15, "ควรมีอย่างน้อย 15 test cases"

    def test_all_categories_covered(self):
        covered = {c.category for c in THAI_TEST_CASES}
        for cat in CATEGORIES:
            assert cat in covered, f"ไม่มี test case สำหรับหมวด '{cat}'"

    def test_all_cases_have_required_fields(self):
        for case in THAI_TEST_CASES:
            assert case.id,                    f"{case.id}: ไม่มี id"
            assert case.prompt,                f"{case.id}: ไม่มี prompt"
            assert case.expected_keywords,     f"{case.id}: ไม่มี expected_keywords"
            assert 0 < case.keyword_threshold <= 1.0, f"{case.id}: keyword_threshold ผิด"
            assert 0 <= case.min_thai_ratio <= 1.0,   f"{case.id}: min_thai_ratio ผิด"
            assert case.min_length > 0,                f"{case.id}: min_length ผิด"

    def test_ids_are_unique(self):
        ids = [c.id for c in THAI_TEST_CASES]
        assert len(ids) == len(set(ids)), "มี id ซ้ำกัน"

    def test_difficulty_values_valid(self):
        valid = {"easy", "medium", "hard"}
        for case in THAI_TEST_CASES:
            assert case.difficulty in valid, f"{case.id}: difficulty '{case.difficulty}' ไม่ถูกต้อง"

    def test_prompts_contain_thai(self):
        """prompt ส่วนใหญ่ควรมีภาษาไทยอยู่ด้วย"""
        thai_prompts = [c for c in THAI_TEST_CASES if _thai_ratio(c.prompt) > 0.1]
        assert len(thai_prompts) >= len(THAI_TEST_CASES) * 0.7


@pytest.fixture(scope="module")
def full():
    return get_suite("full")


class TestFullSuite:
    """ชุดขยาย data/*.json — 100 เคสต่อหมวด"""

    def test_core_is_default_and_unchanged(self):
        assert get_suite() == THAI_TEST_CASES

    def test_100_cases_per_category(self, full):
        for cat in CATEGORIES:
            n = sum(1 for c in full if c.category == cat)
            assert n == 100, f"หมวด {cat} มี {n} เคส (ควรเป็น 100)"

    def test_ids_unique_and_prefixed_like_core(self, full):
        ids = [c.id for c in full]
        assert len(ids) == len(set(ids)), "มี id ซ้ำกันระหว่าง core กับชุดขยาย"
        prefix = {c.category: c.id.rsplit("_", 1)[0] for c in THAI_TEST_CASES}
        for c in full:
            assert c.id.rsplit("_", 1)[0] == prefix[c.category], f"{c.id}: prefix ไม่ตรงหมวด {c.category}"

    def test_prompts_unique(self, full):
        prompts = [c.prompt for c in full]
        assert len(prompts) == len(set(prompts)), "มี prompt ซ้ำกัน"

    def test_fields_valid(self, full):
        for c in full:
            assert c.difficulty in {"easy", "medium", "hard"}, c.id
            assert c.expected_keywords and all(k.strip() for k in c.expected_keywords), c.id
            assert 0 < c.keyword_threshold <= 1.0, c.id
            assert 0 <= c.min_thai_ratio <= 1.0, c.id
            assert c.min_length > 0, c.id

    def test_prompts_contain_thai(self, full):
        for c in full:
            assert _thai_ratio(c.prompt) > 0.05, f"{c.id}: prompt แทบไม่มีภาษาไทย"

    def test_classification_labels_not_substrings_of_each_other(self, full):
        # keyword scorer ใช้ substring match — ถ้าป้าย A อยู่ในป้าย B (เช่น "ทางการ" ใน "กึ่งทางการ")
        # model ที่ตอบผิดเป็น B จะได้คะแนนป้าย A ไปด้วย
        labels = {c.expected_keywords[0] for c in full
                  if c.category == "classification" and len(c.expected_keywords) == 1}
        for a in labels:
            for b in labels:
                assert a == b or a not in b, f"ป้าย {a!r} เป็น substring ของ {b!r}"

    def test_category_filter_respects_suite(self):
        assert len(get_cases_by_category("qa")) == 5
        assert len(get_cases_by_category("qa", suite="full")) == 100

    def test_unknown_suite_raises(self):
        with pytest.raises(ValueError):
            get_suite("huge")


# ── Scorer tests ──────────────────────────────────────────────────────────────

class TestThaiRatio:
    def test_pure_thai(self):
        assert _thai_ratio("สวัสดีครับ") > 0.8

    def test_pure_english(self):
        assert _thai_ratio("Hello world") == 0.0

    def test_mixed(self):
        ratio = _thai_ratio("Hello สวัสดี")
        assert 0.3 < ratio < 0.7

    def test_empty(self):
        assert _thai_ratio("") == 0.0


class TestKeywordScore:
    def test_all_keywords_found(self):
        score = _keyword_score("กรุงเทพมหานคร คือเมืองหลวง", ["กรุงเทพ", "เมืองหลวง"])
        assert score == 1.0

    def test_no_keywords_found(self):
        score = _keyword_score("Hello world", ["กรุงเทพ", "เมืองหลวง"])
        assert score == 0.0

    def test_partial_keywords(self):
        score = _keyword_score("กรุงเทพ is big", ["กรุงเทพ", "เมืองหลวง"])
        assert score == 0.5

    def test_case_insensitive_english(self):
        score = _keyword_score("machine learning is great", ["Machine Learning", "AI"])
        assert score >= 0.5  # "Machine Learning" found case-insensitively

    def test_empty_keywords(self):
        assert _keyword_score("any text", []) == 1.0


class TestScoreResponse:
    def setup_method(self):
        self.case = ThaiTestCase(
            id="test_case",
            category="qa",
            difficulty="easy",
            prompt="เมืองหลวงของไทยคืออะไร?",
            expected_keywords=["กรุงเทพ", "เมืองหลวง"],
            keyword_threshold=0.5,
            min_thai_ratio=0.3,
        )

    def test_perfect_response(self):
        response = "เมืองหลวงของประเทศไทยคือกรุงเทพมหานคร ซึ่งเป็นศูนย์กลางของประเทศ"
        score = score_response(response, self.case)
        assert score.final_score >= 7.0
        assert score.passed

    def test_empty_response_fails(self):
        score = score_response("", self.case)
        assert score.final_score == 0.0
        assert not score.passed

    def test_english_only_response_low_thai(self):
        score = score_response("The capital of Thailand is Bangkok.", self.case)
        assert score.thai_ratio < 0.1
        assert not score.passed  # ไม่ผ่าน min_thai_ratio

    def test_wrong_answer_low_keyword(self):
        score = score_response("ประเทศไทยมีอาหารอร่อยมากมายและวัฒนธรรมที่สวยงาม", self.case)
        assert score.keyword_score < 0.5
        assert not score.passed

    def test_score_in_range(self):
        for response in ["", "สวัสดี", "กรุงเทพมหานครคือเมืองหลวงของประเทศไทยครับ"]:
            score = score_response(response, self.case)
            assert 0.0 <= score.final_score <= 10.0

    def test_suggested_thai_score_in_range(self):
        from openpair.benchmark.scorer import ModelBenchmarkResult
        scores = [score_response("กรุงเทพคือเมืองหลวง", self.case)]
        result = ModelBenchmarkResult(
            model_id="test", model_name="Test", provider="test", scores=scores
        )
        assert 1 <= result.suggested_thai_score <= 10

    def test_short_correct_answer_fails_with_default_min_length(self):
        # Default min_length=20 penalizes a short-but-correct answer.
        score = score_response("กรุงเทพมหานคร", self.case)
        assert not score.length_ok
        assert not score.passed

    def test_short_correct_answer_passes_with_lower_min_length(self):
        # A case that intentionally expects a brief answer should lower min_length.
        brief_case = ThaiTestCase(
            id="brief_case",
            category="qa",
            difficulty="easy",
            prompt="เมืองหลวงของไทยคืออะไร? ตอบสั้นๆ",
            expected_keywords=["กรุงเทพ"],
            keyword_threshold=0.5,
            min_thai_ratio=0.3,
            min_length=5,
        )
        score = score_response("กรุงเทพมหานคร", brief_case)
        assert score.length_ok
        assert score.passed


class TestQa01AndCls02Thresholds:
    """Regression coverage for the qa_01/cls_02 min_length fix — both prompts
    intentionally ask for a brief/single-word answer, so the default 20-char
    length gate was failing genuinely correct responses."""

    def test_qa_01_short_correct_answer_passes(self):
        case = next(c for c in THAI_TEST_CASES if c.id == "qa_01")
        score = score_response("กรุงเทพมหานคร", case)
        assert score.passed
        assert score.length_ok

    def test_cls_02_single_word_answer_passes(self):
        case = next(c for c in THAI_TEST_CASES if c.id == "cls_02")
        score = score_response("เทคโนโลยี", case)
        assert score.passed
        assert score.length_ok


# ── Retry logic tests ─────────────────────────────────────────────────────────

class TestRetryHelpers:
    def test_is_rate_limit_google_429(self):
        err = Exception("429 RESOURCE_EXHAUSTED quota exceeded")
        assert _is_retryable(err)

    def test_is_rate_limit_openai(self):
        err = Exception("rate_limit_exceeded: too many requests")
        assert _is_retryable(err)

    def test_is_overloaded_google_503(self):
        err = Exception("503 UNAVAILABLE. The model is overloaded. Please try again later.")
        assert _is_retryable(err)

    def test_is_rate_limit_false_for_other(self):
        err = Exception("500 Internal Server Error")
        assert not _is_retryable(err)

    def test_extract_retry_delay_google_format(self):
        err = Exception('"retryDelay": "44.5s"')
        assert _extract_retry_delay(err) == pytest.approx(44.5)

    def test_extract_retry_delay_generic_format(self):
        err = Exception("Please retry in 30s after this message")
        assert _extract_retry_delay(err) == pytest.approx(30.0)

    def test_extract_retry_delay_default(self):
        err = Exception("some other error with no delay info")
        assert _extract_retry_delay(err, default=60.0) == 60.0


class TestCallWithRetry:
    def test_success_on_first_try(self):
        with patch("openpair.benchmark.runner.make_call", return_value=("ok", 5, 10, 100.0)):
            result = _call_with_retry(
                provider="google", model_id="m", prompt="p",
                api_key="k", verbose=False,
            )
        assert result == ("ok", 5, 10, 100.0)

    def test_retries_on_rate_limit_then_succeeds(self):
        """ครั้งแรก 429 → retry → สำเร็จ"""
        call_count = 0

        def fake_call(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception('429 RESOURCE_EXHAUSTED "retryDelay": "1s"')
            return ("ok after retry", 5, 10, 200.0)

        with patch("openpair.benchmark.runner.make_call", side_effect=fake_call):
            with patch("openpair.benchmark.runner.time.sleep"):  # ไม่ให้รอจริง
                result = _call_with_retry(
                    provider="google", model_id="m", prompt="p",
                    api_key="k", max_retries=3, verbose=False,
                )

        assert result[0] == "ok after retry"
        assert call_count == 2  # เรียก 2 ครั้ง (1 fail + 1 success)

    def test_raises_after_max_retries(self):
        """429 ทุกครั้ง → raise หลังครบ max_retries"""
        with patch("openpair.benchmark.runner.make_call",
                   side_effect=Exception('429 RESOURCE_EXHAUSTED "retryDelay": "1s"')):
            with patch("openpair.benchmark.runner.time.sleep"):
                with pytest.raises(Exception, match="429"):
                    _call_with_retry(
                        provider="google", model_id="m", prompt="p",
                        api_key="k", max_retries=2, verbose=False,
                    )

    def test_non_rate_limit_error_raises_immediately(self):
        """error ที่ไม่ใช่ rate limit ต้อง raise ทันที ไม่ retry"""
        call_count = 0

        def fake_call(**kwargs):
            nonlocal call_count
            call_count += 1
            raise ValueError("invalid model id")

        with patch("openpair.benchmark.runner.make_call", side_effect=fake_call):
            with pytest.raises(ValueError):
                _call_with_retry(
                    provider="google", model_id="m", prompt="p",
                    api_key="k", max_retries=3, verbose=False,
                )

        assert call_count == 1  # raise ทันที ไม่ retry

    def test_large_retry_delay_raises_quota_exhausted(self):
        """retryDelay >= threshold ต้อง raise QuotaExhausted แทนการ sleep"""
        err = Exception('429 RESOURCE_EXHAUSTED "retryDelay": "600s"')
        with patch("openpair.benchmark.runner.make_call", side_effect=err):
            with patch("openpair.benchmark.runner.time.sleep") as mock_sleep:
                with pytest.raises(QuotaExhausted):
                    _call_with_retry(
                        provider="google", model_id="m", prompt="p",
                        api_key="k", max_retries=3, verbose=False,
                    )
                mock_sleep.assert_not_called()

    def test_per_day_message_raises_quota_exhausted(self):
        err = Exception("429 quota exceeded, limit: 50 requests per day")
        with patch("openpair.benchmark.runner.make_call", side_effect=err):
            with patch("openpair.benchmark.runner.time.sleep") as mock_sleep:
                with pytest.raises(QuotaExhausted):
                    _call_with_retry(
                        provider="google", model_id="m", prompt="p",
                        api_key="k", max_retries=3, verbose=False,
                    )
                mock_sleep.assert_not_called()

    def test_integer_retry_delay_now_matches(self):
        """Bug A: "44s" (ไม่มีทศนิยม) เคยไม่ match — ตอนนี้ต้อง parse ได้"""
        err = Exception('"retryDelay": "44s"')
        assert _extract_retry_delay(err) == pytest.approx(44.0)


# ── Resume / checkpoint flow tests ──────────────────────────────────────────

def _fake_case(id_, prompt=None):
    return ThaiTestCase(
        id=id_, category="qa", difficulty="easy",
        prompt=prompt or f"เมืองหลวงของไทยคืออะไร? [{id_}]",
        expected_keywords=["กรุงเทพ"], keyword_threshold=0.5,
        min_thai_ratio=0.2, min_length=5,
    )


class TestErrorDoesNotHurtAverage:
    def test_error_case_excluded_from_scores_and_average(self):
        cases = [_fake_case("c1"), _fake_case("c2"), _fake_case("c3")]

        def fake_call(**kwargs):
            if kwargs["prompt"] == cases[1].prompt:
                raise ValueError("boom, not retryable")
            return ("กรุงเทพมหานคร", 5, 5, 10.0)

        with patch("openpair.benchmark.runner.make_call", side_effect=fake_call):
            with patch("openpair.benchmark.runner.time.sleep"):
                result = run_model_benchmark(
                    model_id="m1", model_name="M1", provider="google",
                    api_key="k", cases=cases, verbose=False,
                )

        # เคส error ต้องไม่ถูกนับเข้า scores เลย
        assert len(result.scores) == 2
        assert all(s.final_score > 0 for s in result.scores)
        assert result.avg_final_score > 0


class TestResumeFlow:
    def test_fresh_then_resume_only_hits_new_cases(self, tmp_path):
        ckpt_path = tmp_path / "ckpt.jsonl"
        cases_round1 = [_fake_case("c1"), _fake_case("c2")]
        calls = []

        def fake_call(**kwargs):
            calls.append(kwargs["prompt"])
            return ("กรุงเทพมหานคร", 5, 5, 10.0)

        with patch("openpair.benchmark.runner.make_call", side_effect=fake_call):
            with patch("openpair.benchmark.runner.time.sleep"):
                ckpt = CaseCheckpoint(ckpt_path)
                result1 = run_model_benchmark(
                    model_id="m1", model_name="M1", provider="google",
                    api_key="k", cases=cases_round1, verbose=False, checkpoint=ckpt,
                )

        assert len(result1.scores) == 2
        assert len(calls) == 2

        # เพิ่มเคสใหม่ แล้ว resume — ต้องยิงเฉพาะเคสใหม่
        cases_round2 = cases_round1 + [_fake_case("c3")]
        calls.clear()

        with patch("openpair.benchmark.runner.make_call", side_effect=fake_call):
            with patch("openpair.benchmark.runner.time.sleep"):
                ckpt2 = CaseCheckpoint(ckpt_path)  # reload from disk (simulates new process)
                result2 = run_model_benchmark(
                    model_id="m1", model_name="M1", provider="google",
                    api_key="k", cases=cases_round2, verbose=False, checkpoint=ckpt2,
                )

        assert len(result2.scores) == 3
        assert len(calls) == 1  # เฉพาะ c3 เท่านั้นที่ยิง API จริง

    def test_quota_exhausted_mid_run_saves_partial_then_resume_completes(self, tmp_path):
        ckpt_path = tmp_path / "ckpt.jsonl"
        cases = [_fake_case("c1"), _fake_case("c2"), _fake_case("c3")]

        def fake_call_quota_at_c2(**kwargs):
            if kwargs["prompt"] == cases[1].prompt:
                raise Exception('429 RESOURCE_EXHAUSTED "retryDelay": "600s"')
            return ("กรุงเทพมหานคร", 5, 5, 10.0)

        with patch("openpair.benchmark.runner.make_call", side_effect=fake_call_quota_at_c2):
            with patch("openpair.benchmark.runner.time.sleep"):
                ckpt = CaseCheckpoint(ckpt_path)
                result1 = run_model_benchmark(
                    model_id="m1", model_name="M1", provider="google",
                    api_key="k", cases=cases, verbose=False, checkpoint=ckpt,
                )

        # ทำได้แค่ c1 ก่อนหยุดเพราะ quota
        assert len(result1.scores) == 1

        # resume รอบถัดไปด้วย call ปกติ (quota กลับมาแล้ว) — ทำต่อจนครบ
        def fake_call_ok(**kwargs):
            return ("กรุงเทพมหานคร", 5, 5, 10.0)

        with patch("openpair.benchmark.runner.make_call", side_effect=fake_call_ok):
            with patch("openpair.benchmark.runner.time.sleep"):
                ckpt2 = CaseCheckpoint(ckpt_path)
                result2 = run_model_benchmark(
                    model_id="m1", model_name="M1", provider="google",
                    api_key="k", cases=cases, verbose=False, checkpoint=ckpt2,
                )

        assert len(result2.scores) == 3
