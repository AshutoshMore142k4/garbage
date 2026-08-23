"""Thin FastAPI surface (plan.md #16). Phase 1 wires up only /healthz; every other route in
the spec (webhook receiver, batches, exceptions, audit stream) belongs to later phases and is
deliberately not implemented here.
"""
from __future__ import annotations

from fastapi import FastAPI

import ledgerguard
from ledgerguard.models import HealthzResponse

app = FastAPI(title="LedgerGuard")

# Running spend counter. Phase 4's budget_guard.py will own real accounting against
# MAX_SPEND_USD; until L2 exists nothing spends, so this is honestly always zero.
_budget_spent_usd = 0.0


@app.get("/healthz", response_model=HealthzResponse)
def healthz() -> HealthzResponse:
    return HealthzResponse(
        ok=True,
        version=ledgerguard.__version__,
        budget_spent_usd=_budget_spent_usd,
    )
