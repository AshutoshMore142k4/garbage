"""Expected-cost-driven threshold selection (plan.md #9/#19, phases.md Phase 5 task 3/4).

The gate's threshold is picked by minimizing expected cost, not by maximizing accuracy
(phases.md is explicit about this). Two cost terms, both documented assumptions rather than
measured figures -- plan.md gives no real-world number for either, so these are flagged here
for whoever tunes them against real analyst time/loss data later:

- A false AUTO_POST (posted, but wrong) costs the full credit amount -- the money genuinely put
  in the wrong place. This is not a guess about severity; it is definitionally the size of the
  misallocation.
- An ESCALATE costs a fixed, small "analyst review" fee, `ESCALATION_COST_PAISE`, regardless of
  whether the escalated case would have been correct to auto-post. Not tuned to any observed
  analyst cost -- reasonable to argue this constant should live in config.py once someone can
  measure it.
"""
from __future__ import annotations

from dataclasses import dataclass

ESCALATION_COST_PAISE = 5_000  # placeholder: (Rs.)50 flat, documented assumption above


@dataclass
class CostDecision:
    credit_paise: int
    calibrated_confidence: float
    correct: bool


def expected_cost_paise(threshold: float, decisions: list[CostDecision]) -> int:
    total = 0
    for d in decisions:
        if d.calibrated_confidence >= threshold:
            if not d.correct:
                total += d.credit_paise
            # correct auto-post: zero cost
        else:
            total += ESCALATION_COST_PAISE
    return total


def find_optimal_threshold(decisions: list[CostDecision], grid_step: float = 0.01) -> float:
    """Grid search over (0, 1) -- a simple, deterministic, easily-tested 1-D minimization; the
    cost function need not be smooth or convex, so a closed-form solution isn't assumed.
    """
    if not decisions:
        raise ValueError("find_optimal_threshold needs at least one decision")

    best_threshold = 0.5
    best_cost = None
    steps = int(round(1.0 / grid_step))
    for i in range(steps + 1):
        threshold = i * grid_step
        cost = expected_cost_paise(threshold, decisions)
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best_threshold = threshold
    return best_threshold
