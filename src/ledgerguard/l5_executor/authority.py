"""The authority policy (plan.md #9, phases.md Phase 6 task 2).

`AUTO_POST` requires **all three**: the gate already said `AUTO_POST` (which itself already
encodes `calibrated_confidence >= threshold`), the amount is within `AUTHORITY_LIMIT_PAISE`, and
no anomaly was flagged. An anomaly always wins over everything else -- it forces `FLAG_ANOMALY`
even when the gate was confident, which is exactly what "an anomaly flag overrides a
high-confidence match" (phases.md Phase 6) means in code.
"""
from __future__ import annotations

from dataclasses import dataclass

AUTO_POST = "AUTO_POST"
ESCALATE = "ESCALATE"
FLAG_ANOMALY = "FLAG_ANOMALY"


@dataclass
class AuthorityInput:
    gate_action: str  # "AUTO_POST" | "ESCALATE", from l3_calibrate_gate.gate
    amount_paise: int
    authority_limit_paise: int
    has_anomaly: bool


def authorize(decision: AuthorityInput) -> str:
    if decision.has_anomaly:
        return FLAG_ANOMALY
    if decision.gate_action == AUTO_POST and decision.amount_paise <= decision.authority_limit_paise:
        return AUTO_POST
    return ESCALATE
