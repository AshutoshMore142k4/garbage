"""Builds the unified per-bank-line Decision dataset that L3 calibrates and gates over,
combining L1's resolved matches with L2's triage of the residual (phases.md Phase 5).

Defaults to L2's free fallback (`fallback_triage_fn`) -- callers who want a live model's
answers instead (a real Anthropic/OpenAI/Gemini client, see `l2_llm_triage/factory.py`) pass a
`triage_fn` matching the same `(bank_line, candidates) -> (TriageResponse, metadata)` contract.
The calibrator itself is agnostic to which layer produced a raw confidence -- it only ever sees
the feature vector -- so swapping `triage_fn` doesn't change what Phase 5 demonstrates:
calibration and gating over decisions carrying a real (fallback- or model-sourced) raw
confidence.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ledgerguard.l0_normalize.normalize import normalize_timestamp
from ledgerguard.l1_deterministic.matcher import (
    MAX_CANDIDATES_FOR_L2,
    PaymentIndex,
    load_bank_lines,
    load_ledger_payments,
    run_l1,
)
from ledgerguard.l2_llm_triage.fallback import fallback_triage_fn
from ledgerguard.l3_calibrate_gate.features import DecisionInput, extract_features
from ledgerguard.models import TriageResponse

TriageFn = Callable[[dict, list[dict]], tuple[TriageResponse, dict]]


@dataclass
class Decision:
    bank_line_id: str
    split: str
    credit_paise: int
    resolver: str  # "L1_RULE" | "L2_LLM" (source given by `model`, below)
    rule_id: Optional[str]  # which L1 rule fired; None for L2/no-candidate decisions
    order_ids: list[str]
    raw_confidence: float
    reason_code: Optional[str]  # set only when no candidate was proposed at all
    evidence: list[str]
    features: dict[str, float]
    correct: bool
    # e.g. "fallback_rapidfuzz" or "anthropic:claude-opus-5"; None for L1_RULE decisions.
    # Defaulted (rather than required) so existing direct-construction call sites (tests) that
    # predate the multi-provider L2 client don't need updating for a field they don't care about.
    model: Optional[str] = None
    prompt_hash: Optional[str] = None


def _is_correct(order_ids: list[str], ground_truth_entry: dict) -> bool:
    expected = ground_truth_entry.get("correct_match")
    expected_orders = set(expected["order_ids"]) if expected else set()
    return set(order_ids) == expected_orders


def build_decision_dataset(
    data_dir: Path, extra_rules: tuple = (), triage_fn: Optional[TriageFn] = None
) -> list[Decision]:
    """`extra_rules` (D1, Phase 8): promoted learned rules to try after L1's built-ins, in the
    same firing-order-respecting way `matcher.run_l1` already applies them. Defaults to `()` so
    every existing caller (close.py, eval/calibration.py, eval/redteam_eval.py) is unaffected.
    `triage_fn` defaults to `None`, meaning `fallback_triage_fn` -- pass a real provider client's
    `.triage` method (see `l2_llm_triage/factory.py`) to have L2 answer from a live model instead.
    """
    bank_lines = load_bank_lines(data_dir / "bank_statement.csv")
    payments = load_ledger_payments(data_dir / "internal_ledger.csv")
    ground_truth = json.loads((data_dir / "ground_truth.json").read_text())
    return decisions_for(bank_lines, payments, ground_truth, extra_rules=extra_rules, triage_fn=triage_fn)


def decisions_for(
    bank_lines: list[dict],
    payments: list,
    ground_truth: dict[str, dict],
    extra_rules: tuple = (),
    triage_fn: Optional[TriageFn] = None,
) -> list[Decision]:
    """The reusable core of `build_decision_dataset`, taking already-loaded entities directly
    instead of a directory -- lets eval/rule_learning.py (Phase 8) run this over one sequential
    *subset* of bank lines at a time (a "batch"), against the full ledger of payments, without
    writing each batch out to its own directory on disk first.
    """
    triage_fn = triage_fn or fallback_triage_fn
    payments_by_id = {p.payment_id: p for p in payments}
    bank_lines_by_id = {row["id"]: row for row in bank_lines}
    index = PaymentIndex(payments)

    results = run_l1(bank_lines, payments, extra_rules=extra_rules)

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
            rule_id = outcome.rule_id
            model = None
            prompt_hash = None
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
            rule_id = None
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
            response, meta = triage_fn(row, candidate_dicts)
            raw_confidence = response.confidence
            model = meta["model"]
            prompt_hash = meta.get("prompt_hash")

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
                rule_id=rule_id,
                model=model,
                prompt_hash=prompt_hash,
                order_ids=order_ids,
                raw_confidence=raw_confidence,
                reason_code=reason_code,
                evidence=evidence,
                features=features,
                correct=_is_correct(order_ids, gt),
            )
        )

    return decisions
