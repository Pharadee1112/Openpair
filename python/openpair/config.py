"""
openpair.config — API key management
=====================================
Loads API keys from (in order of priority):
  1. Keys passed directly to OpenPair(api_keys={...})
  2. Environment variables: OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, GROQ_API_KEY
  3. .env file in the current directory (via python-dotenv)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# Try to load .env from cwd if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(Path.cwd() / ".env", override=False)
except ImportError:
    pass  # dotenv optional — env vars still work


class ApiKeys:
    """Container for API keys for each provider."""

    def __init__(
        self,
        openai:    Optional[str] = None,
        anthropic: Optional[str] = None,
        google:    Optional[str] = None,
        groq:      Optional[str] = None,
    ) -> None:
        self.openai    = openai    or os.getenv("OPENAI_API_KEY")
        self.anthropic = anthropic or os.getenv("ANTHROPIC_API_KEY")
        self.google    = google    or os.getenv("GOOGLE_API_KEY")
        self.groq      = groq      or os.getenv("GROQ_API_KEY")

    def for_provider(self, provider: str) -> Optional[str]:
        """Return the key for a given provider name."""
        return {
            "openai":    self.openai,
            "anthropic": self.anthropic,
            "google":    self.google,
            "groq":      self.groq,
        }.get(provider)

    def has(self, provider: str) -> bool:
        """Return True if a key exists for this provider."""
        return bool(self.for_provider(provider))

    def available_providers(self) -> list[str]:
        """List providers that have a key configured."""
        return [p for p in ("openai", "anthropic", "google", "groq") if self.has(p)]

    def __repr__(self) -> str:
        def mask(k: Optional[str]) -> str:
            return f"{k[:8]}..." if k else "—"
        return (
            f"ApiKeys(openai={mask(self.openai)}, "
            f"anthropic={mask(self.anthropic)}, "
            f"google={mask(self.google)}, "
            f"groq={mask(self.groq)})"
        )
