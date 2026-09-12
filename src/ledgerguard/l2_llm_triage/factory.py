"""Picks which LLM provider actually answers L2's residual triage, based on whichever credential
is present in `Settings`. `settings.llm_provider` forces a specific one; otherwise Anthropic wins
if multiple keys are set, since every doc, the pricing table, and PREREGISTRATION.md in this repo
were written against Claude specifically -- OpenAI/Gemini are equally-supported, not
equally-documented, alternatives for whoever runs the live experiment with a different key.

Returns `(client, label)`. `client` is `None` (and `label` explains why) when no usable
credential/SDK combination is available -- every caller degrades to the free fallback in that
case, never crashes.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from ledgerguard.config import Settings
from ledgerguard.l2_llm_triage.budget_guard import BudgetGuard

_PROVIDERS = ("anthropic", "openai", "gemini")


class _RetryingTriage:
    """Wraps a provider client's `.triage` with retry+backoff. A live key's free-tier quota
    (a handful of requests/minute is common) will otherwise abort a multi-call benchmark run on
    the very first 429 -- this is the difference between "the experiment finished slowly" and
    "the experiment didn't finish." Not budget-guard's job: that guard caps total *spend*, not
    transient provider-side throttling.
    """

    def __init__(self, client: Any, max_retries: int = 6, base_delay: float = 12.0) -> None:
        self._client = client
        self._max_retries = max_retries
        self._base_delay = base_delay

    def triage(self, bank_line: dict, candidates: list[dict]):
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                return self._client.triage(bank_line, candidates)
            except Exception as exc:
                last_exc = exc
                if attempt < self._max_retries - 1:
                    delay = self._base_delay * (attempt + 1)
                    print(f"    L2 call failed ({exc.__class__.__name__}); retrying in {delay:.0f}s...")
                    time.sleep(delay)
        raise last_exc  # type: ignore[misc]


def _build_anthropic(settings: Settings) -> tuple[Any, str]:
    import anthropic

    from ledgerguard.l2_llm_triage.client import TriageClient

    budget_guard = BudgetGuard(max_spend_usd=settings.max_spend_usd)
    client = TriageClient(
        messages_client=anthropic.Anthropic(api_key=settings.llm_api_key).messages,
        budget_guard=budget_guard,
    )
    return client, f"anthropic:{client._model}"


def _build_openai(settings: Settings) -> tuple[Any, str]:
    import openai

    from ledgerguard.l2_llm_triage.providers import OpenAITriageClient

    budget_guard = BudgetGuard(max_spend_usd=settings.max_spend_usd)
    client = OpenAITriageClient(
        client=openai.OpenAI(api_key=settings.openai_api_key),
        budget_guard=budget_guard,
        model=settings.openai_model,
    )
    return client, f"openai:{client._model}"


def _build_gemini(settings: Settings) -> tuple[Any, str]:
    import google.generativeai as genai

    from ledgerguard.l2_llm_triage.providers import GeminiTriageClient

    genai.configure(api_key=settings.gemini_api_key)
    budget_guard = BudgetGuard(max_spend_usd=settings.max_spend_usd)
    client = GeminiTriageClient(genai_module=genai, budget_guard=budget_guard, model=settings.gemini_model)
    return client, f"gemini:{client._model_name}"


_BUILDERS = {"anthropic": _build_anthropic, "openai": _build_openai, "gemini": _build_gemini}
_KEY_FIELD = {"anthropic": "llm_api_key", "openai": "openai_api_key", "gemini": "gemini_api_key"}


def build_triage_client(settings: Settings) -> tuple[Optional[Any], str]:
    forced = settings.llm_provider.strip().lower()
    order = [forced] if forced in _BUILDERS else []
    order += [p for p in _PROVIDERS if p not in order]

    tried = []
    for name in order:
        if not getattr(settings, _KEY_FIELD[name]):
            continue
        try:
            client, label = _BUILDERS[name](settings)
            return _RetryingTriage(client), label
        except Exception as exc:  # missing SDK, bad key shape, network -- try the next provider
            tried.append(f"{name} ({exc})")
            continue

    reason = "; ".join(tried) if tried else "no LLM_API_KEY/OPENAI_API_KEY/GEMINI_API_KEY set"
    return None, f"fallback_rapidfuzz [{reason}]"
