"""L1 orchestration (plan.md #9/#10, phases.md Phase 3): turns L0-normalized bank lines and
ledger payments into MatchOutcomes, and emits the residual set L2 (Phase 4) will see.

Design invariant asserted here and re-checked by Phase 4's test_l2_never_sees_resolved.py: a
bank_line L1 resolves must never appear in the residual output.

Rules fire in `rules.BUILTIN_RULES` order (single-payment net match, then bounded subset-sum);
the first one that returns a terminal outcome wins. Candidate payments for a bank line are only
those captured within `MAX_LOOKBACK_DAYS` before its value_date -- this bounds both correctness
(no absurd matches far apart in time) and subset-sum's search space.

Known, intentional gap at this phase: L1 has no duplicate-UTR detection (see rules/__init__.py's
module docstring for why -- it's L4's job per phases.md Phase 6, and an earlier attempt at doing
it here was both buggy and out of scope). Concretely, this means the "reporting artifact" half of
a duplicate-UTR pair will currently get matched to the same order as its real counterpart,
which is wrong relative to ground truth -- and is expected to stay wrong until L4 exists to veto
it. This is recorded in PROGRESS.md/BROKE.md, not hidden in the accuracy numbers.
"""
from __future__ import annotations

import bisect
import csv
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from ledgerguard.l0_normalize.normalize import normalize_bank_line, normalize_timestamp
from ledgerguard.l1_deterministic.rules import (
    LedgerPayment,
    MatchOutcome,
    rule_single_payment_net_match,
    rule_subset_sum_split_settlement,
)

MAX_LOOKBACK_DAYS = 10


def load_ledger_payments(ledger_csv_path: Path) -> list[LedgerPayment]:
    payments: dict[str, LedgerPayment] = {}
    with open(ledger_csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            payment_id = row["payment_id"]
            if not payment_id or payment_id in payments:
                continue
            net_paise = int(row["order_amount_paise"]) - int(row["fee_paise"]) - int(row["tax_paise"])
            payments[payment_id] = LedgerPayment(
                payment_id=payment_id,
                order_id=row["order_id"],
                net_paise=net_paise,
                captured_at=normalize_timestamp(row["captured_at"]),
            )
    return list(payments.values())


def load_bank_lines(bank_statement_csv_path: Path) -> list[dict]:
    with open(bank_statement_csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class PaymentIndex:
    """Payments sorted by captured_at, so each bank line's candidate window is a binary search
    rather than a full scan -- matters once the dataset reaches plan.md's ~3,000-record scale.
    """

    def __init__(self, payments: list[LedgerPayment]):
        self._payments = sorted(payments, key=lambda p: p.captured_at)
        self._captured_ats = [p.captured_at for p in self._payments]

    def candidates_before(self, value_date: datetime, lookback_days: int = MAX_LOOKBACK_DAYS) -> list[LedgerPayment]:
        earliest = datetime.fromtimestamp(value_date.timestamp() - lookback_days * 86400, tz=value_date.tzinfo)
        lo = bisect.bisect_left(self._captured_ats, earliest)
        hi = bisect.bisect_right(self._captured_ats, value_date)
        return self._payments[lo:hi]


def match_bank_line(bank_line_row: dict, index: PaymentIndex) -> MatchOutcome:
    bl = normalize_bank_line(bank_line_row)
    candidates = index.candidates_before(bl.value_date)

    outcome = rule_single_payment_net_match(bl, candidates)
    if outcome is not None:
        return outcome

    outcome = rule_subset_sum_split_settlement(bl, candidates)
    if outcome is not None:
        return outcome

    if not candidates:
        return MatchOutcome(
            resolved=False,
            reason_code="NO_CANDIDATE_FOUND",
            evidence=[f"no ledger payment captured within {MAX_LOOKBACK_DAYS} days before this credit"],
        )
    return MatchOutcome(
        resolved=False,
        reason_code="AMOUNT_GAP_EXCEEDS_TOLERANCE",
        evidence=[f"{len(candidates)} candidates in the lookback window; none (alone or combined) match the credit"],
        candidate_payment_ids=[p.payment_id for p in candidates],
    )


def run_l1(bank_lines: list[dict], payments: list[LedgerPayment]) -> dict[str, MatchOutcome]:
    index = PaymentIndex(payments)
    results: dict[str, MatchOutcome] = {}
    for row in sorted(bank_lines, key=lambda r: r["id"]):
        results[row["id"]] = match_bank_line(row, index)
    return results


MAX_CANDIDATES_FOR_L2 = 10


def write_residual(
    results: dict[str, MatchOutcome],
    bank_lines: list[dict],
    payments: list[LedgerPayment],
    out_path: Path,
    max_candidates: int = MAX_CANDIDATES_FOR_L2,
) -> None:
    """Emits one JSON line per unresolved bank line, each carrying the bounded candidate set
    (payment_id/order_id/net_paise/captured_at, closest-by-date first, capped at
    `max_candidates`) that L2 (Phase 4) will be handed -- never the full ledger.
    """
    bank_lines_by_id = {row["id"]: row for row in bank_lines}
    payments_by_id = {p.payment_id: p for p in payments}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for bank_line_id in sorted(results):
            outcome = results[bank_line_id]
            if outcome.resolved:
                continue

            bl_row = bank_lines_by_id[bank_line_id]
            value_date = normalize_timestamp(bl_row["value_date"])
            candidate_payments = sorted(
                (payments_by_id[pid] for pid in outcome.candidate_payment_ids if pid in payments_by_id),
                key=lambda p: abs((value_date - p.captured_at).total_seconds()),
            )[:max_candidates]
            candidates = [
                {
                    "payment_id": p.payment_id,
                    "order_id": p.order_id,
                    "net_paise": p.net_paise,
                    "captured_at": p.captured_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                for p in candidate_payments
            ]

            outcome_fields = {k: v for k, v in asdict(outcome).items() if k != "candidate_payment_ids"}
            record = {
                "bank_line_id": bank_line_id,
                "credit_paise": int(bl_row["credit_paise"]),
                "narration": bl_row["narration"],
                "value_date": bl_row["value_date"],
                "candidates": candidates,
                **outcome_fields,
            }
            f.write(json.dumps(record, sort_keys=True) + "\n")


def score_against_ground_truth(
    results: dict[str, MatchOutcome], ground_truth: dict[str, dict], split: str | None = None
) -> dict:
    considered = 0
    resolved = 0
    correct = 0
    for bank_line_id, gt in ground_truth.items():
        if split is not None and gt.get("split") != split:
            continue
        considered += 1
        outcome = results.get(bank_line_id)
        if outcome is None or not outcome.resolved:
            continue
        resolved += 1
        expected = gt.get("correct_match")
        expected_orders = set(expected["order_ids"]) if expected else set()
        if set(outcome.order_ids) == expected_orders:
            correct += 1
    return {
        "considered": considered,
        "resolved": resolved,
        "resolution_rate": resolved / considered if considered else 0.0,
        "correct": correct,
        "precision_among_resolved": correct / resolved if resolved else 0.0,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the L1 deterministic matcher.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--residual-out", type=Path, default=None)
    args = parser.parse_args()

    data_dir = args.data_dir
    if not (data_dir / "bank_statement.csv").exists():
        data_dir = Path("data/samples")

    bank_lines = load_bank_lines(data_dir / "bank_statement.csv")
    payments = load_ledger_payments(data_dir / "internal_ledger.csv")
    ground_truth = json.loads((data_dir / "ground_truth.json").read_text())

    results = run_l1(bank_lines, payments)

    residual_out = args.residual_out or (data_dir / "residual.jsonl")
    write_residual(results, bank_lines, payments, residual_out)

    overall = score_against_ground_truth(results, ground_truth)
    validation = score_against_ground_truth(results, ground_truth, split="validation")
    print(f"L1 rules-only, {data_dir}/:")
    print(f"  overall:    resolved {overall['resolved']}/{overall['considered']} "
          f"({overall['resolution_rate']:.1%}), precision {overall['precision_among_resolved']:.1%}")
    print(f"  validation: resolved {validation['resolved']}/{validation['considered']} "
          f"({validation['resolution_rate']:.1%}), precision {validation['precision_among_resolved']:.1%}")
    print(f"  residual written to {residual_out}")


if __name__ == "__main__":
    main()
