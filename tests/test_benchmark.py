"""
Unit tests สำหรับ Thai Benchmark System
ไม่ต้องการ API key — test เฉพาะ scorer และ dataset
"""

import pytest
from openpair.benchmark.dataset import THAI_TEST_CASES, ThaiTestCase, CATEGORIES
from openpair.benchmark.scorer import score_response, _thai_ratio, _keyword_score


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
