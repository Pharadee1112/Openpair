"""
Token streaming: provider streamers (fake SDK streams), the pre-first-chunk
fallback rule, and ChatSession.stream(). No network, no API keys.
"""

from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

from openpair import ApiKeys, ChatSession, OpenPair, caller
from openpair.caller import make_chat_stream

MSGS = [{"role": "user", "content": "hi"}]


def drain(gen):
    """Collect (chunks, return_value) from a generator."""
    chunks = []
    while True:
        try:
            chunks.append(next(gen))
        except StopIteration as stop:
            return chunks, stop.value


# ── fake SDKs ───────────────────────────────────────────────────────────────

def oa_chunk(text=None, usage=None, choices=True, x_groq=None):
    c = NS(choices=[NS(delta=NS(content=text))] if choices else [], usage=usage)
    if x_groq is not None:
        c.x_groq = x_groq
    return c


class FakeOpenAI:
    """Stand-in for openai.OpenAI; records create() kwargs."""
    last_kwargs = None
    chunks: list = []

    def __init__(self, **kw):
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kwargs):
        FakeOpenAI.last_kwargs = kwargs
        return iter(FakeOpenAI.chunks)


class FakeGemini:
    chunks: list = []

    def __init__(self, **kw):
        self.models = NS(generate_content_stream=lambda **k: iter(FakeGemini.chunks))


# ── provider shapes ─────────────────────────────────────────────────────────

class TestOpenAICompatStreams:
    @pytest.mark.parametrize("provider", ["groq", "ollama"])
    def test_chunks_none_delta_and_usage_chunk(self, provider):
        FakeOpenAI.chunks = [
            oa_chunk("Hel"),
            oa_chunk(None),                                   # None delta
            oa_chunk("lo"),
            oa_chunk(choices=False, usage=NS(prompt_tokens=7, completion_tokens=3)),  # no choices
        ]
        with patch("openai.OpenAI", FakeOpenAI):
            chunks, ret = drain(make_chat_stream(provider=provider, model_id="m", messages=MSGS, api_key="k"))
        assert chunks == ["Hel", "lo"]
        assert ret[:2] == (7, 3) and ret[2] >= 0
        assert FakeOpenAI.last_kwargs["stream"] is True
        assert FakeOpenAI.last_kwargs["stream_options"] == {"include_usage": True}

    def test_missing_usage_gives_zero_tokens(self):
        FakeOpenAI.chunks = [oa_chunk("a"), oa_chunk("b")]
        with patch("openai.OpenAI", FakeOpenAI):
            chunks, ret = drain(make_chat_stream(provider="ollama", model_id="m", messages=MSGS, api_key="k"))
        assert chunks == ["a", "b"] and ret[:2] == (0, 0)

    def test_groq_usage_under_x_groq(self):
        FakeOpenAI.chunks = [
            oa_chunk("a"),
            oa_chunk(None, x_groq=NS(usage=NS(prompt_tokens=4, completion_tokens=2))),
        ]
        with patch("openai.OpenAI", FakeOpenAI):
            _, ret = drain(make_chat_stream(provider="groq", model_id="m", messages=MSGS, api_key="k"))
        assert ret[:2] == (4, 2)


class TestGeminiStream:
    def test_chunks_none_text_and_final_usage(self):
        FakeGemini.chunks = [
            NS(text="Sa", usage_metadata=None),
            NS(text=None, usage_metadata=None),               # no text in this chunk
            NS(text="wat", usage_metadata=NS(prompt_token_count=5, candidates_token_count=2)),
        ]
        with patch("google.genai.Client", FakeGemini):
            chunks, ret = drain(make_chat_stream(provider="google", model_id="m", messages=MSGS, api_key="k"))
        assert chunks == ["Sa", "wat"] and ret[:2] == (5, 2)

    def test_missing_usage(self):
        FakeGemini.chunks = [NS(text="x", usage_metadata=None)]
        with patch("google.genai.Client", FakeGemini):
            _, ret = drain(make_chat_stream(provider="google", model_id="m", messages=MSGS, api_key="k"))
        assert ret[:2] == (0, 0)


class TestNonStreamingProvidersStillWork:
    @pytest.mark.parametrize("provider", ["openai", "anthropic", "openrouter"])
    def test_whole_reply_as_one_chunk(self, provider, monkeypatch):
        monkeypatch.setitem(caller._CALLERS, provider, lambda *a, **k: ("whole reply", 11, 22))
        chunks, ret = drain(make_chat_stream(provider=provider, model_id="m", messages=MSGS, api_key="k"))
        assert chunks == ["whole reply"] and ret[:2] == (11, 22)

    def test_unknown_provider(self):
        with pytest.raises(ValueError):
            drain(make_chat_stream(provider="nope", model_id="m", messages=MSGS, api_key="k"))


# ── fallback + history (ChatSession.stream) ─────────────────────────────────

@pytest.fixture(autouse=True)
def _no_local_ollama():
    with patch.object(ApiKeys, "is_ollama_available", return_value=False):
        yield


@pytest.fixture
def session():
    return ChatSession(OpenPair(api_keys=ApiKeys(google="sk-g", groq="gsk-g")))


def scripted(script):
    """
    make_chat_stream fake. `script` maps provider -> list of items (str chunks, or
    an Exception raised at that point). Records the providers that were opened.
    """
    opened = []

    def fake(*, provider, model_id, messages, api_key, system=None, max_tokens=2048):
        opened.append(provider)
        for item in script[provider]:
            if isinstance(item, BaseException):
                raise item
            yield item
        return 3, 4, 5.0

    fake.opened = opened
    return fake


RATE_LIMIT = RuntimeError("429 rate limit")


class TestFallbackRule:
    def test_fallback_when_first_provider_fails_before_any_chunk(self, session):
        fake = scripted({"groq": [RATE_LIMIT], "google": ["from ", "google"]})
        with patch("openpair.session.make_chat_stream", fake):
            chunks = list(session.stream("hi"))
        assert len(fake.opened) == 2
        assert "".join(chunks) == "from google"
        assert session.last_fallback_from == fake.opened[0]
        assert session.last_result.provider == fake.opened[1]
        assert session.last_result.response_text == "from google"

    def test_no_fallback_after_first_chunk(self, session):
        fake = scripted({"groq": ["partial ", RATE_LIMIT], "google": ["other"]})
        got = []
        with patch("openpair.session.make_chat_stream", fake):
            with pytest.raises(RuntimeError, match="429"):
                for chunk in session.stream("hi"):
                    got.append(chunk)
        assert len(fake.opened) == 1  # never tried the 2nd provider
        assert got == ["partial "]
        assert session.messages == [] and session.last_result is None

    def test_non_retryable_error_before_chunk_does_not_fall_back(self, session):
        fake = scripted({"groq": [ValueError("bad")], "google": ["x"]})
        with patch("openpair.session.make_chat_stream", fake):
            with pytest.raises(ValueError):
                list(session.stream("hi"))
        assert len(fake.opened) == 1


class TestHistory:
    def test_success_updates_history_and_last_result(self, session):
        fake = scripted({"groq": ["a", "b"], "google": ["a", "b"]})
        with patch("openpair.session.make_chat_stream", fake):
            assert list(session.stream("hi")) == ["a", "b"]
        assert session.messages == [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "ab"},
        ]
        r = session.last_result
        assert (r.input_tokens, r.output_tokens, r.latency_ms) == (3, 4, 5.0)
        assert session.last_fallback_from is None

    def test_cancel_leaves_history_unchanged(self, session):
        fake = scripted({"groq": ["a", "b", "c"], "google": ["a", "b", "c"]})
        with patch("openpair.session.make_chat_stream", fake):
            gen = session.stream("hi")
            assert next(gen) == "a"
            gen.close()
        assert session.messages == [] and session.last_result is None

    def test_failure_leaves_history_unchanged_and_next_turn_works(self, session):
        fake = scripted({"groq": [ValueError("x")], "google": ["ok"]})
        with patch("openpair.session.make_chat_stream", fake):
            with pytest.raises(ValueError):
                list(session.stream("one"))
            assert session.messages == []

    def test_second_turn_sends_first_turn(self, session):
        seen = []

        def fake(*, provider, model_id, messages, api_key, system=None, max_tokens=2048):
            seen.append([dict(m) for m in messages])
            yield "r"
            return 0, 0, 1.0

        with patch("openpair.session.make_chat_stream", fake):
            list(session.stream("one"))
            list(session.stream("two"))
        assert seen[1] == [
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "r"},
            {"role": "user", "content": "two"},
        ]

    def test_empty_text_rejected(self, session):
        with pytest.raises(ValueError):
            list(session.stream("   "))


class TestSendUnchanged:
    def test_send_still_uses_make_chat_call(self, session):
        with patch("openpair.session.make_chat_call", return_value=("full", 1, 2, 3.0)) as call, \
             patch("openpair.session.make_chat_stream") as stream:
            result = session.send("hi")
        assert result.response_text == "full"
        call.assert_called_once()
        stream.assert_not_called()
        assert session.last_result is None  # send() does not touch last_result
