"""The FastAPI surface (plan.md #16). Deliberately small: six endpoints, enough to drive the
whole demo and nothing more.

Deployment split: this runs on a container host (see `render.yaml`), not on the frontend's
static host. The project's dependency set measures ~320 MB installed, well past a serverless
platform's 250 MB ceiling -- so rather than shipping a stripped-down reimplementation, the API
runs the *actual* pipeline and the frontend is deployed separately against it.

Every response carries `data_provenance`. `REAL_VS_SIMULATED.md` records that no session in this
project has ever had Razorpay credentials or network egress; the pipeline is real, the data is
synthetic, and the interface says so rather than implying a live payment connection.
"""
from __future__ import annotations

import json
import os

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import ledgerguard
from ledgerguard.api.schemas import (
    DATA_PROVENANCE,
    AuditResponse,
    DashboardResponse,
    ExecuteResponse,
    InvestigationResponse,
    ReconciliationListResponse,
)
from ledgerguard.api.service import BATCH_ID, get_state
from ledgerguard.l2_llm_triage.run import SPEND_STATE_PATH
from ledgerguard.models import HealthzResponse

app = FastAPI(
    title="LedgerGuard",
    description="Reconciliation controller with a calibrated abstention gate. "
    f"{DATA_PROVENANCE}.",
    version=ledgerguard.__version__,
)

# The frontend is served from a different origin, so the browser needs this. `ALLOWED_ORIGINS`
# is an exact-match allowlist (comma-separated) -- set it to the real deployed frontend URL(s)
# once known, e.g. `ALLOWED_ORIGINS=https://ledgerguard.vercel.app`.
#
# The regex defaults to local development only (`vite dev`'s :5173, `vite preview`'s :4173, and
# both `localhost`/`127.0.0.1`, which are *different origins* to a browser). It previously also
# matched *any* `https://*.vercel.app`, which means any attacker's own Vercel deployment could
# call this API from a browser -- narrowed here to an explicit opt-in via
# `ALLOWED_ORIGIN_REGEX`, since Vercel preview URLs are dynamic per-PR and the exact-match
# allowlist alone can't cover them.
_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
_origin_regex = os.environ.get("ALLOWED_ORIGIN_REGEX", r"http://(localhost|127\.0\.0\.1):\d+")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=_origin_regex,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Empty by default: `/execute` is open unless a deployment sets this, matching how this repo has
# always run (no secrets required for `make api`). Set `EXECUTE_API_KEY` to require callers to
# send a matching `X-Execute-Key` header before this endpoint will write to the ledger.
_execute_api_key = os.environ.get("EXECUTE_API_KEY", "")


def _check_execute_auth(x_execute_key: str | None) -> None:
    if _execute_api_key and x_execute_key != _execute_api_key:
        raise HTTPException(status_code=401, detail="missing or invalid X-Execute-Key header")


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
    """Deliberately does no pipeline work: the frontend calls this first to wake a sleeping
    free-tier instance, and it must answer as soon as the process is up rather than waiting on
    a dataset build.
    """
    return HealthzResponse(
        ok=True,
        version=ledgerguard.__version__,
        budget_spent_usd=_current_budget_spent_usd(),
    )


@app.get("/api/v1/dashboard", response_model=DashboardResponse)
def dashboard() -> DashboardResponse:
    return get_state().dashboard()


@app.get("/api/v1/reconciliation", response_model=ReconciliationListResponse)
def reconciliation(
    action: str | None = Query(default=None, description="AUTO_POST | ESCALATE | FLAG_ANOMALY"),
    difficulty: str | None = Query(default=None, description="EASY | MEDIUM | HARD | ADVERSARIAL"),
    search: str | None = Query(default=None, description="Substring of bank line id or narration"),
    limit: int = Query(default=500, ge=1, le=2000),
) -> ReconciliationListResponse:
    return get_state().queue(action=action, difficulty=difficulty, search=search, limit=limit)


@app.get("/api/v1/reconciliation/{bank_line_id}", response_model=InvestigationResponse)
def investigation(bank_line_id: str) -> InvestigationResponse:
    state = get_state()
    if bank_line_id not in state.states:
        raise HTTPException(status_code=404, detail=f"unknown bank line {bank_line_id}")
    return state.investigation(bank_line_id)


@app.post("/api/v1/reconciliation/{bank_line_id}/execute", response_model=ExecuteResponse)
def execute(bank_line_id: str, x_execute_key: str | None = Header(default=None)) -> ExecuteResponse:
    """Bounded action. The authority policy decides; only an AUTO_POST verdict reaches the
    ledger, and the insert is idempotent, so a repeated call posts once. Gated behind
    `EXECUTE_API_KEY` when that env var is set (see above) -- unset, this is unchanged from how
    every prior version of this endpoint ran.
    """
    _check_execute_auth(x_execute_key)
    state = get_state()
    if bank_line_id not in state.states:
        raise HTTPException(status_code=404, detail=f"unknown bank line {bank_line_id}")
    return state.execute(bank_line_id)


@app.get("/api/v1/audit", response_model=AuditResponse)
def audit(limit: int = Query(default=200, ge=1, le=1000)) -> AuditResponse:
    events = get_state().audit(limit=limit)
    return AuditResponse(batch_id=BATCH_ID, total=len(events), events=events)
