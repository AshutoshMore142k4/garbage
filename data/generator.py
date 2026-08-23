"""Seeded, difficulty-stratified data generator (plan.md #2/#7/#10, phases.md Phase 2).

Produces a bank statement, an internal ledger, and ground truth. Every entity is built from a
single seeded `random.Random(seed)` instance so the whole run is pure given a seed -- no
wall-clock, no unscoped `random` calls (phases.md Phase 2 implementation detail).

Provenance honesty note: this module always synthesizes its own orders/payments (there is no
`data/raw/` from a live Razorpay ingest in this environment -- see docs/razorpay-verification.md
and PROGRESS.md Phase 0/1). Once `ledgerguard.razorpay.ingest` has actually been run against a
live test-mode account, its `data/raw/*.json` should replace the synthesized orders/payments
here and REAL_VS_SIMULATED.md's Orders/Payments/Refunds row should be revisited. Settlements are
*always* SIMULATED regardless of that, per the Phase 0 R1 finding: real settlement batches/UTRs
are not expected to exist for test-mode payments.

Chaos-case taxonomy
--------------------
plan.md/phases.md direct Claude Code to implement "every chaos case from CLAUDE.md Sec.Chaos".
CLAUDE.md does not exist in this repo (flagged in PROGRESS.md since Phase 0), so there is no such
list to follow. The taxonomy below is instead derived directly from cases plan.md itself names
explicitly (#2 Problem Statement, #8 J2/J4, #12 refund timing) plus this phase's own
"Implementation details" in phases.md (split-settlement group sizes; the duplicate-UTR /
genuine-double-settlement matched pair required in holdout). If CLAUDE.md is authored later with
a different or additional list, reconcile against it -- see BROKE.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import string
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ledgerguard.models import BankLine, GroundTruth, Order, Payment, Refund, Settlement

# ---- chaos taxonomy ----

EASY_EXACT_MATCH = "EASY_EXACT_MATCH"
SPLIT_SETTLEMENT = "SPLIT_SETTLEMENT"
LATE_REFUND = "LATE_REFUND"
FEE_TAX_VARIANT = "FEE_TAX_VARIANT"
DATE_SKEW_BOUNDARY = "DATE_SKEW_BOUNDARY"
TRUNCATED_NARRATION = "TRUNCATED_NARRATION"
NO_MATCH_EXISTS = "NO_MATCH_EXISTS"
AMBIGUOUS_MULTI_CANDIDATE = "AMBIGUOUS_MULTI_CANDIDATE"
DUPLICATE_UTR = "DUPLICATE_UTR"
GENUINE_DOUBLE_SETTLEMENT = "GENUINE_DOUBLE_SETTLEMENT"

# The single-bank-line chaos categories (one bank_line produced per instance).
_SINGLE_LINE_CATEGORIES = (
    SPLIT_SETTLEMENT,
    LATE_REFUND,
    FEE_TAX_VARIANT,
    DATE_SKEW_BOUNDARY,
    TRUNCATED_NARRATION,
    NO_MATCH_EXISTS,
    AMBIGUOUS_MULTI_CANDIDATE,
)
# The two-bank-line chaos categories (plan.md #8 J4 / #2's duplicate-vs-double-settlement pair).
_DOUBLE_LINE_CATEGORIES = (DUPLICATE_UTR, GENUINE_DOUBLE_SETTLEMENT)

CATEGORY_DIFFICULTY = {
    EASY_EXACT_MATCH: "EASY",
    SPLIT_SETTLEMENT: "MEDIUM",
    LATE_REFUND: "MEDIUM",
    FEE_TAX_VARIANT: "MEDIUM",
    DATE_SKEW_BOUNDARY: "HARD",
    TRUNCATED_NARRATION: "HARD",
    NO_MATCH_EXISTS: "HARD",
    AMBIGUOUS_MULTI_CANDIDATE: "ADVERSARIAL",
    DUPLICATE_UTR: "ADVERSARIAL",
    GENUINE_DOUBLE_SETTLEMENT: "ADVERSARIAL",
}

DEFAULT_TOTAL_BANK_LINES = 3000
CHAOS_MIN_COUNT = 8  # comfortably above phases.md's ">= 5 instances per category" test bar

BASE_DATE = datetime(2026, 1, 5, tzinfo=timezone.utc)
FEE_RATE = 0.02
ALT_FEE_RATE = 0.035
TAX_RATE_ON_FEE = 0.18  # GST-on-fee, the documented Razorpay-style contract (unverified live)

DEMO_AMOUNT_PAISE = 48_200 * 100
DEMO_VALUE_DATE = BASE_DATE + timedelta(days=60)
# _settle()'s defaults are settle_offset_days=2, bank_delay_days=0, so captured_at + 2 days must
# equal DEMO_VALUE_DATE for L1's date-tolerance rule to actually match the demo pair -- forcing
# only the value_date (as an earlier version of this file did) while leaving the underlying
# order/payment's captured_at randomly drawn could put it *after* the forced value_date,
# making the demo pair structurally unmatchable. See BROKE.md, Phase 6.
# _make_order_payment additionally offsets captured_at by 1-30 minutes past `forced_created` (to
# look like a real capture timestamp), so this constant needs a >=30-minute safety margin below
# the exact 2-day mark or that offset alone pushes captured_at under the MIN_SETTLEMENT_DAYS
# boundary. See BROKE.md, Phase 6 (second bug found in the same fix).
DEMO_CAPTURED_AT = DEMO_VALUE_DATE - timedelta(days=2, minutes=45)
_MERCHANT_TOKENS = ("ACMEENTERP", "GLOBALTRADE", "SUNRISEMART", "APEXRETAIL", "NORTHSTARCO")


@dataclass
class GeneratedDataset:
    orders: list[Order]
    payments: list[Payment]
    refunds: list[Refund]
    settlements: list[Settlement]
    bank_lines: list[BankLine]
    ground_truth: dict[str, GroundTruth]
    category_of: dict[str, str]
    demo_pair: dict[str, str]


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _utr(rng: random.Random) -> str:
    return "".join(rng.choices(string.ascii_uppercase + string.digits, k=16))


def _narration(rng: random.Random, utr: str, hard_truncate: bool = False) -> str:
    merchant = rng.choice(_MERCHANT_TOKENS)
    raw = f"RZPX*{merchant}{utr[:8]}"
    return raw[: 18 if hard_truncate else 30]


def _flip_last_char(s: str) -> str:
    if not s:
        return s
    return s[:-1] + ("0" if s[-1] != "0" else "1")


def _make_order_payment(
    rng: random.Random,
    idx: int,
    amount_paise: int,
    fee_rate: float = FEE_RATE,
    forced_created: datetime | None = None,
) -> tuple[Order, Payment]:
    order_id = f"order_synth_{idx:05d}"
    payment_id = f"pay_synth_{idx:05d}"
    created = forced_created or (BASE_DATE + timedelta(days=rng.randint(0, 120), minutes=rng.randint(0, 1439)))
    # Percentage arithmetic is transiently float; the stored field is always the rounded int
    # paise value below -- no float ever lands in a model field (plan.md Phase 1 money rule).
    fee_paise = round(amount_paise * fee_rate)
    tax_paise = round(fee_paise * TAX_RATE_ON_FEE)
    order = Order(
        id=order_id,
        amount_paise=amount_paise,
        currency="INR",
        created_at=_iso(created),
        source="synthetic_fixture",
    )
    payment = Payment(
        id=payment_id,
        order_id=order_id,
        amount_paise=amount_paise,
        fee_paise=fee_paise,
        tax_paise=tax_paise,
        method=rng.choice(["card", "upi", "netbanking"]),
        status="captured",
        captured_at=_iso(created + timedelta(minutes=rng.randint(1, 30))),
    )
    return order, payment


def _settle(
    rng: random.Random,
    payments: list[Payment],
    settle_offset_days: int = 2,
    bank_delay_days: int = 0,
    hard_truncate_narration: bool = False,
    forced_utr: str | None = None,
    forced_value_date: datetime | None = None,
    forced_narration: str | None = None,
) -> tuple[Settlement, BankLine]:
    net_paise = sum(p.amount_paise - p.fee_paise - p.tax_paise for p in payments)
    last_captured = max(_parse_iso(p.captured_at) for p in payments)
    settled_at = last_captured + timedelta(days=settle_offset_days)
    value_date = forced_value_date or (settled_at + timedelta(days=bank_delay_days))
    utr = forced_utr or _utr(rng)
    settlement_id = f"setl_synth_{utr}"
    settlement = Settlement(
        id=settlement_id, utr=utr, amount_paise=net_paise, settled_at=_iso(settled_at), is_synthetic=True
    )
    narration = forced_narration or _narration(rng, utr, hard_truncate=hard_truncate_narration)
    bank_line = BankLine(
        id=f"bl_{settlement_id}", utr=utr, credit_paise=net_paise, narration=narration, value_date=_iso(value_date)
    )
    return settlement, bank_line


def generate(
    seed: int = 42,
    total_bank_lines: int = DEFAULT_TOTAL_BANK_LINES,
    chaos_min_count: int = CHAOS_MIN_COUNT,
) -> GeneratedDataset:
    rng = random.Random(seed)

    orders: list[Order] = []
    payments: list[Payment] = []
    refunds: list[Refund] = []
    settlements: list[Settlement] = []
    bank_lines: list[BankLine] = []
    ground_truth: dict[str, GroundTruth] = {}
    category_of: dict[str, str] = {}
    demo_pair: dict[str, str] = {}

    _counter = {"n": 0}

    def next_idx() -> int:
        _counter["n"] += 1
        return _counter["n"]

    n_double_line = chaos_min_count * len(_DOUBLE_LINE_CATEGORIES) * 2
    n_single_line = chaos_min_count * len(_SINGLE_LINE_CATEGORIES)
    easy_count = total_bank_lines - n_single_line - n_double_line
    if easy_count <= 0:
        raise ValueError(
            f"total_bank_lines={total_bank_lines} is too small for chaos_min_count={chaos_min_count}; "
            f"need at least {n_single_line + n_double_line + 1}"
        )

    def add_ground_truth(bank_line_id: str, correct_match: dict | None, category: str) -> None:
        ground_truth[bank_line_id] = GroundTruth(
            bank_line_id=bank_line_id,
            correct_match=correct_match,
            difficulty=CATEGORY_DIFFICULTY[category],
            split="train",  # placeholder; overwritten once the final split is computed
        )
        category_of[bank_line_id] = category

    # ---- EASY_EXACT_MATCH: bulk fill, one payment settles cleanly and on time ----
    for _ in range(easy_count):
        amount = rng.randint(10_000, 50_00_000)
        order, payment = _make_order_payment(rng, next_idx(), amount)
        orders.append(order)
        payments.append(payment)
        settlement, bank_line = _settle(rng, [payment])
        settlements.append(settlement)
        bank_lines.append(bank_line)
        add_ground_truth(
            bank_line.id, {"settlement_id": settlement.id, "order_ids": [order.id]}, EASY_EXACT_MATCH
        )

    # ---- SPLIT_SETTLEMENT: one bank credit backs several orders (bounded group size) ----
    group_sizes = [2, 3, 3, 4, 5, 6, 8, 10, 12]
    for i in range(chaos_min_count):
        group_size = group_sizes[i % len(group_sizes)]
        group_orders, group_payments = [], []
        for _ in range(group_size):
            amount = rng.randint(10_000, 20_00_000)
            order, payment = _make_order_payment(rng, next_idx(), amount)
            orders.append(order)
            payments.append(payment)
            group_orders.append(order)
            group_payments.append(payment)
        settlement, bank_line = _settle(rng, group_payments)
        settlements.append(settlement)
        bank_lines.append(bank_line)
        add_ground_truth(
            bank_line.id,
            {"settlement_id": settlement.id, "order_ids": [o.id for o in group_orders]},
            SPLIT_SETTLEMENT,
        )

    # ---- LATE_REFUND: a partial refund lands after the settlement it modifies ----
    for _ in range(chaos_min_count):
        amount = rng.randint(10_000, 20_00_000)
        order, payment = _make_order_payment(rng, next_idx(), amount)
        orders.append(order)
        payments.append(payment)
        settlement, bank_line = _settle(rng, [payment])
        settlements.append(settlement)
        bank_lines.append(bank_line)
        settled_at = _parse_iso(settlement.settled_at)
        refund_amount = int(payment.amount_paise * rng.uniform(0.1, 0.5))
        refund = Refund(
            id=f"rfnd_synth_{next_idx():05d}",
            payment_id=payment.id,
            amount_paise=refund_amount,
            created_at=_iso(settled_at + timedelta(days=rng.randint(1, 5))),
        )
        refunds.append(refund)
        add_ground_truth(
            bank_line.id, {"settlement_id": settlement.id, "order_ids": [order.id]}, LATE_REFUND
        )

    # ---- FEE_TAX_VARIANT: a different fee contract widens gross vs net ----
    for _ in range(chaos_min_count):
        amount = rng.randint(10_000, 20_00_000)
        order, payment = _make_order_payment(rng, next_idx(), amount, fee_rate=ALT_FEE_RATE)
        orders.append(order)
        payments.append(payment)
        settlement, bank_line = _settle(rng, [payment])
        settlements.append(settlement)
        bank_lines.append(bank_line)
        add_ground_truth(
            bank_line.id, {"settlement_id": settlement.id, "order_ids": [order.id]}, FEE_TAX_VARIANT
        )

    # ---- DATE_SKEW_BOUNDARY: bank value_date sits exactly at, or just past, the T+2 tolerance ----
    for i in range(chaos_min_count):
        amount = rng.randint(10_000, 20_00_000)
        order, payment = _make_order_payment(rng, next_idx(), amount)
        orders.append(order)
        payments.append(payment)
        bank_delay = 2 if i % 2 == 0 else 3
        settlement, bank_line = _settle(rng, [payment], bank_delay_days=bank_delay)
        settlements.append(settlement)
        bank_lines.append(bank_line)
        add_ground_truth(
            bank_line.id, {"settlement_id": settlement.id, "order_ids": [order.id]}, DATE_SKEW_BOUNDARY
        )

    # ---- TRUNCATED_NARRATION: bank narration hard-truncated below the merchant token ----
    for _ in range(chaos_min_count):
        amount = rng.randint(10_000, 20_00_000)
        order, payment = _make_order_payment(rng, next_idx(), amount)
        orders.append(order)
        payments.append(payment)
        settlement, bank_line = _settle(rng, [payment], hard_truncate_narration=True)
        settlements.append(settlement)
        bank_lines.append(bank_line)
        add_ground_truth(
            bank_line.id, {"settlement_id": settlement.id, "order_ids": [order.id]}, TRUNCATED_NARRATION
        )

    # ---- NO_MATCH_EXISTS: a stray bank credit with no backing settlement at all ----
    for _ in range(chaos_min_count):
        amount = rng.randint(10_000, 20_00_000)
        utr = _utr(rng)
        bank_line = BankLine(
            id=f"bl_stray_{next_idx():05d}",
            utr=utr,
            credit_paise=amount,
            narration=_narration(rng, utr),
            value_date=_iso(BASE_DATE + timedelta(days=rng.randint(0, 150))),
        )
        bank_lines.append(bank_line)
        add_ground_truth(bank_line.id, None, NO_MATCH_EXISTS)

    # ---- AMBIGUOUS_MULTI_CANDIDATE: a same-amount decoy order sits unsettled in the ledger ----
    for _ in range(chaos_min_count):
        amount = rng.randint(1_00_000, 5_00_000)
        order_a, payment_a = _make_order_payment(rng, next_idx(), amount)
        order_b, payment_b = _make_order_payment(rng, next_idx(), amount)  # decoy: never settled
        orders += [order_a, order_b]
        payments += [payment_a, payment_b]
        settlement, bank_line = _settle(rng, [payment_a])
        settlements.append(settlement)
        bank_lines.append(bank_line)
        add_ground_truth(
            bank_line.id,
            {"settlement_id": settlement.id, "order_ids": [order_a.id]},
            AMBIGUOUS_MULTI_CANDIDATE,
        )

    # ---- DUPLICATE_UTR: a reporting glitch posts the same real settlement twice ----
    for i in range(chaos_min_count):
        is_demo = i == 0
        amount = DEMO_AMOUNT_PAISE if is_demo else rng.randint(1_00_000, 5_00_000)
        order, payment = _make_order_payment(
            rng, next_idx(), amount, forced_created=DEMO_CAPTURED_AT if is_demo else None
        )
        orders.append(order)
        payments.append(payment)
        settlement, bank_line = _settle(
            rng,
            [payment],
            forced_value_date=DEMO_VALUE_DATE if is_demo else None,
            forced_narration=f"RZPX*{_MERCHANT_TOKENS[0]}7F3A2C" if is_demo else None,
        )
        settlements.append(settlement)
        bank_lines.append(bank_line)
        dup_bank_line = BankLine(
            id=f"bl_dup_{next_idx():05d}",
            utr=settlement.utr,
            credit_paise=settlement.amount_paise,
            narration=bank_line.narration,
            value_date=bank_line.value_date,
        )
        bank_lines.append(dup_bank_line)
        add_ground_truth(
            bank_line.id, {"settlement_id": settlement.id, "order_ids": [order.id]}, DUPLICATE_UTR
        )
        # The duplicate is a reporting artifact, not a second real credit: its correct answer is
        # "no match" -- posting against it would double-count money that was only sent once.
        add_ground_truth(dup_bank_line.id, None, DUPLICATE_UTR)
        if is_demo:
            demo_pair["duplicate_utr_bank_line_id"] = dup_bank_line.id

    # ---- GENUINE_DOUBLE_SETTLEMENT: the same order batch is really credited twice ----
    for i in range(chaos_min_count):
        is_demo = i == 0
        amount = DEMO_AMOUNT_PAISE if is_demo else rng.randint(1_00_000, 5_00_000)
        order, payment = _make_order_payment(
            rng, next_idx(), amount, forced_created=DEMO_CAPTURED_AT if is_demo else None
        )
        orders.append(order)
        payments.append(payment)
        settlement_1, bank_line_1 = _settle(
            rng,
            [payment],
            forced_value_date=DEMO_VALUE_DATE if is_demo else None,
            forced_narration=f"RZPX*{_MERCHANT_TOKENS[0]}7F3A21" if is_demo else None,
        )
        utr_2 = _utr(rng)
        settlement_2 = Settlement(
            id=f"setl_synth_{utr_2}",
            utr=utr_2,
            amount_paise=settlement_1.amount_paise,
            settled_at=settlement_1.settled_at,
            is_synthetic=True,
        )
        bank_line_2 = BankLine(
            id=f"bl_{settlement_2.id}",
            utr=utr_2,
            credit_paise=settlement_1.amount_paise,
            narration=_flip_last_char(bank_line_1.narration),
            value_date=bank_line_1.value_date,
        )
        settlements += [settlement_1, settlement_2]
        bank_lines += [bank_line_1, bank_line_2]
        # Both credits are real -- the merchant really was paid twice for the same order batch.
        add_ground_truth(
            bank_line_1.id,
            {"settlement_id": settlement_1.id, "order_ids": [order.id]},
            GENUINE_DOUBLE_SETTLEMENT,
        )
        add_ground_truth(
            bank_line_2.id,
            {"settlement_id": settlement_2.id, "order_ids": [order.id]},
            GENUINE_DOUBLE_SETTLEMENT,
        )
        if is_demo:
            demo_pair["genuine_double_settlement_bank_line_id"] = bank_line_2.id

    # ---- split assignment: 60/20/20, disjoint, with the demo pair forced into holdout ----
    forced_holdout = set(demo_pair.values())
    all_ids = [bl.id for bl in bank_lines]
    remaining_ids = [i for i in all_ids if i not in forced_holdout]
    rng.shuffle(remaining_ids)

    n_total = len(all_ids)
    target_holdout = max(round(n_total * 0.2), len(forced_holdout))
    target_train = round(n_total * 0.6)
    extra_holdout_needed = target_holdout - len(forced_holdout)

    holdout_ids = list(forced_holdout) + remaining_ids[:extra_holdout_needed]
    rest = remaining_ids[extra_holdout_needed:]
    train_ids = rest[:target_train]
    val_ids = rest[target_train:]

    split_of: dict[str, str] = {}
    for bid in holdout_ids:
        split_of[bid] = "holdout"
    for bid in train_ids:
        split_of[bid] = "train"
    for bid in val_ids:
        split_of[bid] = "validation"

    for bid, split in split_of.items():
        ground_truth[bid] = ground_truth[bid].model_copy(update={"split": split})

    return GeneratedDataset(
        orders=orders,
        payments=payments,
        refunds=refunds,
        settlements=settlements,
        bank_lines=bank_lines,
        ground_truth=ground_truth,
        category_of=category_of,
        demo_pair=demo_pair,
    )


def write_dataset(dataset: GeneratedDataset, out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bank_lines_sorted = sorted(dataset.bank_lines, key=lambda b: b.id)
    with open(out_dir / "bank_statement.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "utr", "credit_paise", "narration", "value_date"])
        for bl in bank_lines_sorted:
            writer.writerow([bl.id, bl.utr or "", bl.credit_paise, bl.narration, bl.value_date])

    orders_by_id = {o.id: o for o in dataset.orders}
    payments_by_order: dict[str, list[Payment]] = {}
    for p in dataset.payments:
        payments_by_order.setdefault(p.order_id, []).append(p)
    refunds_by_payment: dict[str, list[Refund]] = {}
    for r in dataset.refunds:
        refunds_by_payment.setdefault(r.payment_id, []).append(r)

    with open(out_dir / "internal_ledger.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "order_id", "order_amount_paise", "currency", "order_created_at",
                "payment_id", "payment_status", "fee_paise", "tax_paise", "captured_at",
                "refund_id", "refund_amount_paise", "refund_created_at",
            ]
        )
        for order_id in sorted(orders_by_id):
            order = orders_by_id[order_id]
            for payment in sorted(payments_by_order.get(order_id, []), key=lambda p: p.id):
                payment_refunds = refunds_by_payment.get(payment.id) or [None]
                for refund in payment_refunds:
                    writer.writerow(
                        [
                            order.id, order.amount_paise, order.currency, order.created_at,
                            payment.id, payment.status, payment.fee_paise, payment.tax_paise,
                            payment.captured_at,
                            refund.id if refund else "",
                            refund.amount_paise if refund else "",
                            refund.created_at if refund else "",
                        ]
                    )

    ground_truth_out = {bid: dataset.ground_truth[bid].model_dump() for bid in sorted(dataset.ground_truth)}
    (out_dir / "ground_truth.json").write_text(
        json.dumps(ground_truth_out, indent=2, sort_keys=True), encoding="utf-8"
    )

    category_counts = Counter(dataset.category_of.values())
    manifest = {
        "category_counts": dict(sorted(category_counts.items())),
        "demo_pair": dataset.demo_pair,
        "total_bank_lines": len(dataset.bank_lines),
    }
    (out_dir / "chaos_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def main() -> None:
    import os

    parser = argparse.ArgumentParser(description="Generate LedgerGuard's seeded reconciliation dataset.")
    parser.add_argument("--seed", type=int, default=int(os.environ.get("SEED", 42)))
    parser.add_argument("--size", type=int, default=DEFAULT_TOTAL_BANK_LINES)
    parser.add_argument("--out", type=Path, default=Path("data/raw"))
    args = parser.parse_args()

    dataset = generate(seed=args.seed, total_bank_lines=args.size)
    write_dataset(dataset, args.out)

    counts = Counter(dataset.category_of.values())
    print(f"Generated {len(dataset.bank_lines)} bank lines (seed={args.seed}) -> {args.out}/")
    for category in sorted(counts):
        print(f"  {category}: {counts[category]}")
    print(f"  demo pair: {dataset.demo_pair}")


if __name__ == "__main__":
    main()
