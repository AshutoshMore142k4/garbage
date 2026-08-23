"""Response models for the `/api/v1` surface (plan.md #16: "All request/response bodies are
Pydantic models. No untyped dicts cross a boundary.").

Deliberately additive and kept out of `models.py`: the domain schemas there are depended on by
ten phases of tests, and this UI surface has no business reshaping them.

**Provenance is a first-class field, not a footnote.** Every response carries `data_provenance`,
and the UI renders it verbatim. `REAL_VS_SIMULATED.md` records that no session in this project
has ever had Razorpay credentials or network egress -- so an interface claiming a live payment
connection would be false. The constant below is the single place that wording is defined.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

DATA_PROVENANCE = "Synthetic dataset · no live Razorpay connection"

SignalStatus = Literal["pass", "warn", "fail"]


class BankLineOut(BaseModel):
    bank_line_id: str
    utr: Optional[str] = None
    credit_paise: int
    narration: str
    value_date: str


class PaymentOut(BaseModel):
    payment_id: str
    order_id: str
    amount_paise: int
    fee_paise: int
    tax_paise: int
    net_paise: int
    captured_at: str
    role: Literal["matched", "candidate"]


class MatchSignal(BaseModel):
    """One structured decision factor. Never free-form model reasoning -- these are computed
    from the same feature vector L3 calibrates on (l3_calibrate_gate/features.py).
    """

    label: str
    value: str
    status: SignalStatus
    detail: Optional[str] = None


class PolicyCheck(BaseModel):
    """One clause of the L5 authority policy, shown with its actual measured value so a reviewer
    can see exactly which clause blocked an action.
    """

    label: str
    required: str
    actual: str
    passed: bool


class QueueItem(BaseModel):
    bank_line_id: str
    value_date: str
    credit_paise: int
    narration: str
    resolver: str
    rule_id: Optional[str] = None
    action: str
    reason_code: Optional[str] = None
    calibrated_confidence: float
    threshold: float
    difficulty: str
    order_ids: list[str] = Field(default_factory=list)
    has_anomaly: bool = False


class DashboardResponse(BaseModel):
    data_provenance: str = DATA_PROVENANCE
    dataset: str
    batch_id: str
    total_bank_lines: int
    counts_by_action: dict[str, int]
    refused: int
    auto_post_rate: float
    precision_auto_posted: float
    false_auto_match_rate: float
    threshold: float
    total_credit_paise: int
    llm_invocation_count: int
    # The duplicate-UTR / genuine-double-settlement pair the generator deliberately plants in
    # holdout. Read from chaos_manifest.json rather than guessed by reason code -- the dataset
    # contains ten of each, and the UI must point at the actual planted pair, not whichever one
    # happens to sort first.
    demo_pair: list[str] = Field(default_factory=list)


class ReconciliationListResponse(BaseModel):
    data_provenance: str = DATA_PROVENANCE
    total: int
    items: list[QueueItem]


class AnomalyOut(BaseModel):
    reason_code: str
    evidence: list[str] = Field(default_factory=list)


class InvestigationResponse(BaseModel):
    data_provenance: str = DATA_PROVENANCE
    bank_line: BankLineOut
    payments: list[PaymentOut] = Field(default_factory=list)
    resolver: str
    rule_id: Optional[str] = None
    model: Optional[str] = None
    order_ids: list[str] = Field(default_factory=list)
    raw_confidence: float
    calibrated_confidence: float
    threshold: float
    action: str
    reason_code: Optional[str] = None
    evidence: list[str] = Field(default_factory=list)
    signals: list[MatchSignal] = Field(default_factory=list)
    policy: list[PolicyCheck] = Field(default_factory=list)
    anomalies: list[AnomalyOut] = Field(default_factory=list)
    difficulty: str
    # Ground truth exists only because this dataset is synthetic and the generator knows the
    # answer it constructed. Surfaced so a reviewer can audit the decision, and labelled as such
    # in the UI -- a production deployment would have no such field.
    ground_truth_order_ids: Optional[list[str]] = None
    decision_was_correct: Optional[bool] = None


class ExecuteResponse(BaseModel):
    data_provenance: str = DATA_PROVENANCE
    bank_line_id: str
    authorized: bool
    action: str
    reason_code: Optional[str] = None
    policy: list[PolicyCheck] = Field(default_factory=list)
    message: str
    # Populated only on an authorized execution.
    decision_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    newly_posted: Optional[bool] = None


class AuditEvent(BaseModel):
    decision_id: str
    batch_id: str
    bank_line_id: str
    resolver: str
    action: str
    reason_code: Optional[str] = None
    calibrated_confidence: Optional[float] = None
    threshold: Optional[float] = None
    idempotency_key: str
    created_at: str
    evidence: list[str] = Field(default_factory=list)


class AuditResponse(BaseModel):
    data_provenance: str = DATA_PROVENANCE
    batch_id: str
    total: int
    events: list[AuditEvent]
