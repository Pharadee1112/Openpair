"""
Tests proving the Ollama fallback path works end-to-end without a real
Ollama server, using the `fake_ollama` fixture (see tests/conftest.py).
Run with: pytest tests/test_ollama_fallback.py -v
"""

from openpair import OpenPair
from openpair.caller import call_ollama
from openpair.config import ApiKeys
from openpair import caller


class TestCallOllamaDirect:
    """Unit tests of caller.call_ollama() itself, against the fake client."""

    def test_returns_parsed_response(self, fake_ollama):
        fake_ollama.response_text = "สวัสดีจาก Ollama"
        fake_ollama.prompt_tokens = 5
        fake_ollama.completion_tokens = 9

        text, in_tok, out_tok = call_ollama(
            model_id="llama3.1",
            prompt="สวัสดี",
            api_key="ollama",
        )

        assert text == "สวัสดีจาก Ollama"
        assert in_tok == 5
        assert out_tok == 9

    def test_sends_system_prompt_and_max_tokens(self, fake_ollama):
        call_ollama(
            model_id="llama3.1",
            prompt="Hi",
            api_key="ollama",
            system="Be terse.",
            max_tokens=64,
        )

        [call] = fake_ollama.calls
        assert call["model"] == "llama3.1"
        assert call["max_tokens"] == 64
        assert call["messages"][0] == {"role": "system", "content": "Be terse."}
        assert call["messages"][1] == {"role": "user", "content": "Hi"}

    def test_uses_local_base_url_by_default(self, monkeypatch, fake_ollama):
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        call_ollama(model_id="llama3.1", prompt="Hi", api_key="ollama")

        [kwargs] = fake_ollama.client_kwargs
        assert kwargs["base_url"] == "http://localhost:11434/v1"
        assert kwargs["api_key"] == "ollama"


class TestClientFallsBackToOllama:
    """
    Integration tests through OpenPair.call() -> the real make_call()
    dispatcher -> the real call_ollama() -> the fake HTTP layer. Only cloud
    provider callers are stubbed to fail; Ollama's code path is untouched,
    so a bug in the real fallback wiring would surface here.
    """

    def _fail_cloud_providers(self, monkeypatch):
        def _raise(*_args, **_kwargs):
            raise Exception("429 rate limit")

        for provider in ("openai", "anthropic", "google", "groq"):
            monkeypatch.setitem(caller._CALLERS, provider, _raise)

    def test_falls_back_to_ollama_when_no_cloud_keys(self, monkeypatch, fake_ollama):
        for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY"):
            monkeypatch.delenv(var, raising=False)
        fake_ollama.response_text = "local model reply"

        client = OpenPair(api_keys=ApiKeys())
        result = client.call("Hello!")

        assert result.provider == "ollama"
        assert result.response_text == "local model reply"
        assert result.cost_per_1k_input == 0.0
        assert len(fake_ollama.calls) == 1

    def test_falls_back_to_ollama_after_all_cloud_providers_rate_limited(self, monkeypatch, fake_ollama):
        self._fail_cloud_providers(monkeypatch)
        fake_ollama.response_text = "rescued by ollama"

        client = OpenPair(api_keys=ApiKeys(
            openai="sk-fake", anthropic="sk-fake", google="sk-fake", groq="gsk-fake",
        ))
        result = client.call("Hello!")

        assert result.provider == "ollama"
        assert result.response_text == "rescued by ollama"
        assert len(fake_ollama.calls) == 1

    def test_does_not_use_ollama_when_a_cloud_provider_succeeds(self, monkeypatch, fake_ollama):
        # groq/google/openai fail; anthropic (last in the default chain)
        # succeeds before Ollama is ever reached. All four are stubbed here
        # (rather than hitting real provider SDKs) — only Ollama's code path
        # is under test.
        def _raise(*_args, **_kwargs):
            raise Exception("429 rate limit")

        def _succeed(*_args, **_kwargs):
            return "ok from anthropic", 5, 10

        monkeypatch.setitem(caller._CALLERS, "groq", _raise)
        monkeypatch.setitem(caller._CALLERS, "google", _raise)
        monkeypatch.setitem(caller._CALLERS, "openai", _raise)
        monkeypatch.setitem(caller._CALLERS, "anthropic", _succeed)

        client = OpenPair(api_keys=ApiKeys(
            openai="sk-fake", anthropic="sk-fake", google="sk-fake", groq="gsk-fake",
        ))
        result = client.call("Hello!", preferred_provider="groq")

        assert result.provider == "anthropic"
        assert fake_ollama.calls == []
