"""The API's view of the reconciliation pipeline: runs L0->L5 once, caches it, and reshapes it
into the `/api/v1` response models.

**Why cached at module scope.** Every endpoint answers from one pipeline run over the committed
seeded dataset. Building it costs a couple of seconds (L1 over 300 bank lines, then a
logistic-regression fit on the validation split); doing that per request would be wasteful and,
on a free-tier host, indistinguishable from being down. The dataset is seeded and deterministic,
so a cached run and a fresh one are the same answer -- there is nothing to go stale.

**What is real here and what is not.** The pipeline itself is the real one: the same
`build_decision_dataset`, `Calibrator`, `find_optimal_threshold`, `detect_anomalies` and
`authorize` that `make close` and `make bench` use, with no reimplementation. What is synthetic
is the *data* -- see `REAL_VS_SIMULATED.md`. `/execute` performs a genuine idempotent insert
against a real SQLite ledger and appends a real audit line; it is not a mocked animation.

**Writes never touch the repo.** `LEDGERGUARD_DB_PATH` / `LEDGERGUARD_AUDIT_PATH` default to a
temp directory, because the deployment target's filesystem is ephemeral and read-only outside
`/tmp`, and because an API request has no business mutating checked-in files.
"""
from __future__ import annotations

import csv
import json
import os
import sqlite3
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from ledgerguard.api.schemas import (
    AnomalyOut,
    AuditEvent,
    BankLineOut,
    DashboardResponse,
    ExecuteResponse,
    InvestigationResponse,
    MatchSignal,
    PaymentOut,
    PolicyCheck,
    QueueItem,
    ReconciliationListResponse,
)
from ledgerguard.audit.writer import AuditWriter
from ledgerguard.close import DEFAULT_AUTHORITY_LIMIT_PAISE
from ledgerguard.db import init_db
from ledgerguard.l1_deterministic.matcher import load_bank_lines, load_ledger_payments, run_l1
from ledgerguard.l1_deterministic.tolerance import MAX_SETTLEMENT_DAYS, MIN_SETTLEMENT_DAYS
from ledgerguard.l3_calibrate_gate.calibrator import Calibrator
from ledgerguard.l3_calibrate_gate.cost_model import CostDecision, find_optimal_threshold
from ledgerguard.l3_calibrate_gate.decisions import Decision, build_decision_dataset
from ledgerguard.l3_calibrate_gate.gate import AUTO_POST, GateInput, gate
from ledgerguard.l4_anomaly.detectors import AnomalyFlag, detect_anomalies
from ledgerguard.l5_executor.authority import AuthorityInput, authorize
from ledgerguard.l5_executor.idempotency import derive_idempotency_key
from ledgerguard.l5_executor.ledger import post_decision
from ledgerguard.models import MatchDecision

BATCH_ID = "live-batch"
NARRATION_SIMILARITY_PASS = 70.0


def _data_dir() -> Path:
    """`data/raw` when a real ingest has produced one, else the committed sample -- the same
    fallback every CLI in this project uses, so the API can never silently read a different
    dataset than `make close` does.
    """
    configured = os.environ.get("LEDGERGUARD_DATA_DIR")
    if configured:
        return Path(configured)
    raw = Path("data/raw")
    return raw if (raw / "bank_statement.csv").exists() else Path("data/samples")


def _writable_path(env_var: str, filename: str) -> Path:
    configured = os.environ.get(env_var)
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / filename


@dataclass
class BankLineState:
    decision: Decision
    row: dict
    calibrated: float
    gate_action: str
    gate_reason: Optional[str]
    final_action: str
    reason_code: Optional[str]
    resolver: str
    model: Optional[str]
    evidence: list[str]
    anomalies: list[AnomalyFlag]
    matched_payment_ids: list[str]
    candidate_payment_ids: list[str]
    difficulty: str
    ground_truth_order_ids: Optional[list[str]]


class PipelineState:
    """One full L0->L5 pass, held in memory and reshaped on demand."""

    def __init__(self) -> None:
        data_dir = _data_dir()
        self.data_dir = data_dir
        self.authority_limit_paise = int(
            os.environ.get("AUTHORITY_LIMIT_PAISE", DEFAULT_AUTHORITY_LIMIT_PAISE)
        )

        bank_lines = load_bank_lines(data_dir / "bank_statement.csv")
        payments = load_ledger_payments(data_dir / "internal_ledger.csv")
        ground_truth = json.loads((data_dir / "ground_truth.json").read_text())

        self.payments_by_id = {p.payment_id: p for p in payments}
        self.rows_by_id = {row["id"]: row for row in bank_lines}
        self.order_created_at = self._load_order_created_at(data_dir / "internal_ledger.csv")
        self.demo_pair = self._load_demo_pair(data_dir / "chaos_manifest.json")

        decisions = build_decision_dataset(data_dir)
        outcomes = run_l1(bank_lines, payments)

        # L3: fit on validation only, select the threshold there, then apply to everything --
        # identical discipline to close.py, so the UI cannot show a differently-tuned system.
        validation = [d for d in decisions if d.split == "validation"]
        calibrator = Calibrator()
        calibrator.fit([d.features for d in validation], [d.correct for d in validation])
        calibrated_by_id = dict(
            zip(
                (d.bank_line_id for d in decisions),
                calibrator.predict_proba([d.features for d in decisions]),
            )
        )
        self.threshold = find_optimal_threshold(
            [
                CostDecision(
                    credit_paise=d.credit_paise,
                    calibrated_confidence=calibrated_by_id[d.bank_line_id],
                    correct=d.correct,
                )
                for d in validation
            ]
        )

        anomalies_by_id: dict[str, list[AnomalyFlag]] = defaultdict(list)
        for flag in detect_anomalies(decisions, bank_lines, payments):
            if flag.bank_line_id:
                anomalies_by_id[flag.bank_line_id].append(flag)

        self.states: dict[str, BankLineState] = {}
        for d in decisions:
            calibrated = calibrated_by_id[d.bank_line_id]
            flags = anomalies_by_id.get(d.bank_line_id, [])
            outcome = outcomes[d.bank_line_id]

            gate_outcome = gate(
                GateInput(
                    has_candidate=bool(d.order_ids),
                    calibrated_confidence=calibrated,
                    existing_reason_code=d.reason_code,
                ),
                threshold=self.threshold,
            )
            final_action = authorize(
                AuthorityInput(
                    gate_action=gate_outcome.action,
                    amount_paise=d.credit_paise,
                    authority_limit_paise=self.authority_limit_paise,
                    has_anomaly=bool(flags),
                )
            )

            if flags:
                resolver, model = "L4_ANOMALY", None
                reason_code = flags[0].reason_code
                evidence = [e for f in flags for e in f.evidence]
            else:
                resolver = d.resolver if d.order_ids else "ABSTAIN"
                model = "fallback_rapidfuzz" if d.resolver == "L2_LLM" else None
                reason_code = gate_outcome.reason_code
                evidence = d.evidence

            gt = ground_truth[d.bank_line_id].get("correct_match")
            self.states[d.bank_line_id] = BankLineState(
                decision=d,
                row=self.rows_by_id[d.bank_line_id],
                calibrated=calibrated,
                gate_action=gate_outcome.action,
                gate_reason=gate_outcome.reason_code,
                final_action=final_action,
                reason_code=reason_code,
                resolver=resolver,
                model=model,
                evidence=evidence,
                anomalies=flags,
                matched_payment_ids=list(outcome.payment_ids),
                candidate_payment_ids=list(outcome.candidate_payment_ids),
                difficulty=ground_truth[d.bank_line_id]["difficulty"],
                ground_truth_order_ids=list(gt["order_ids"]) if gt else None,
            )

    @staticmethod
    def _load_demo_pair(manifest_path: Path) -> list[str]:
        """The planted duplicate-vs-double-settlement pair, named by the generator itself. Guessing
        it from reason codes would be wrong: the dataset carries ten of each category.
        """
        if not manifest_path.exists():
            return []
        try:
            return list(json.loads(manifest_path.read_text())["demo_pair"].values())
        except (json.JSONDecodeError, KeyError, OSError):
            return []

    @staticmethod
    def _load_order_created_at(ledger_csv: Path) -> dict[str, str]:
        out: dict[str, str] = {}
        with open(ledger_csv, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                out.setdefault(row["order_id"], row["order_created_at"])
        return out

    # ---- reshaping ----

    def dashboard(self) -> DashboardResponse:
        counts: dict[str, int] = defaultdict(int)
        auto_posted = auto_posted_correct = llm_calls = 0
        total_credit = 0
        for s in self.states.values():
            counts[s.final_action] += 1
            total_credit += s.decision.credit_paise
            if s.decision.resolver == "L2_LLM":
                llm_calls += 1
            if s.final_action == AUTO_POST:
                auto_posted += 1
                if s.decision.correct:
                    auto_posted_correct += 1

        total = len(self.states)
        return DashboardResponse(
            dataset=str(self.data_dir),
            batch_id=BATCH_ID,
            total_bank_lines=total,
            counts_by_action=dict(sorted(counts.items())),
            refused=total - counts.get(AUTO_POST, 0),
            auto_post_rate=counts.get(AUTO_POST, 0) / total if total else 0.0,
            precision_auto_posted=auto_posted_correct / auto_posted if auto_posted else 0.0,
            false_auto_match_rate=(auto_posted - auto_posted_correct) / auto_posted if auto_posted else 0.0,
            threshold=self.threshold,
            total_credit_paise=total_credit,
            llm_invocation_count=llm_calls,
            demo_pair=self.demo_pair,
        )

    def _queue_item(self, s: BankLineState) -> QueueItem:
        return QueueItem(
            bank_line_id=s.decision.bank_line_id,
            value_date=s.row["value_date"],
            credit_paise=s.decision.credit_paise,
            narration=s.row["narration"],
            resolver=s.resolver,
            rule_id=s.decision.rule_id,
            action=s.final_action,
            reason_code=s.reason_code,
            calibrated_confidence=s.calibrated,
            threshold=self.threshold,
            difficulty=s.difficulty,
            order_ids=s.decision.order_ids,
            has_anomaly=bool(s.anomalies),
        )

    def queue(
        self,
        action: Optional[str] = None,
        difficulty: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 500,
    ) -> ReconciliationListResponse:
        items = [self._queue_item(s) for s in self.states.values()]
        if action:
            items = [i for i in items if i.action == action]
        if difficulty:
            items = [i for i in items if i.difficulty == difficulty]
        if search:
            needle = search.lower()
            items = [i for i in items if needle in i.bank_line_id.lower() or needle in i.narration.lower()]
        # Refused first, then by rupees at risk -- the exception queue's own ranking (plan.md #19),
        # so the most consequential decisions are what a reviewer sees first.
        items.sort(key=lambda i: (i.action == AUTO_POST, -i.credit_paise))
        return ReconciliationListResponse(total=len(items), items=items[:limit])

    def _signals(self, s: BankLineState) -> list[MatchSignal]:
        f = s.decision.features
        gap = int(f["absolute_amount_gap_paise"])
        skew = f["date_skew_days"]
        narration = f["narration_similarity_score"]
        candidates = int(f["candidate_set_size"])

        signals = [
            MatchSignal(
                label="Amount match",
                value="exact" if gap == 0 else f"off by {gap / 100:,.2f}",
                status="pass" if gap == 0 else "fail",
                detail="Bank credit vs. the net of the proposed payment(s), in paise.",
            ),
            MatchSignal(
                label="Settlement date",
                value=f"{skew:.2f} days",
                status="pass" if MIN_SETTLEMENT_DAYS <= skew <= MAX_SETTLEMENT_DAYS else "warn",
                detail=f"Expected settlement window is T+{MIN_SETTLEMENT_DAYS} to T+{MAX_SETTLEMENT_DAYS}.",
            ),
            MatchSignal(
                label="Narration plausibility",
                value=f"{narration:.0f}/100",
                status="pass" if narration >= NARRATION_SIMILARITY_PASS else "warn",
                detail="Fuzzy score against the merchant's known bank-narration tokens.",
            ),
            MatchSignal(
                label="Candidate ambiguity",
                value=f"{candidates} in window",
                status="pass" if candidates <= 1 else "warn",
                detail="Payments captured inside the lookback window that could have produced this credit.",
            ),
        ]
        for flag in s.anomalies:
            signals.append(
                MatchSignal(
                    label="Anomaly detected",
                    value=flag.reason_code,
                    status="fail",
                    detail=flag.evidence[0] if flag.evidence else None,
                )
            )
        return signals

    def _policy(self, s: BankLineState) -> list[PolicyCheck]:
        """The three clauses of the L5 authority policy, each with its measured value. Mirrors
        `l5_executor/authority.authorize` exactly -- if that changes, this must too.
        """
        return [
            PolicyCheck(
                label="Calibrated confidence",
                required=f">= {self.threshold:.2f}",
                actual=f"{s.calibrated:.3f}",
                passed=bool(s.decision.order_ids) and s.calibrated >= self.threshold,
            ),
            PolicyCheck(
                label="Amount within authority",
                required=f"<= {self.authority_limit_paise / 100:,.2f}",
                actual=f"{s.decision.credit_paise / 100:,.2f}",
                passed=s.decision.credit_paise <= self.authority_limit_paise,
            ),
            PolicyCheck(
                label="No anomaly flag",
                required="none",
                actual=s.anomalies[0].reason_code if s.anomalies else "none",
                passed=not s.anomalies,
            ),
        ]

    def _payments(self, s: BankLineState) -> list[PaymentOut]:
        matched = set(s.matched_payment_ids)
        ids = s.matched_payment_ids or s.candidate_payment_ids[:8]
        out = []
        for pid in ids:
            p = self.payments_by_id.get(pid)
            if p is None:
                continue
            out.append(
                PaymentOut(
                    payment_id=p.payment_id,
                    order_id=p.order_id,
                    amount_paise=p.amount_paise,
                    fee_paise=p.fee_paise,
                    tax_paise=p.tax_paise,
                    net_paise=p.net_paise,
                    captured_at=p.captured_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    role="matched" if pid in matched else "candidate",
                )
            )
        return out

    def investigation(self, bank_line_id: str) -> InvestigationResponse:
        s = self.states[bank_line_id]
        return InvestigationResponse(
            bank_line=BankLineOut(
                bank_line_id=bank_line_id,
                utr=s.row.get("utr") or None,
                credit_paise=s.decision.credit_paise,
                narration=s.row["narration"],
                value_date=s.row["value_date"],
            ),
            payments=self._payments(s),
            resolver=s.resolver,
            rule_id=s.decision.rule_id,
            model=s.model,
            order_ids=s.decision.order_ids,
            raw_confidence=s.decision.raw_confidence,
            calibrated_confidence=s.calibrated,
            threshold=self.threshold,
            action=s.final_action,
            reason_code=s.reason_code,
            evidence=s.evidence,
            signals=self._signals(s),
            policy=self._policy(s),
            anomalies=[AnomalyOut(reason_code=f.reason_code, evidence=f.evidence) for f in s.anomalies],
            difficulty=s.difficulty,
            ground_truth_order_ids=s.ground_truth_order_ids,
            decision_was_correct=s.decision.correct,
        )

    def execute(self, bank_line_id: str) -> ExecuteResponse:
        """The bounded action. Runs the real authority policy; only an AUTO_POST verdict reaches
        the ledger, and the insert is idempotent by construction, so calling this twice posts
        once (`idempotency_key UNIQUE`, db.py).
        """
        s = self.states[bank_line_id]
        policy = self._policy(s)

        if s.final_action != AUTO_POST:
            failed = [c for c in policy if not c.passed]
            if s.anomalies:
                why = f"an anomaly flag ({s.anomalies[0].reason_code}) prevents autonomous execution"
            elif failed:
                why = f"{failed[0].label.lower()} was {failed[0].actual}, required {failed[0].required}"
            else:
                why = "the gate did not clear this decision for posting"
            return ExecuteResponse(
                bank_line_id=bank_line_id,
                authorized=False,
                action=s.final_action,
                reason_code=s.reason_code,
                policy=policy,
                message=f"AUTO-POST BLOCKED — {why}.",
            )

        idempotency_key = derive_idempotency_key(BATCH_ID, bank_line_id)
        decision = MatchDecision(
            decision_id=f"dec_{idempotency_key}",
            batch_id=BATCH_ID,
            bank_line_id=bank_line_id,
            resolver=s.resolver,
            rule_id=s.decision.rule_id,
            model=s.model,
            prompt_hash=None,
            raw_confidence=s.decision.raw_confidence,
            calibrated_confidence=s.calibrated,
            threshold=self.threshold,
            action=s.final_action,
            reason_code=s.reason_code,
            evidence=s.evidence,
            idempotency_key=idempotency_key,
            created_at=s.row["value_date"],
        )

        conn = init_db(_writable_path("LEDGERGUARD_DB_PATH", "ledgerguard.db"))
        try:
            newly_posted = post_decision(conn, decision)
        finally:
            conn.close()

        if newly_posted:
            AuditWriter(_writable_path("LEDGERGUARD_AUDIT_PATH", "audit.jsonl")).append(decision)
            message = "Reconciliation entry posted. Idempotency key stored, audit event recorded."
        else:
            message = "Already posted — idempotency key already present, so this was a no-op."

        return ExecuteResponse(
            bank_line_id=bank_line_id,
            authorized=True,
            action=s.final_action,
            reason_code=s.reason_code,
            policy=policy,
            message=message,
            decision_id=decision.decision_id,
            idempotency_key=idempotency_key,
            newly_posted=newly_posted,
        )

    def audit(self, limit: int = 200) -> list[AuditEvent]:
        db_path = _writable_path("LEDGERGUARD_DB_PATH", "ledgerguard.db")
        if not db_path.exists():
            return []
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT decision_id, batch_id, bank_line_id, resolver, action, reason_code, "
                "calibrated_confidence, threshold, idempotency_key, created_at, evidence_json "
                "FROM match_decisions ORDER BY rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()

        events = []
        for r in rows:
            try:
                evidence = json.loads(r[10]) if r[10] else []
            except json.JSONDecodeError:
                evidence = []
            events.append(
                AuditEvent(
                    decision_id=r[0], batch_id=r[1], bank_line_id=r[2], resolver=r[3], action=r[4],
                    reason_code=r[5], calibrated_confidence=r[6], threshold=r[7],
                    idempotency_key=r[8], created_at=r[9], evidence=evidence,
                )
            )
        return events


@lru_cache(maxsize=1)
def get_state() -> PipelineState:
    """Built on first use rather than at import, so the module stays importable (and testable)
    even where the dataset is absent, and so a cold start does not pay for it twice.
    """
    return PipelineState()
