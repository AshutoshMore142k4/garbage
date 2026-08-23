"""L4 anomaly detection (plan.md #9, phases.md Phase 6). L4 has veto power over L1 and L3: any
bank line flagged here is forced to ESCALATE / FLAG_ANOMALY regardless of how confidently L1/L2
matched it or how high L3 calibrated its confidence -- an anomaly flag always beats a confident
match (plan.md #9's design invariant).

Four detectors, mapping 1:1 to phases.md Phase 6's task list:

- **Duplicate UTR** (reporting artifact): the *same* UTR value appears on two or more bank
  lines. Only one of them (if any) is a real credit, but nothing available at this layer says
  which -- so this never tries to guess a winner; it flags every bank line sharing the UTR for
  human review. This is deliberately conservative: refusing to auto-pick "the real one" is the
  whole point (plan.md #2: "one is a reporting artifact, the other is real money sent twice").
- **Genuine double-settlement**: two or more bank lines with *distinct* UTRs both resolved to
  the exact same order(s) -- the merchant really was credited twice for the same batch. UTR
  distinctness is what tells this apart from the duplicate-UTR case above; it is the same
  distinction data/generator.py's DUPLICATE_UTR vs. GENUINE_DOUBLE_SETTLEMENT categories encode.
- **Missing settlement**: a captured payment that no bank line ever matched to, long enough
  after capture that it should have settled by now (using the same tolerance window L1 matches
  against). This is a ledger-level anomaly, not a bank-line-level one -- `bank_line_id` is None.
- **Fee/tax contract violation**: a matched payment's fee or tax, as a fraction of its gross
  amount, falls outside a documented contract band. The bands below are the merchant's expected
  contract, not a measured real-world figure -- flagged for whoever can supply the real one.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ledgerguard.l1_deterministic.rules import LedgerPayment
from ledgerguard.l1_deterministic.tolerance import MAX_SETTLEMENT_DAYS
from ledgerguard.l3_calibrate_gate.decisions import Decision

# Documented assumption, not a measured contract -- see module docstring. data/generator.py's
# normal fee rate is 2% (band midpoint) and its FEE_TAX_VARIANT chaos category uses 3.5%,
# deliberately outside this band so the detector has something real to catch.
FEE_RATE_BAND = (0.015, 0.025)
TAX_RATE_ON_FEE_BAND = (0.15, 0.21)

DUPLICATE_UTR = "DUPLICATE_UTR"
GENUINE_DOUBLE_SETTLEMENT = "GENUINE_DOUBLE_SETTLEMENT"
MISSING_SETTLEMENT = "MISSING_SETTLEMENT"
FEE_TAX_CONTRACT_VIOLATION = "FEE_TAX_CONTRACT_VIOLATION"


@dataclass
class AnomalyFlag:
    bank_line_id: Optional[str]  # None for ledger-level anomalies (missing settlement)
    reason_code: str
    evidence: list[str] = field(default_factory=list)


def detect_duplicate_utr(bank_lines: list[dict]) -> list[AnomalyFlag]:
    by_utr: dict[str, list[str]] = defaultdict(list)
    for row in bank_lines:
        utr = row.get("utr") or None
        if utr:
            by_utr[utr].append(row["id"])

    flags = []
    for utr, bank_line_ids in by_utr.items():
        if len(bank_line_ids) < 2:
            continue
        others = ", ".join(sorted(bank_line_ids))
        for bank_line_id in bank_line_ids:
            flags.append(
                AnomalyFlag(
                    bank_line_id=bank_line_id,
                    reason_code=DUPLICATE_UTR,
                    evidence=[f"utr {utr} appears on {len(bank_line_ids)} bank lines: {others}"],
                )
            )
    return flags


def detect_genuine_double_settlement(decisions: list[Decision], bank_lines_by_id: dict[str, dict]) -> list[AnomalyFlag]:
    by_order_set: dict[tuple[str, ...], list[Decision]] = defaultdict(list)
    for d in decisions:
        if d.order_ids:
            by_order_set[tuple(sorted(d.order_ids))].append(d)

    flags = []
    for order_ids, group in by_order_set.items():
        if len(group) < 2:
            continue
        utrs = {bank_lines_by_id[d.bank_line_id].get("utr") or None for d in group}
        utrs.discard(None)
        if len(utrs) < 2:
            continue  # same (or no) UTR -- that's detect_duplicate_utr's job, not this one
        bank_line_ids = ", ".join(sorted(d.bank_line_id for d in group))
        for d in group:
            flags.append(
                AnomalyFlag(
                    bank_line_id=d.bank_line_id,
                    reason_code=GENUINE_DOUBLE_SETTLEMENT,
                    evidence=[
                        f"orders {list(order_ids)} matched by {len(group)} bank lines with "
                        f"distinct UTRs: {bank_line_ids}"
                    ],
                )
            )
    return flags


def detect_missing_settlement(
    payments: list[LedgerPayment],
    decisions: list[Decision],
    as_of: datetime,
    min_days_overdue: float = MAX_SETTLEMENT_DAYS,
) -> list[AnomalyFlag]:
    matched_order_ids = {order_id for d in decisions for order_id in d.order_ids}

    flags = []
    for p in payments:
        if p.order_id in matched_order_ids:
            continue
        days_since_capture = (as_of - p.captured_at).total_seconds() / 86400
        if days_since_capture >= min_days_overdue:
            flags.append(
                AnomalyFlag(
                    bank_line_id=None,
                    reason_code=MISSING_SETTLEMENT,
                    evidence=[
                        f"payment {p.payment_id} (order {p.order_id}) captured "
                        f"{days_since_capture:.1f} days ago with no matching bank credit yet"
                    ],
                )
            )
    return flags


def detect_fee_tax_contract_violations(
    decisions: list[Decision],
    payments_by_order_id: dict[str, LedgerPayment],
    fee_rate_band: tuple[float, float] = FEE_RATE_BAND,
    tax_rate_on_fee_band: tuple[float, float] = TAX_RATE_ON_FEE_BAND,
) -> list[AnomalyFlag]:
    flags = []
    for d in decisions:
        for order_id in d.order_ids:
            payment = payments_by_order_id.get(order_id)
            if payment is None or payment.amount_paise <= 0 or payment.fee_paise <= 0:
                continue
            fee_rate = payment.fee_paise / payment.amount_paise
            tax_rate_on_fee = payment.tax_paise / payment.fee_paise
            fee_ok = fee_rate_band[0] <= fee_rate <= fee_rate_band[1]
            tax_ok = tax_rate_on_fee_band[0] <= tax_rate_on_fee <= tax_rate_on_fee_band[1]
            if fee_ok and tax_ok:
                continue
            flags.append(
                AnomalyFlag(
                    bank_line_id=d.bank_line_id,
                    reason_code=FEE_TAX_CONTRACT_VIOLATION,
                    evidence=[
                        f"payment {payment.payment_id}: fee_rate={fee_rate:.4f} "
                        f"(band {fee_rate_band}), tax_rate_on_fee={tax_rate_on_fee:.4f} "
                        f"(band {tax_rate_on_fee_band})"
                    ],
                )
            )
    return flags


def detect_anomalies(
    decisions: list[Decision],
    bank_lines: list[dict],
    payments: list[LedgerPayment],
) -> list[AnomalyFlag]:
    """Runs all four detectors and returns every flag found. A bank line can carry more than one
    flag (e.g. a duplicate-UTR line whose payment also violates the fee/tax contract) -- callers
    that only need "is this bank line anomalous at all" should group by bank_line_id themselves.
    """
    bank_lines_by_id = {row["id"]: row for row in bank_lines}
    payments_by_order_id = {p.order_id: p for p in payments}
    as_of = max((p.captured_at for p in payments), default=datetime.min)

    return [
        *detect_duplicate_utr(bank_lines),
        *detect_genuine_double_settlement(decisions, bank_lines_by_id),
        *detect_missing_settlement(payments, decisions, as_of),
        *detect_fee_tax_contract_violations(decisions, payments_by_order_id),
    ]
