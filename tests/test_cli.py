"""
Tests for openpair.cli — the `openpair` command-line entry point.
Run with: pytest tests/test_cli.py -v
"""

from unittest.mock import patch

import pytest

from openpair.cli import main
from openpair.config import ApiKeys


@pytest.fixture(autouse=True)
def clear_cloud_keys(monkeypatch):
    """Isolate every test from real .env keys so routing/fallback is deterministic."""
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)


class TestRouteOnly:
    def test_prints_routing_decision(self, capsys):
        exit_code = main(["Hello!", "--route-only"])
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "Model:" in out
        assert "Provider:" in out
        assert "Tier:" in out
        assert "Score:" in out
        assert "Reason:" in out

    def test_does_not_call_the_api(self, capsys):
        with patch("openpair.client.make_call") as mock_call:
            main(["Hello!", "--route-only"])
        mock_call.assert_not_called()

    def test_respects_provider_flag(self, capsys):
        with patch.object(ApiKeys, "is_ollama_available", return_value=False):
            main(["Hello!", "--route-only", "--provider", "groq"])
        out = capsys.readouterr().out
        assert "Provider: groq" in out


class TestCall:
    def test_successful_call_prints_response(self, capsys, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk-fake-key")
        with patch(
            "openpair.client.make_call",
            return_value=("Mocked reply", 10, 20, 150.0),
        ):
            exit_code = main(["Hello!", "--provider", "groq"])
        captured = capsys.readouterr()

        assert exit_code == 0
        assert "Mocked reply" in captured.out
        assert "groq" in captured.err
        assert "tok" in captured.err

    def test_passes_system_and_max_tokens_through(self, capsys, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk-fake-key")
        with patch(
            "openpair.client.make_call",
            return_value=("ok", 1, 1, 1.0),
        ) as mock_call:
            main([
                "Hello!",
                "--provider", "groq",
                "--system", "Be terse.",
                "--max-tokens", "64",
            ])
        _, kwargs = mock_call.call_args
        assert kwargs["system"] == "Be terse."
        assert kwargs["max_tokens"] == 64

    def test_no_api_keys_prints_error_and_returns_1(self, capsys):
        with patch.object(ApiKeys, "is_ollama_available", return_value=False):
            exit_code = main(["Hello!"])
        captured = capsys.readouterr()

        assert exit_code == 1
        assert "Error:" in captured.err
        assert "No API key" in captured.err
        assert captured.out == ""


class TestArgParsing:
    def test_missing_prompt_exits_nonzero(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code != 0

    def test_default_max_tokens_is_2048(self, capsys, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk-fake-key")
        with patch(
            "openpair.client.make_call",
            return_value=("ok", 1, 1, 1.0),
        ) as mock_call:
            main(["Hello!", "--provider", "groq"])
        _, kwargs = mock_call.call_args
        assert kwargs["max_tokens"] == 2048
