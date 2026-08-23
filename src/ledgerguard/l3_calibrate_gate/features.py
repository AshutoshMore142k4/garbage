"""L3 feature extraction (plan.md #9, phases.md Phase 5 task 1).

Six named features, computed identically whether the decision came from L1's rules or L2's
model, so one calibrator can learn across both source layers. `model_self_rated_confidence` is
included as one feature among six -- never treated as the calibrated answer itself (phases.md:
"Do not calibrate on raw LLM token probabilities... the model's self-rating is one feature among
many, never the answer").
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ledgerguard.l0_normalize.normalize import normalize_timestamp
from ledgerguard.l1_deterministic.rules import narration_similarity_score
from ledgerguard.l1_deterministic.tolerance import MAX_SETTLEMENT_DAYS, MIN_SETTLEMENT_DAYS

FEATURE_NAMES = (
    "partial_rule_agreement_count",
    "absolute_amount_gap_paise",
    "date_skew_days",
    "narration_similarity_score",
    "candidate_set_size",
    "model_self_rated_confidence",
)


@dataclass
class DecisionInput:
    credit_paise: int
    narration: str
    value_date: str  # ISO-8601
    candidate_set_size: int
    chosen_net_paise: Optional[int]  # None if no candidate was chosen
    chosen_captured_at: Optional[str]  # ISO-8601; None if no candidate was chosen
    raw_confidence: float


def extract_features(d: DecisionInput) -> dict[str, float]:
    narration_score = narration_similarity_score(d.narration)

    if d.chosen_net_paise is None or d.chosen_captured_at is None:
        # Nothing was chosen -- the whole credit is "unexplained," so treat the gap as maximal
        # and there is no date to compare against.
        amount_gap = float(d.credit_paise)
        date_skew = 0.0
        agreement = 0
    else:
        amount_gap = float(abs(d.credit_paise - d.chosen_net_paise))
        value_date = normalize_timestamp(d.value_date)
        captured_at = normalize_timestamp(d.chosen_captured_at)
        date_skew = abs((value_date - captured_at).total_seconds()) / 86400
        agreement = sum(
            (
                amount_gap == 0,
                MIN_SETTLEMENT_DAYS <= date_skew <= MAX_SETTLEMENT_DAYS,
                narration_score >= 70,
            )
        )

    return {
        "partial_rule_agreement_count": float(agreement),
        "absolute_amount_gap_paise": amount_gap,
        "date_skew_days": date_skew,
        "narration_similarity_score": narration_score,
        "candidate_set_size": float(d.candidate_set_size),
        "model_self_rated_confidence": d.raw_confidence,
    }
