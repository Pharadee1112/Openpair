"""
Live tests — make REAL API calls and cost real money.

Run with:
    pytest tests/test_live.py -v -m live

Skipped automatically (per-test) when the matching provider has no API key.
Excluded from a plain `pytest` run only if you pass `-m "not live"`.
"""

import pytest

from openpair import OpenPair, ApiKeys


@pytest.mark.live
class TestLive:
    @pytest.fixture(autouse=True)
    def require_keys(self):
        keys = ApiKeys()
        if not keys.available_providers():
            pytest.skip("No API keys configured")

    def test_live_openai(self):
        keys = ApiKeys()
        if not keys.has("openai"):
            pytest.skip("No OPENAI_API_KEY")
        client = OpenPair(api_keys=keys, preferred_provider="openai")
        result = client.call("Say 'hello' in one word.")
        assert len(result.response_text) > 0
        assert result.provider == "openai"
        print(f"\n[OpenAI] {result.model_name}: {result.response_text!r} ({result.latency_ms:.0f}ms)")

    def test_live_anthropic(self):
        keys = ApiKeys()
        if not keys.has("anthropic"):
            pytest.skip("No ANTHROPIC_API_KEY")
        client = OpenPair(api_keys=keys, preferred_provider="anthropic")
        result = client.call("Say 'hello' in one word.")
        assert len(result.response_text) > 0
        assert result.provider == "anthropic"
        print(f"\n[Anthropic] {result.model_name}: {result.response_text!r} ({result.latency_ms:.0f}ms)")

    def test_live_google(self):
        keys = ApiKeys()
        if not keys.has("google"):
            pytest.skip("No GOOGLE_API_KEY")
        client = OpenPair(api_keys=keys, preferred_provider="google")
        result = client.call("Say 'hello' in one word.")
        assert len(result.response_text) > 0
        assert result.provider == "google"
        print(f"\n[Google] {result.model_name}: {result.response_text!r} ({result.latency_ms:.0f}ms)")

    def test_live_groq(self):
        keys = ApiKeys()
        if not keys.has("groq"):
            pytest.skip("No GROQ_API_KEY")
        client = OpenPair(api_keys=keys, preferred_provider="groq")
        result = client.call("Say 'hello' in one word.")
        assert len(result.response_text) > 0
        assert result.provider == "groq"
        print(f"\n[Groq] {result.model_name}: {result.response_text!r} ({result.latency_ms:.0f}ms)")

    def test_live_thai_routing(self):
        keys = ApiKeys()
        client = OpenPair(api_keys=keys)
        result = client.call("สวัสดีครับ คุณชื่ออะไร")
        assert len(result.response_text) > 0
        print(f"\n[Thai] {result.model_name}: {result.response_text!r}")
