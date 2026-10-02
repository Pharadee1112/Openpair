"""
openpair.config — API key management
=====================================
Loads API keys from (in order of priority):
  1. Keys passed directly to OpenPair(api_keys={...})
  2. Environment variables: OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, GROQ_API_KEY,
     OPENROUTER_API_KEY
  3. .env file in the current directory (via python-dotenv)
"""

from __future__ import annotations

import os
import urllib.request
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
        openai:       Optional[str] = None,
        anthropic:    Optional[str] = None,
        google:       Optional[str] = None,
        groq:         Optional[str] = None,
        openrouter:   Optional[str] = None,
        ollama_base_url: Optional[str] = None,
        ollama_model:    Optional[str] = None,
    ) -> None:
        self.openai    = openai    or os.getenv("OPENAI_API_KEY")
        self.anthropic = anthropic or os.getenv("ANTHROPIC_API_KEY")
        self.google    = google    or os.getenv("GOOGLE_API_KEY")
        self.groq      = groq      or os.getenv("GROQ_API_KEY")
        self.openrouter = openrouter or os.getenv("OPENROUTER_API_KEY")

        # Ollama doesn't use an API key — "available" means the local server responds.
        self.ollama_base_url = ollama_base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model    = ollama_model    or os.getenv("OLLAMA_MODEL", "llama3.1")

    def is_ollama_available(self, timeout: float = 1.0) -> bool:
        """Ping the local Ollama server — False if it isn't running."""
        try:
            urllib.request.urlopen(f"{self.ollama_base_url}/api/tags", timeout=timeout)
            return True
        except Exception:
            return False

    def for_provider(self, provider: str) -> Optional[str]:
        """Return the key for a given provider name. Ollama has no key — returns a truthy placeholder when its server is reachable."""
        if provider == "ollama":
            return "local" if self.is_ollama_available() else None
        return {
            "openai":    self.openai,
            "anthropic": self.anthropic,
            "google":    self.google,
            "groq":      self.groq,
            "openrouter": self.openrouter,
        }.get(provider)

    def has(self, provider: str) -> bool:
        """Return True if a key exists for this provider."""
        return bool(self.for_provider(provider))

    def available_providers(self) -> list[str]:
        """List providers that have a key configured."""
        return [p for p in ("openai", "anthropic", "google", "groq", "openrouter") if self.has(p)]

    def __repr__(self) -> str:
        def mask(k: Optional[str]) -> str:
            return f"{k[:8]}..." if k else "—"
        return (
            f"ApiKeys(openai={mask(self.openai)}, "
            f"anthropic={mask(self.anthropic)}, "
            f"google={mask(self.google)}, "
            f"groq={mask(self.groq)}, "
            f"openrouter={mask(self.openrouter)})"
        )
