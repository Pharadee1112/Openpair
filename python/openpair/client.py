"""
openpair.client — Main OpenPair Client
========================================
Usage:
    from openpair import OpenPair

    client = OpenPair()                             # reads keys from env
    decision = client.route("What is Python?")      # routing only, no API call
    result   = client.call("What is Python?")       # route + real API call
"""

from __future__ import annotations

import types
from collections import OrderedDict
from dataclasses import replace
from typing import Optional, TYPE_CHECKING

from .config import ApiKeys
from .caller import make_call, CallResult
from .caller import is_loopback_url
from .errors import LocalModeError, is_retryable_error

if TYPE_CHECKING:
    pass


# Tried, in order, after the routed provider — before falling back to Ollama.
# Only providers with models in the Rust registry (Gemini + Groq since 2026-10-02).
_DEFAULT_FALLBACK_ORDER = ["groq", "google"]


class OpenPair:
    """
    Intelligent AI Router that automatically selects the best model for each prompt.

    Args:
        api_keys (ApiKeys | dict | None):
            API keys for each provider. If None, reads from environment variables:
            GOOGLE_API_KEY, GROQ_API_KEY
        preferred_provider (str | None):
            Pin to a specific provider: "google" | "groq"

    Examples:
        >>> client = OpenPair()
        >>> result = client.call("Explain quantum computing in simple terms")
        >>> print(result.response_text)
        >>> print(result.model_name, result.estimated_cost)
    """

    def __init__(
        self,
        api_keys: Optional[ApiKeys | dict] = None,
        preferred_provider: Optional[str] = None,
        cache_size: int = 128,
    ) -> None:
        # Normalise api_keys input
        if isinstance(api_keys, dict):
            self._keys = ApiKeys(
                openai    = api_keys.get("openai"),
                anthropic = api_keys.get("anthropic"),
                google    = api_keys.get("google"),
                groq      = api_keys.get("groq"),
                openrouter = api_keys.get("openrouter"),
            )
        elif isinstance(api_keys, ApiKeys):
            self._keys = api_keys
        else:
            self._keys = ApiKeys()  # reads from env

        self._preferred_provider = preferred_provider

        # In-memory LRU cache of (prompt, provider pin, system, max_tokens) -> CallResult.
        # Repeating the exact same call() args returns the cached response instead of
        # paying for another API call. Per-instance, not shared across OpenPair objects.
        self._cache_size: int = cache_size
        self._cache: "OrderedDict[tuple, CallResult]" = OrderedDict()

        # Lazy-import the Rust core (built by maturin)
        try:
            from openpair import _core as _rust
        except ImportError:
            raise ImportError(
                "openpair Rust core not found. Build it with:\n"
                "  pip install maturin\n"
                "  maturin develop"
            )
        self._rust = _rust

    # ── Public API ──────────────────────────────────────────────────────────

    def route(self, prompt: str, preferred_provider: Optional[str] = None):
        """
        Route a prompt to the best model WITHOUT making an API call.
        Returns a RoutingDecision with model_id, provider, tier, etc.

        Useful for inspecting routing decisions before committing to an API call.
        """
        provider = preferred_provider or self._preferred_provider
        return self._rust.route(prompt, provider)

    def call(
        self,
        prompt: str,
        *,
        preferred_provider: Optional[str] = None,
        system: Optional[str] = None,
        max_tokens: int = 2048,
        fallback_providers: Optional[list[str]] = None,
        use_cache: bool = True,
    ) -> CallResult:
        """
        Route the prompt to the best model AND make the real API call.

        Resilience: if a provider fails with a transient error (429 rate limit
        / quota exhausted, 503 overloaded), automatically retries the same
        prompt against the next provider in the fallback chain instead of
        raising immediately. Default chain (when `fallback_providers` isn't
        given): routed provider → groq → google → Ollama. A provider with no
        model in the registry (e.g. "openai") is skipped even if it has a key.
        Ollama is always tried last, and only if a local server is actually
        reachable — it's the fallback of last resort for when every cloud
        provider is rate-limited, or when no cloud API key is configured at
        all but Ollama happens to be running.

        Args:
            prompt: The user's prompt.
            preferred_provider: Override routing to use a specific provider.
            system: System prompt / instructions for the model.
            max_tokens: Maximum tokens in the response.
            fallback_providers: Explicit override for the fallback order
                                e.g. ["anthropic", "openai"] — tries in order.
                                Ollama is still appended last if available.
            use_cache: If True (default), an exact repeat of the same
                       (prompt, preferred_provider, system, max_tokens) skips
                       the API call entirely and returns the cached CallResult
                       (with `from_cache=True`, `estimated_cost` reported as 0).
                       Pass False to force a fresh call.

        Returns:
            CallResult with response_text, token counts, cost, latency, and routing info.

        Raises:
            RuntimeError: If no provider in the chain has a usable key.
            Exception:    Whatever the last provider tried raised, if it wasn't
                          a transient error (or retries were exhausted).
        """
        provider = preferred_provider or self._preferred_provider

        cache_key = (prompt, provider, system, max_tokens)
        if use_cache and cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return replace(self._cache[cache_key], from_cache=True)

        def dispatch(candidate: str, model_id: str, api_key: str):
            return make_call(
                provider   = candidate,
                model_id   = model_id,
                prompt     = prompt,
                api_key    = api_key,
                system     = system,
                max_tokens = max_tokens,
            )

        result, _failed = self._call_with_fallback(
            route_prompt       = prompt,
            preferred_provider = provider,
            fallback_providers = fallback_providers,
            dispatch           = dispatch,
        )

        if use_cache:
            self._cache[cache_key] = result
            self._cache.move_to_end(cache_key)
            if len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)

        return result

    def available_providers(self) -> list[str]:
        """Return providers that have API keys configured."""
        return self._keys.available_providers()

    def score(self, prompt: str) -> int:
        """Return the complexity score (1–10) for a prompt."""
        return self._rust.score_complexity(prompt)

    def is_thai(self, text: str) -> bool:
        """Return True if the text contains Thai characters."""
        return self._rust.is_thai(text)

    # ── Internal helpers ────────────────────────────────────────────────────

    def _call_with_fallback(
        self,
        *,
        route_prompt: str,
        preferred_provider: Optional[str],
        fallback_providers: Optional[list[str]],
        dispatch,
        local_only: bool = False,
        no_fallback: bool = False,
    ) -> tuple[CallResult, list[str]]:
        """
        Route `route_prompt`, then walk the fallback chain until one provider answers.
        Shared by call() (single prompt) and ChatSession.send() (multi-turn).

        `dispatch(provider, model_id, api_key)` makes the real API call and returns
        (text, input_tokens, output_tokens, latency_ms); it decides what is sent
        (a prompt or a message history). This method never touches the response cache.

        Returns (result, failed) where `failed` lists the providers that raised a
        retryable error before the one that answered, in the order they were tried.
        Raises exactly as documented on call().
        """
        last_error: Optional[Exception] = None
        failed: list[str] = []

        for candidate, cdec, api_key, can_fall_back in self._candidates(
            route_prompt, preferred_provider, fallback_providers, local_only, no_fallback
        ):
            try:
                text, in_tok, out_tok, latency_ms = dispatch(candidate, cdec.model_id, api_key)
            except Exception as e:
                last_error = e
                if is_retryable_error(e) and can_fall_back:
                    failed.append(candidate)
                    continue
                raise

            return self._build_result(candidate, cdec, text, in_tok, out_tok, latency_ms), failed

        raise last_error  # type: ignore[misc]

    def _stream_with_fallback(
        self,
        *,
        route_prompt: str,
        preferred_provider: Optional[str],
        fallback_providers: Optional[list[str]],
        open_stream,
        local_only: bool = False,
        no_fallback: bool = False,
    ):
        """
        Streaming twin of _call_with_fallback, as a generator: yields text chunks and
        returns (result, failed) when the stream completes.

        `open_stream(provider, model_id, api_key)` returns a generator that yields
        text chunks and returns (input_tokens, output_tokens, latency_ms).

        Fallback rule: a provider may be replaced by the next one ONLY if it failed
        with a retryable error before the first chunk was yielded. Once any text has
        been yielded the error is raised, so two providers' text never mixes in one reply.
        """
        last_error: Optional[Exception] = None
        failed: list[str] = []

        for candidate, cdec, api_key, can_fall_back in self._candidates(
            route_prompt, preferred_provider, fallback_providers, local_only, no_fallback
        ):
            emitted = False
            inner = open_stream(candidate, cdec.model_id, api_key)
            parts: list[str] = []
            try:
                while True:
                    try:
                        chunk = next(inner)
                    except StopIteration as stop:
                        in_tok, out_tok, latency_ms = stop.value
                        break
                    emitted = True
                    parts.append(chunk)
                    yield chunk
            except Exception as e:
                last_error = e
                if not emitted and is_retryable_error(e) and can_fall_back:
                    failed.append(candidate)
                    continue
                raise
            finally:
                inner.close()  # also runs when the consumer cancels (GeneratorExit)

            return self._build_result(candidate, cdec, "".join(parts), in_tok, out_tok, latency_ms), failed

        raise last_error  # type: ignore[misc]

    def _candidates(self, route_prompt, preferred_provider, fallback_providers, local_only=False,
                    no_fallback=False):
        """
        Route `route_prompt` and yield (provider, decision, api_key, can_fall_back)
        for each usable provider in the fallback chain, in order. `can_fall_back` is
        True when another provider follows in the chain. Raises RuntimeError if
        no provider is usable at all (no key / no model).

        With `local_only` the chain is restricted to Ollama alone: cloud keys are never
        looked at, there is no fallback, and the Ollama URL must be a loopback address.
        The URL is read once (ApiKeys.ollama_base_url) and the same value is used for
        the availability check here and (via local_ollama_url) for the call itself.

        With `no_fallback` the chain is ONLY the pinned provider (`preferred_provider`):
        no other provider is ever yielded, so nothing can be sent anywhere else. If the
        pinned provider has no key or no model, RuntimeError is raised.
        """
        if local_only:
            url = self.local_ollama_url()
            if not is_loopback_url(url):
                raise LocalModeError(
                    f"Local mode is on: refusing Ollama URL {url!r} because it is not a "
                    f"loopback address (localhost, 127.0.0.1 or ::1)."
                )
            if not self._keys.is_ollama_available():
                raise LocalModeError(f"Ollama was not reachable at {url}")
            primary = self._rust.route(route_prompt, "ollama")
            yield "ollama", self._decision_for("ollama", route_prompt, primary), "local", False
            return

        provider = preferred_provider or self._preferred_provider
        decision = self._rust.route(route_prompt, provider)

        if no_fallback:
            chain = [provider or decision.provider]
        else:
            chain = self._build_fallback_chain(decision.provider, fallback_providers)
        attempted = False

        for i, candidate in enumerate(chain):
            api_key = self._keys.for_provider(candidate)
            if not api_key:
                continue

            candidate_decision = self._decision_for(candidate, route_prompt, decision)
            if candidate_decision.provider != candidate:
                # The registry has no model for this provider — routing fell back to
                # another provider's model, which this provider's API can't serve.
                continue
            attempted = True
            yield candidate, candidate_decision, api_key, i < len(chain) - 1

        if not attempted:
            raise RuntimeError(
                f"No API key found for any provider. "
                f"Set GOOGLE_API_KEY or GROQ_API_KEY, "
                f"run Ollama locally, or pass api_keys={{...}} to OpenPair()."
            )

    def local_ollama_url(self) -> str:
        """The Ollama base URL, read once from ApiKeys (env / .env / argument)."""
        return self._keys.ollama_base_url

    @staticmethod
    def _build_result(candidate, cdec, text, in_tok, out_tok, latency_ms) -> CallResult:
        return CallResult(
            model_id          = cdec.model_id,
            model_name        = cdec.model_name,
            provider          = candidate,
            tier              = cdec.tier,
            complexity_score  = cdec.complexity_score,
            routing_reason    = cdec.reason,
            cost_per_1k_input = cdec.cost_per_1k_input,
            response_text     = text,
            input_tokens      = in_tok,
            output_tokens     = out_tok,
            latency_ms        = latency_ms,
        )

    def _build_fallback_chain(self, primary: str, explicit_fallbacks: Optional[list[str]]) -> list[str]:
        """
        Ordered list of providers to attempt: primary, then the fallback
        order (explicit override or the default groq/google chain), then Ollama last — only if its local server is reachable.
        """
        if explicit_fallbacks:
            chain = [primary] + [p for p in explicit_fallbacks if p != primary]
        else:
            chain = [primary] + [p for p in _DEFAULT_FALLBACK_ORDER if p != primary]

        if "ollama" not in chain and self._keys.is_ollama_available():
            chain.append("ollama")

        return chain

    def _decision_for(self, candidate: str, prompt: str, primary_decision):
        """
        Routing info for `candidate`. Ollama isn't in the Rust registry (its
        model catalog is whatever the user has pulled locally, not a fixed
        cost/tier the router can reason about) so it's synthesized here
        instead of going through `self._rust.route()`.
        """
        if candidate == "ollama":
            return types.SimpleNamespace(
                model_id          = self._keys.ollama_model,
                model_name        = f"Ollama ({self._keys.ollama_model})",
                provider          = "ollama",
                tier              = primary_decision.tier,
                complexity_score  = primary_decision.complexity_score,
                reason            = f"{primary_decision.reason} — local fallback via Ollama",
                cost_per_1k_input = 0.0,
            )
        if candidate == primary_decision.provider:
            return primary_decision
        return self._rust.route(prompt, candidate)

    def __repr__(self) -> str:
        providers = self._keys.available_providers()
        pin = f", preferred='{self._preferred_provider}'" if self._preferred_provider else ""
        return f"OpenPair(keys={providers}{pin})"
