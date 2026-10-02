"""
Tests for run_benchmark.py's --models parsing (no API calls).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_benchmark import parse_model_spec


class TestParseModelSpec:
    def test_openrouter_prefix_is_stripped(self):
        m = parse_model_spec("openrouter:meta-llama/llama-3.3-70b-instruct")
        assert m == {
            "model_id":   "meta-llama/llama-3.3-70b-instruct",
            "model_name": "meta-llama/llama-3.3-70b-instruct",
            "provider":   "openrouter",
        }

    def test_org_slash_model_without_prefix_stays_groq(self):
        assert parse_model_spec("openai/gpt-oss-120b")["provider"] == "groq"

    def test_gemini_is_google(self):
        m = parse_model_spec("gemini-3.1-flash-lite")
        assert m["provider"] == "google"
        assert m["model_id"] == "gemini-3.1-flash-lite"
