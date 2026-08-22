"""Pydantic schemas for every entity and API boundary in plan.md sections 15 and 16.

All money fields are integer paise -- no floats anywhere in a money path (plan.md Phase 1
implementation detail). All timestamp fields are ISO-8601 UTC strings.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Currency = Literal["INR"]

# plan.md #15 match_decisions.resolver
ResolverType = Literal["L1_RULE", "L2_LLM", "L4_ANOMALY", "ABSTAIN"]

# plan.md #15 match_decisions.action
ActionType = Literal["AUTO_POST", "ESCALATE", "FLAG_ANOMALY"]

# phases.md Phase 5 "closed enum" -- L4 anomaly reason codes (Phase 6) extend this set later.
ReasonCode = Literal[
    "AMBIGUOUS_NARRATION_MULTI_CANDIDATE",
    "SUBSET_SUM_OVER_BUDGET",
    "AMOUNT_GAP_EXCEEDS_TOLERANCE",
    "NO_CANDIDATE_FOUND",
    "SCHEMA_VALIDATION_FAILED",
    "BUDGET_EXHAUSTED",
]

# plan.md #15 learned_rules.status
RuleStatus = Literal["CANDIDATE", "PROMOTED", "REJECTED"]

# plan.md #10 SPLIT / #24 stratified reporting
Difficulty = Literal["EASY", "MEDIUM", "HARD", "ADVERSARIAL"]
Split = Literal["train", "validation", "holdout"]

ExceptionStatus = Literal["open", "resolved"]


class Order(BaseModel):
    id: str
    amount_paise: int
    currency: Currency
    created_at: str
    source: str


class Payment(BaseModel):
    id: str
    order_id: str
    amount_paise: int
    fee_paise: int
    tax_paise: int
    method: str
    status: str
    captured_at: str


class Refund(BaseModel):
    id: str
    payment_id: str
    amount_paise: int
    created_at: str


class Settlement(BaseModel):
    id: str
    utr: Optional[str] = None
    amount_paise: int
    settled_at: str
    is_synthetic: bool


class BankLine(BaseModel):
    id: str
    utr: Optional[str] = None
    credit_paise: int
    narration: str
    value_date: str


class MatchDecision(BaseModel):
    """One row of match_decisions (plan.md #15) -- also the audit.jsonl line shape (#19)."""

    decision_id: str
    batch_id: str
    bank_line_id: str
    resolver: ResolverType
    rule_id: Optional[str] = None
    model: Optional[str] = None
    prompt_hash: Optional[str] = None
    raw_confidence: Optional[float] = None
    calibrated_confidence: Optional[float] = None
    threshold: Optional[float] = None
    action: ActionType
    reason_code: Optional[ReasonCode] = None
    evidence: list[str] = Field(default_factory=list)
    idempotency_key: str
    created_at: str


class ExceptionRecord(BaseModel):
    id: str
    decision_id: str
    reason_code: ReasonCode
    status: ExceptionStatus
    human_resolution: Optional[dict] = None
    resolved_at: Optional[str] = None


class LearnedRule(BaseModel):
    rule_id: str
    spec: dict
    proposed_from: str
    validation_hits: int
    validation_false_positives: int
    status: RuleStatus
    promoted_at: Optional[str] = None


class GroundTruth(BaseModel):
    bank_line_id: str
    correct_match: Optional[dict] = None
    difficulty: Difficulty
    split: Split


# ---- API boundary models (plan.md #16) ----


class BatchCreateRequest(BaseModel):
    seed: int
    size: int


class BatchCreateResponse(BaseModel):
    batch_id: str


class BatchStatusResponse(BaseModel):
    status: str
    metrics: dict = Field(default_factory=dict)
    counts_by_action: dict[str, int] = Field(default_factory=dict)


class ExceptionResolveRequest(BaseModel):
    chosen_candidate_id: str


class ExceptionResolveResponse(BaseModel):
    resolved: bool
    proposed_rule: Optional[dict] = None


class HealthzResponse(BaseModel):
    ok: bool
    version: str
    budget_spent_usd: float
