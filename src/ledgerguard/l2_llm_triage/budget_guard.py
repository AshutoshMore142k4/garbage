"""Running spend counter with a hard cap (plan.md #20's budget_guard.py).

Aborts loudly on breach -- it never silently continues or silently degrades. Degradation is
fallback.py's job, and it only ever kicks in because this guard raised, not because it
swallowed an overage quietly (phases.md Phase 4: "exceeding cap aborts, does not silently
continue").
"""
from __future__ import annotations


class BudgetExhaustedError(RuntimeError):
    """Raised when a call would push cumulative L2 spend over the configured cap."""


class BudgetGuard:
    def __init__(self, max_spend_usd: float):
        self.max_spend_usd = max_spend_usd
        self.spent_usd = 0.0

    def check(self, projected_usd: float) -> None:
        """Raise if adding `projected_usd` to spend-so-far would breach the cap, without
        committing the spend. Used as a pre-flight gate before a call is made.
        """
        if self.spent_usd + projected_usd > self.max_spend_usd:
            raise BudgetExhaustedError(
                f"L2 call would reach ${self.spent_usd + projected_usd:.4f} of the "
                f"${self.max_spend_usd:.2f} cap"
            )

    def charge(self, usd: float) -> None:
        """Commit real spend after a call completes. Re-checks the cap as defense in depth."""
        self.check(usd)
        self.spent_usd += usd
