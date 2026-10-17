"""
Tests for run_benchmark.py's --models parsing (no API calls).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_benchmark import parse_case_ids, parse_model_spec


class TestParseModelSpec:
    def test_openrouter_prefix_is_stripped(self):
        m = parse_model_spec("openrouter:meta-llama/llama-3.3-70b-instruct")
        assert m == {
            "model_id":   "meta-llama/llama-3.3-70b-instruct",
            "model_name": "meta-llama/llama-3.3-70b-instruct",
            "provider":   "openrouter",
        }

    def test_ollama_prefix_is_stripped_and_keeps_tag(self):
        m = parse_model_spec("ollama:qwen2.5:3b")
        assert m == {
            "model_id":   "qwen2.5:3b",
            "model_name": "qwen2.5:3b",
            "provider":   "ollama",
        }

    def test_org_slash_model_without_prefix_stays_groq(self):
        assert parse_model_spec("openai/gpt-oss-120b")["provider"] == "groq"

    def test_gemini_is_google(self):
        m = parse_model_spec("gemini-3.1-flash-lite")
        assert m["provider"] == "google"
        assert m["model_id"] == "gemini-3.1-flash-lite"


class TestParseCaseIds:
    def test_comma_list(self):
        assert parse_case_ids("qa_52, qa_53,") == {"qa_52", "qa_53"}

    def test_file_with_one_id_per_line(self, tmp_path):
        f = tmp_path / "ids.txt"
        f.write_text("qa_52\n\ntr_71\n", encoding="utf-8")
        assert parse_case_ids(f"@{f}") == {"qa_52", "tr_71"}
