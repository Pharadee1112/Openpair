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
from .errors import is_retryable_error

if TYPE_CHECKING:
    pass


# Tried, in order, after the routed provider — before falling back to Ollama.
_DEFAULT_FALLBACK_ORDER = ["groq", "google", "openai", "anthropic"]


class OpenPair:
    """
    Intelligent AI Router that automatically selects the best model for each prompt.

    Args:
        api_keys (ApiKeys | dict | None):
            API keys for each provider. If None, reads from environment variables:
            OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY
        preferred_provider (str | None):
            Pin to a specific provider: "openai" | "anthropic" | "google"

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
        given): routed provider → groq → google → openai → anthropic → Ollama.
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

        decision = self._rust.route(prompt, provider)

        chain = self._build_fallback_chain(decision.provider, fallback_providers)

        last_error: Optional[Exception] = None
        attempted = False

        for i, candidate in enumerate(chain):
            api_key = self._keys.for_provider(candidate)
            if not api_key:
                continue
            attempted = True

            candidate_decision = self._decision_for(candidate, prompt, decision)

            try:
                text, in_tok, out_tok, latency_ms = make_call(
                    provider   = candidate,
                    model_id   = candidate_decision.model_id,
                    prompt     = prompt,
                    api_key    = api_key,  # type: ignore[arg-type]
                    system     = system,
                    max_tokens = max_tokens,
                )
            except Exception as e:
                last_error = e
                if is_retryable_error(e) and i < len(chain) - 1:
                    continue
                raise

            result = CallResult(
                model_id          = candidate_decision.model_id,
                model_name        = candidate_decision.model_name,
                provider          = candidate,
                tier              = candidate_decision.tier,
                complexity_score  = candidate_decision.complexity_score,
                routing_reason    = candidate_decision.reason,
                cost_per_1k_input = candidate_decision.cost_per_1k_input,
                response_text     = text,
                input_tokens      = in_tok,
                output_tokens     = out_tok,
                latency_ms        = latency_ms,
            )

            if use_cache:
                self._cache[cache_key] = result
                self._cache.move_to_end(cache_key)
                if len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)

            return result

        if not attempted:
            raise RuntimeError(
                f"No API key found for any provider. "
                f"Set OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, or GROQ_API_KEY, "
                f"run Ollama locally, or pass api_keys={{...}} to OpenPair()."
            )
        raise last_error  # type: ignore[misc]

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

    def _build_fallback_chain(self, primary: str, explicit_fallbacks: Optional[list[str]]) -> list[str]:
        """
        Ordered list of providers to attempt: primary, then the fallback
        order (explicit override or the default groq/google/openai/anthropic
        chain), then Ollama last — only if its local server is reachable.
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
