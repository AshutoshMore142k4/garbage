"""Free rapidfuzz-based fallback for when the budget guard trips or the API is unavailable
(plan.md #20). Degrades L2's resolution rate, never the system's availability -- it returns
the same `TriageResponse` shape as the real model path so L3 (Phase 5) can treat both
uniformly, and this is reported honestly rather than hidden (plan.md #20: "The system degrades
to rules+fuzzy... This is reported, not hidden.").
"""
from __future__ import annotations

from ledgerguard.l1_deterministic.rules import narration_similarity_score
from ledgerguard.models import TriageResponse

PLAUSIBILITY_THRESHOLD = 50.0
MAX_FALLBACK_CONFIDENCE = 0.6


def fallback_triage(narration: str, candidates: list[dict]) -> TriageResponse:
    if not candidates:
        return TriageResponse(candidate_id=None, confidence=0.0, evidence=["no candidates available"])

    score = narration_similarity_score(narration)
    if score < PLAUSIBILITY_THRESHOLD:
        return TriageResponse(
            candidate_id=None,
            confidence=0.0,
            evidence=[f"narration plausibility score {score:.0f} is below the fallback threshold"],
        )

    # The ledger carries no per-order narration to compare against (see l1's rules module
    # docstring), so this free path has no way to disambiguate between several candidates on
    # narration alone -- it can only confidently answer when the field has already narrowed
    # things to exactly one.
    if len(candidates) == 1:
        confidence = min(score / 100, MAX_FALLBACK_CONFIDENCE)
        return TriageResponse(
            candidate_id=candidates[0]["payment_id"],
            confidence=confidence,
            evidence=[f"single candidate, narration plausibility score {score:.0f}"],
        )

    return TriageResponse(
        candidate_id=None,
        confidence=0.0,
        evidence=[f"{len(candidates)} candidates; the fallback cannot disambiguate without the LLM"],
    )
