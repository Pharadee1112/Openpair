"""
OpenPair — Intelligent AI Router
==================================
Automatically routes prompts to the best AI model based on complexity,
language, provider preference, and cost.

Quick start:
    from openpair import OpenPair

    client = OpenPair()                          # reads API keys from env
    result = client.call("Explain black holes")  # route + call
    print(result.response_text)
    print(f"Used: {result.model_name} | Cost: ${result.estimated_cost:.5f}")

Routing only (no API call):
    decision = client.route("Write a Python class")
    print(decision.model_name, decision.tier, decision.complexity_score)
"""

from .client import OpenPair
from .config import ApiKeys
from .caller import CallResult

__version__ = "0.1.0"
__registry_snapshot__ = "2026-07-28"  # date the model prices/thai_score in src/registry.rs were last refreshed
__all__ = ["OpenPair", "ApiKeys", "CallResult", "__registry_snapshot__"]
