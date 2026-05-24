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

from typing import Optional, TYPE_CHECKING

from .config import ApiKeys
from .caller import make_call, CallResult

if TYPE_CHECKING:
    pass


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
    ) -> None:
        # Normalise api_keys input
        if isinstance(api_keys, dict):
            self._keys = ApiKeys(
                openai    = api_keys.get("openai"),
                anthropic = api_keys.get("anthropic"),
                google    = api_keys.get("google"),
            )
        elif isinstance(api_keys, ApiKeys):
            self._keys = api_keys
        else:
            self._keys = ApiKeys()  # reads from env

        self._preferred_provider = preferred_provider

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
    ) -> CallResult:
        """
        Route the prompt to the best model AND make the real API call.

        Args:
            prompt: The user's prompt.
            preferred_provider: Override routing to use a specific provider.
            system: System prompt / instructions for the model.
            max_tokens: Maximum tokens in the response.
            fallback_providers: List of providers to try if the primary has no key.
                                e.g. ["anthropic", "openai"] — tries in order.

        Returns:
            CallResult with response_text, token counts, cost, latency, and routing info.

        Raises:
            RuntimeError: If no API key is available for the routed provider.
            ValueError:   If an unknown provider is routed to.
        """
        provider = preferred_provider or self._preferred_provider

        # Get routing decision from Rust core
        decision = self._rust.route(prompt, provider)

        # Find a usable provider (primary → fallbacks)
        chosen_provider = self._resolve_provider(
            decision.provider,
            fallback_providers or [],
        )

        # If fallback changed the provider, re-route so model_id matches the new provider
        if chosen_provider != decision.provider:
            decision = self._rust.route(prompt, chosen_provider)

        api_key = self._keys.for_provider(chosen_provider)

        # Make the actual API call
        text, in_tok, out_tok, latency_ms = make_call(
            provider   = chosen_provider,
            model_id   = decision.model_id,
            prompt     = prompt,
            api_key    = api_key,  # type: ignore[arg-type]
            system     = system,
            max_tokens = max_tokens,
        )

        return CallResult(
            model_id          = decision.model_id,
            model_name        = decision.model_name,
            provider          = chosen_provider,
            tier              = decision.tier,
            complexity_score  = decision.complexity_score,
            routing_reason    = decision.reason,
            cost_per_1k_input = decision.cost_per_1k_input,
            response_text     = text,
            input_tokens      = in_tok,
            output_tokens     = out_tok,
            latency_ms        = latency_ms,
        )

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

    def _resolve_provider(self, primary: str, fallbacks: list[str]) -> str:
        """
        Find the first provider with a configured API key.
        Tries primary → fallbacks → raises RuntimeError if none available.
        """
        candidates = [primary] + [f for f in fallbacks if f != primary]
        for p in candidates:
            if self._keys.has(p):
                return p

        available = self._keys.available_providers()
        if available:
            return available[0]   # last resort: any available key

        raise RuntimeError(
            f"No API key found for any provider. "
            f"Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY, "
            f"or pass api_keys={{...}} to OpenPair()."
        )

    def __repr__(self) -> str:
        providers = self._keys.available_providers()
        pin = f", preferred='{self._preferred_provider}'" if self._preferred_provider else ""
        return f"OpenPair(keys={providers}{pin})"
