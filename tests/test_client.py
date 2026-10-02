"""
Python-side tests for OpenPair client.
Run with: pytest tests/test_client.py -v

NOTE: Live tests (real API calls, @pytest.mark.live) live in tests/test_live.py.
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
        monkeypatch.setenv("GROQ_API_KEY", "sk-test-groq")

        keys = ApiKeys()
        assert keys.openai    == "sk-test-openai"
        assert keys.anthropic == "sk-test-anthropic"
        assert keys.google    == "sk-test-google"
        assert keys.groq      == "sk-test-groq"

    def test_explicit_keys_override_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key")
        keys = ApiKeys(openai="sk-explicit-key")
        assert keys.openai == "sk-explicit-key"

    def test_available_providers(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY",    raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY",    raising=False)
        monkeypatch.delenv("GROQ_API_KEY",      raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        keys = ApiKeys(openai="sk-x", google="gk-x")
        assert "openai" in keys.available_providers()
        assert "google" in keys.available_providers()
        assert "anthropic" not in keys.available_providers()
        assert "groq" not in keys.available_providers()

    def test_has_provider(self):
        keys = ApiKeys(anthropic="sk-ant-test")
        assert keys.has("anthropic")
        assert not keys.has("openai")

    def test_has_groq_provider(self):
        keys = ApiKeys(groq="gsk-test")
        assert keys.has("groq")
        assert "groq" in keys.available_providers()

    def test_repr_masks_keys(self):
        keys = ApiKeys(openai="sk-1234567890abcdef")
        r = repr(keys)
        assert "sk-12345" in r
        assert "abcdef" not in r   # full key must NOT appear

    def test_ollama_defaults(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("OLLAMA_MODEL",    raising=False)
        keys = ApiKeys()
        assert keys.ollama_base_url == "http://localhost:11434"
        assert keys.ollama_model    == "llama3.1"

    def test_ollama_available_when_server_responds(self):
        keys = ApiKeys()
        with patch("urllib.request.urlopen", return_value=MagicMock()):
            assert keys.is_ollama_available()
            assert keys.has("ollama")
            assert keys.for_provider("ollama") == "local"

    def test_ollama_unavailable_when_server_unreachable(self):
        keys = ApiKeys()
        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            assert not keys.is_ollama_available()
            assert not keys.has("ollama")
            assert keys.for_provider("ollama") is None


class TestOpenRouter:
    def test_reads_key_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-env")
        keys = ApiKeys()
        assert keys.openrouter == "sk-or-env"
        assert keys.for_provider("openrouter") == "sk-or-env"
        assert "openrouter" in keys.available_providers()

    def test_explicit_key_and_dict_input(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        assert ApiKeys(openrouter="sk-or-x").has("openrouter")
        client = OpenPair(api_keys={"openrouter": "sk-or-dict"})
        assert "openrouter" in client.available_providers()

    def test_repr_masks_openrouter_key(self):
        r = repr(ApiKeys(openrouter="sk-or-1234567890abcdef"))
        assert "openrouter=sk-or-12" in r
        assert "abcdef" not in r

    def test_make_call_hits_openrouter_endpoint(self, fake_ollama):
        # fake_ollama patches openai.OpenAI — reused here since OpenRouter is the same SDK surface.
        from openpair.caller import make_call
        fake_ollama.response_text = "สวัสดีจาก OpenRouter"
        text, in_tok, out_tok, latency_ms = make_call(
            provider="openrouter",
            model_id="meta-llama/llama-3.3-70b-instruct",
            prompt="สวัสดี",
            api_key="sk-or-test",
            system="ตอบเป็นภาษาไทย",
            max_tokens=128,
        )
        assert text == "สวัสดีจาก OpenRouter"
        assert (in_tok, out_tok) == (8, 16)
        assert fake_ollama.client_kwargs == [
            {"api_key": "sk-or-test", "base_url": "https://openrouter.ai/api/v1"}
        ]
        call = fake_ollama.calls[0]
        assert call["model"] == "meta-llama/llama-3.3-70b-instruct"
        assert call["max_tokens"] == 128
        assert call["messages"] == [
            {"role": "system", "content": "ตอบเป็นภาษาไทย"},
            {"role": "user", "content": "สวัสดี"},
        ]


# ── Routing tests (no API key needed) ────────────────────────────────────────

class TestRouting:
    def setup_method(self):
        # OpenPair without any API keys — only routing, no calls
        self.client = OpenPair(api_keys=ApiKeys())

    def test_route_returns_decision(self):
        d = self.client.route("Hello!")
        assert d.model_id
        assert d.provider in ("openai", "anthropic", "google", "groq")
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
        for provider in ("openai", "anthropic", "google", "groq"):
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
        monkeypatch.delenv("GROQ_API_KEY",      raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        client = OpenPair(api_keys=ApiKeys())
        assert client.available_providers() == []


# ── Call tests (mocked) ──────────────────────────────────────────────────────

class TestCall:
    def setup_method(self):
        self.client = OpenPair(api_keys=ApiKeys(
            openai    = "sk-fake-openai",
            anthropic = "sk-fake-anthropic",
            google    = "sk-fake-google",
            groq      = "gsk-fake-groq",
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
        assert result.provider in ("openai", "anthropic", "google", "groq")
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
        monkeypatch.delenv("GROQ_API_KEY",      raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        client = OpenPair(api_keys=ApiKeys())
        with patch.object(ApiKeys, "is_ollama_available", return_value=False):
            with pytest.raises(RuntimeError, match="No API key"):
                client.call("Hello!")

    def test_fallback_provider_used(self, monkeypatch):
        # Clear all env vars so only our explicit key is used
        monkeypatch.delenv("OPENAI_API_KEY",    raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY",    raising=False)
        monkeypatch.delenv("GROQ_API_KEY",      raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        # Only anthropic key is set
        client = OpenPair(api_keys=ApiKeys(anthropic="sk-ant-test"))
        with patch("openpair.client.make_call", return_value=("ok", 5, 10, 100.0)):
            result = client.call("Hello!")
        # Should have used anthropic (the only available key)
        assert result.provider == "anthropic"

    def test_groq_provider_used_when_preferred(self):
        with self._mock_make_call():
            result = self.client.call("Hello!", preferred_provider="groq")
        assert result.provider == "groq"
        assert result.model_id


# ── Cache tests ─────────────────────────────────────────────────────────────

class TestCache:
    def setup_method(self):
        self.client = OpenPair(api_keys=ApiKeys(
            openai    = "sk-fake-openai",
            anthropic = "sk-fake-anthropic",
            google    = "sk-fake-google",
            groq      = "gsk-fake-groq",
        ))

    def test_repeated_call_hits_cache_without_calling_api(self):
        with patch(
            "openpair.client.make_call",
            return_value=("first response", 10, 20, 150.0),
        ) as mock_call:
            first = self.client.call("Hello!")
            second = self.client.call("Hello!")

        assert mock_call.call_count == 1
        assert first.from_cache is False
        assert second.from_cache is True
        assert second.response_text == "first response"
        assert second.estimated_cost == 0.0

    def test_different_prompt_is_not_a_cache_hit(self):
        with patch(
            "openpair.client.make_call",
            return_value=("resp", 10, 20, 150.0),
        ) as mock_call:
            self.client.call("Hello!")
            self.client.call("Different prompt")

        assert mock_call.call_count == 2

    def test_use_cache_false_forces_fresh_call(self):
        with patch(
            "openpair.client.make_call",
            return_value=("resp", 10, 20, 150.0),
        ) as mock_call:
            self.client.call("Hello!")
            result = self.client.call("Hello!", use_cache=False)

        assert mock_call.call_count == 2
        assert result.from_cache is False

    def test_cache_evicts_oldest_beyond_cache_size(self):
        client = OpenPair(
            api_keys=ApiKeys(groq="gsk-fake-groq"),
            cache_size=2,
        )
        with patch(
            "openpair.client.make_call",
            return_value=("resp", 10, 20, 150.0),
        ) as mock_call:
            client.call("prompt A")
            client.call("prompt B")
            client.call("prompt C")  # evicts "prompt A"
            client.call("prompt A")  # cache miss again, re-calls API

        assert mock_call.call_count == 4


# ── Fallback chain tests (mocked) ──────────────────────────────────────────────

class TestFallbackChain:
    def setup_method(self):
        self.client = OpenPair(api_keys=ApiKeys(
            openai    = "sk-fake-openai",
            anthropic = "sk-fake-anthropic",
            google    = "sk-fake-google",
            groq      = "gsk-fake-groq",
        ))

    def test_falls_back_to_next_provider_on_rate_limit(self):
        # Force groq as primary; it hits a 429, google (next in the default
        # chain) should be tried automatically and succeed.
        with patch.object(ApiKeys, "is_ollama_available", return_value=False):
            with patch(
                "openpair.client.make_call",
                side_effect=[
                    Exception("429 RESOURCE_EXHAUSTED"),
                    ("ok from google", 5, 10, 100.0),
                ],
            ):
                result = self.client.call("Hello!", preferred_provider="groq")
        assert result.provider == "google"
        assert result.response_text == "ok from google"

    def test_non_retryable_error_raises_immediately_without_fallback(self):
        with patch.object(ApiKeys, "is_ollama_available", return_value=False):
            with patch(
                "openpair.client.make_call",
                side_effect=ValueError("invalid request: bad prompt"),
            ) as mock_call:
                with pytest.raises(ValueError, match="invalid request"):
                    self.client.call("Hello!", preferred_provider="groq")
        assert mock_call.call_count == 1

    def test_falls_back_to_ollama_when_all_cloud_providers_exhausted(self):
        with patch.object(ApiKeys, "is_ollama_available", return_value=True):
            with patch(
                "openpair.client.make_call",
                side_effect=[
                    Exception("429 rate limit"),   # groq
                    Exception("503 UNAVAILABLE"),  # google
                    Exception("429 rate limit"),   # openai
                    Exception("429 rate limit"),   # anthropic
                    ("ok from local model", 5, 10, 100.0),  # ollama
                ],
            ):
                result = self.client.call("Hello!", preferred_provider="groq")
        assert result.provider == "ollama"
        assert result.response_text == "ok from local model"
        assert result.cost_per_1k_input == 0.0

    def test_uses_ollama_when_no_cloud_keys_but_available(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY",    raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY",    raising=False)
        monkeypatch.delenv("GROQ_API_KEY",      raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        client = OpenPair(api_keys=ApiKeys())
        with patch.object(ApiKeys, "is_ollama_available", return_value=True):
            with patch(
                "openpair.client.make_call",
                return_value=("ok from local model", 5, 10, 100.0),
            ):
                result = client.call("Hello!")
        assert result.provider == "ollama"
        assert result.response_text == "ok from local model"

# Live tests moved to tests/test_live.py (@pytest.mark.live, real API calls).
