"""Thin FastAPI surface (plan.md #16). Phase 1 wires up only /healthz; every other route in
the spec (webhook receiver, batches, exceptions, audit stream) belongs to later phases and is
deliberately not implemented here.
"""
from __future__ import annotations

import json

from fastapi import FastAPI

import ledgerguard
from ledgerguard.l2_llm_triage.run import SPEND_STATE_PATH
from ledgerguard.models import HealthzResponse

app = FastAPI(title="LedgerGuard")


def _current_budget_spent_usd() -> float:
    """Reads the last L2 run's persisted spend (Phase 4's run.py writes it). Zero before any
    L2 run has ever happened -- this process doesn't track spend itself, since batch runs and
    the API server are separate processes in this phase (no shared in-memory state).
    """
    if not SPEND_STATE_PATH.exists():
        return 0.0
    try:
        return json.loads(SPEND_STATE_PATH.read_text(encoding="utf-8"))["last_run_spend_usd"]
    except (json.JSONDecodeError, KeyError, OSError):
        return 0.0


@app.get("/healthz", response_model=HealthzResponse)
def healthz() -> HealthzResponse:
    return HealthzResponse(
        ok=True,
        version=ledgerguard.__version__,
        budget_spent_usd=_current_budget_spent_usd(),
    )
