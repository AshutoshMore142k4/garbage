"""Builds the unified per-bank-line Decision dataset that L3 calibrates and gates over,
combining L1's resolved matches with L2's triage of the residual (phases.md Phase 5).

Uses L2's free fallback rather than a live model call: no session so far has had Anthropic
credentials or network access to call the real API (see PROGRESS.md/BROKE.md, Phases 0 and 4).
The calibrator itself is agnostic to which layer produced a raw confidence -- it only ever sees
the feature vector -- so this substitution doesn't change what Phase 5 demonstrates: calibration
and gating over decisions carrying a real (if currently fallback-sourced) raw confidence.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ledgerguard.l0_normalize.normalize import normalize_timestamp
from ledgerguard.l1_deterministic.matcher import (
    MAX_CANDIDATES_FOR_L2,
    PaymentIndex,
    load_bank_lines,
    load_ledger_payments,
    run_l1,
)
from ledgerguard.l2_llm_triage.fallback import fallback_triage
from ledgerguard.l3_calibrate_gate.features import DecisionInput, extract_features


@dataclass
class Decision:
    bank_line_id: str
    split: str
    credit_paise: int
    resolver: str  # "L1_RULE" | "L2_LLM" (fallback-sourced; see module docstring)
    order_ids: list[str]
    raw_confidence: float
    reason_code: Optional[str]  # set only when no candidate was proposed at all
    evidence: list[str]
    features: dict[str, float]
    correct: bool


def _is_correct(order_ids: list[str], ground_truth_entry: dict) -> bool:
    expected = ground_truth_entry.get("correct_match")
    expected_orders = set(expected["order_ids"]) if expected else set()
    return set(order_ids) == expected_orders


def build_decision_dataset(data_dir: Path) -> list[Decision]:
    bank_lines = load_bank_lines(data_dir / "bank_statement.csv")
    payments = load_ledger_payments(data_dir / "internal_ledger.csv")
    ground_truth = json.loads((data_dir / "ground_truth.json").read_text())

    payments_by_id = {p.payment_id: p for p in payments}
    bank_lines_by_id = {row["id"]: row for row in bank_lines}
    index = PaymentIndex(payments)

    results = run_l1(bank_lines, payments)

    decisions: list[Decision] = []
    for bank_line_id, outcome in results.items():
        row = bank_lines_by_id[bank_line_id]
        gt = ground_truth[bank_line_id]
        credit_paise = int(row["credit_paise"])
        value_date = normalize_timestamp(row["value_date"])
        # The full candidate pool in the date-tolerance lookback window, regardless of whether
        # this decision resolved -- a uniform ambiguity signal for both L1 and L2 decisions.
        candidate_set_size = len(index.candidates_before(value_date))

        if outcome.resolved:
            resolver = "L1_RULE"
            order_ids = outcome.order_ids
            raw_confidence = outcome.confidence or 0.0
            reason_code = None
            evidence = outcome.evidence
            chosen_payments = [payments_by_id[pid] for pid in outcome.payment_ids if pid in payments_by_id]
            chosen_net_paise = sum(p.net_paise for p in chosen_payments) if chosen_payments else None
            chosen_captured_at = (
                max(p.captured_at for p in chosen_payments).strftime("%Y-%m-%dT%H:%M:%SZ")
                if chosen_payments
                else None
            )
        else:
            resolver = "L2_LLM"
            bounded_candidates = sorted(
                (payments_by_id[pid] for pid in outcome.candidate_payment_ids if pid in payments_by_id),
                key=lambda p: abs((value_date - p.captured_at).total_seconds()),
            )[:MAX_CANDIDATES_FOR_L2]
            candidate_dicts = [
                {
                    "payment_id": p.payment_id,
                    "order_id": p.order_id,
                    "net_paise": p.net_paise,
                    "captured_at": p.captured_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                for p in bounded_candidates
            ]
            response = fallback_triage(row["narration"], candidate_dicts)
            raw_confidence = response.confidence

            if response.candidate_id is None:
                order_ids = []
                reason_code = outcome.reason_code
                chosen_net_paise = None
                chosen_captured_at = None
                evidence = outcome.evidence + response.evidence
            else:
                chosen = payments_by_id[response.candidate_id]
                order_ids = [chosen.order_id]
                reason_code = None
                chosen_net_paise = chosen.net_paise
                chosen_captured_at = chosen.captured_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                evidence = response.evidence

        features = extract_features(
            DecisionInput(
                credit_paise=credit_paise,
                narration=row["narration"],
                value_date=row["value_date"],
                candidate_set_size=candidate_set_size,
                chosen_net_paise=chosen_net_paise,
                chosen_captured_at=chosen_captured_at,
                raw_confidence=raw_confidence,
            )
        )

        decisions.append(
            Decision(
                bank_line_id=bank_line_id,
                split=gt["split"],
                credit_paise=credit_paise,
                resolver=resolver,
                order_ids=order_ids,
                raw_confidence=raw_confidence,
                reason_code=reason_code,
                evidence=evidence,
                features=features,
                correct=_is_correct(order_ids, gt),
            )
        )

    return decisions
