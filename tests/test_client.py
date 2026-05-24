"""
Python-side tests for OpenPair client.
Run with: pytest tests/test_client.py -v

NOTE: Tests marked @pytest.mark.live require real API keys in the environment.
      Run live tests with: pytest tests/test_client.py -v -m live
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from openpair import OpenPair, ApiKeys, CallResult


# ── Config tests ─────────────────────────────────────────────────────────────

class TestApiKeys:
    def test_reads_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-anthropic")
        monkeypatch.setenv("GOOGLE_API_KEY", "sk-test-google")

        keys = ApiKeys()
        assert keys.openai    == "sk-test-openai"
        assert keys.anthropic == "sk-test-anthropic"
        assert keys.google    == "sk-test-google"

    def test_explicit_keys_override_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key")
        keys = ApiKeys(openai="sk-explicit-key")
        assert keys.openai == "sk-explicit-key"

    def test_available_providers(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY",    raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY",    raising=False)
        keys = ApiKeys(openai="sk-x", google="gk-x")
        assert "openai" in keys.available_providers()
        assert "google" in keys.available_providers()
        assert "anthropic" not in keys.available_providers()

    def test_has_provider(self):
        keys = ApiKeys(anthropic="sk-ant-test")
        assert keys.has("anthropic")
        assert not keys.has("openai")

    def test_repr_masks_keys(self):
        keys = ApiKeys(openai="sk-1234567890abcdef")
        r = repr(keys)
        assert "sk-12345" in r
        assert "abcdef" not in r   # full key must NOT appear


# ── Routing tests (no API key needed) ────────────────────────────────────────

class TestRouting:
    def setup_method(self):
        # OpenPair without any API keys — only routing, no calls
        self.client = OpenPair(api_keys=ApiKeys())

    def test_route_returns_decision(self):
        d = self.client.route("Hello!")
        assert d.model_id
        assert d.provider in ("openai", "anthropic", "google")
        assert d.tier in ("small", "mid", "top", "expert")
        assert 1 <= d.complexity_score <= 10

    def test_simple_prompt_routes_small(self):
        d = self.client.route("Hi!")
        assert d.tier == "small"
        assert d.complexity_score <= 3

    def test_complex_prompt_routes_top(self):
        d = self.client.route(
            "Design a comprehensive microservices architecture for an e-commerce platform. "
            "Analyze trade-offs between synchronous and asynchronous communication patterns, "
            "implement circuit breakers, and explain database sharding strategies."
        )
        assert d.complexity_score >= 6

    def test_preferred_provider_respected(self):
        for provider in ("openai", "anthropic", "google"):
            d = self.client.route("What is Python?", preferred_provider=provider)
            assert d.provider == provider

    def test_thai_prompt_detected(self):
        d = self.client.route("สวัสดีครับ คุณเป็นอย่างไรบ้าง")
        assert "Thai" in d.reason

    def test_score_method(self):
        assert self.client.score("Hi") <= 3
        # 6-word prompt with design/system keywords → mid-range (4–6)
        assert self.client.score("Design a complex distributed system architecture") >= 4

    def test_is_thai_method(self):
        assert self.client.is_thai("สวัสดี")
        assert not self.client.is_thai("Hello world")

    def test_available_providers_empty_when_no_keys(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY",    raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY",    raising=False)
        client = OpenPair(api_keys=ApiKeys())
        assert client.available_providers() == []


# ── Call tests (mocked) ──────────────────────────────────────────────────────

class TestCall:
    def setup_method(self):
        self.client = OpenPair(api_keys=ApiKeys(
            openai    = "sk-fake-openai",
            anthropic = "sk-fake-anthropic",
            google    = "sk-fake-google",
        ))

    def _mock_make_call(self, mocker=None, text="Mocked response", in_tok=10, out_tok=20, latency=150.0):
        """Patch caller.make_call to return a fake response."""
        return patch(
            "openpair.client.make_call",
            return_value=(text, in_tok, out_tok, latency),
        )

    def test_call_returns_call_result(self):
        with self._mock_make_call():
            result = self.client.call("What is 2+2?")
        assert isinstance(result, CallResult)
        assert result.response_text == "Mocked response"
        assert result.input_tokens  == 10
        assert result.output_tokens == 20
        assert result.latency_ms    == 150.0

    def test_call_includes_routing_info(self):
        with self._mock_make_call():
            result = self.client.call("Hello!")
        assert result.model_id
        assert result.provider in ("openai", "anthropic", "google")
        assert result.tier in ("small", "mid", "top", "expert")
        assert result.routing_reason

    def test_estimated_cost_is_positive(self):
        with self._mock_make_call(in_tok=1000):
            result = self.client.call("Hello!")
        assert result.estimated_cost > 0

    def test_no_key_raises_runtime_error(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY",    raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY",    raising=False)
        client = OpenPair(api_keys=ApiKeys())
        with pytest.raises(RuntimeError, match="No API key"):
            client.call("Hello!")

    def test_fallback_provider_used(self, monkeypatch):
        # Clear all env vars so only our explicit key is used
        monkeypatch.delenv("OPENAI_API_KEY",    raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY",    raising=False)
        # Only anthropic key is set
        client = OpenPair(api_keys=ApiKeys(anthropic="sk-ant-test"))
        with patch("openpair.client.make_call", return_value=("ok", 5, 10, 100.0)):
            result = client.call("Hello!")
        # Should have used anthropic (the only available key)
        assert result.provider == "anthropic"


# ── Live tests (skipped unless real API keys present) ─────────────────────────

@pytest.mark.live
class TestLive:
    """
    These tests make REAL API calls and will cost money.
    Run with: pytest tests/test_client.py -v -m live
    """

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

    def test_live_thai_routing(self):
        keys = ApiKeys()
        client = OpenPair(api_keys=keys)
        result = client.call("สวัสดีครับ คุณชื่ออะไร")
        assert len(result.response_text) > 0
        print(f"\n[Thai] {result.model_name}: {result.response_text!r}")
