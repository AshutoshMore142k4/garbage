"""The abstention gate (plan.md #9, phases.md Phase 5 task 4). A decision only ever reaches
AUTO_POST by clearing a cost-derived threshold -- never by raw confidence, and never below the
threshold, regardless of what upstream layer produced it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

AUTO_POST = "AUTO_POST"
ESCALATE = "ESCALATE"

# phases.md Phase 5's closed reason-code enum (also src/ledgerguard/models.py's ReasonCode).
AMBIGUOUS_NARRATION_MULTI_CANDIDATE = "AMBIGUOUS_NARRATION_MULTI_CANDIDATE"


@dataclass
class GateInput:
    has_candidate: bool  # did L1/L2 propose a specific order-group at all?
    calibrated_confidence: float
    existing_reason_code: Optional[str]  # already set by L1/L2 if it escalated with no candidate


@dataclass
class GateOutcome:
    action: str
    reason_code: Optional[str]


def gate(decision: GateInput, threshold: float) -> GateOutcome:
    if decision.has_candidate and decision.calibrated_confidence >= threshold:
        return GateOutcome(action=AUTO_POST, reason_code=None)

    if decision.existing_reason_code is not None:
        # L1/L2 already had a specific reason for finding no candidate at all -- preserve it.
        return GateOutcome(action=ESCALATE, reason_code=decision.existing_reason_code)

    # A candidate was proposed but didn't clear the bar -- plan.md's own worked example (#8 J2:
    # "Calibrated confidence 0.62, threshold 0.94") uses this exact reason code for precisely
    # this situation, so it's reused here rather than inventing a new one outside the closed enum.
    return GateOutcome(action=ESCALATE, reason_code=AMBIGUOUS_NARRATION_MULTI_CANDIDATE)
