from datetime import datetime, timedelta, timezone

from ledgerguard.l1_deterministic.rules import LedgerPayment
from ledgerguard.l3_calibrate_gate.decisions import Decision
from ledgerguard.l4_anomaly.detectors import (
    detect_duplicate_utr,
    detect_fee_tax_contract_violations,
    detect_genuine_double_settlement,
    detect_missing_settlement,
)

BASE = datetime(2026, 1, 5, tzinfo=timezone.utc)


def _decision(bank_line_id, order_ids, correct=True) -> Decision:
    return Decision(
        bank_line_id=bank_line_id,
        split="holdout",
        credit_paise=50_000,
        resolver="L1_RULE",
        rule_id="single_payment_net_match",
        order_ids=order_ids,
        raw_confidence=0.9,
        reason_code=None,
        evidence=[],
        features={},
        correct=correct,
    )


def test_detect_duplicate_utr_flags_every_line_sharing_a_utr():
    bank_lines = [
        {"id": "bl_1", "utr": "UTR-A"},
        {"id": "bl_2", "utr": "UTR-A"},
        {"id": "bl_3", "utr": "UTR-B"},
    ]
    flags = detect_duplicate_utr(bank_lines)
    flagged_ids = {f.bank_line_id for f in flags}
    assert flagged_ids == {"bl_1", "bl_2"}
    assert all(f.reason_code == "DUPLICATE_UTR" for f in flags)


def test_detect_duplicate_utr_ignores_missing_or_blank_utr():
    bank_lines = [{"id": "bl_1", "utr": ""}, {"id": "bl_2", "utr": None}]
    assert detect_duplicate_utr(bank_lines) == []


def test_detect_genuine_double_settlement_requires_distinct_utrs():
    decisions = [_decision("bl_1", ["order_1"]), _decision("bl_2", ["order_1"])]
    bank_lines_by_id = {"bl_1": {"utr": "UTR-A"}, "bl_2": {"utr": "UTR-B"}}

    flags = detect_genuine_double_settlement(decisions, bank_lines_by_id)

    flagged_ids = {f.bank_line_id for f in flags}
    assert flagged_ids == {"bl_1", "bl_2"}
    assert all(f.reason_code == "GENUINE_DOUBLE_SETTLEMENT" for f in flags)


def test_detect_genuine_double_settlement_does_not_fire_on_same_utr():
    # Same order, same UTR -- this is detect_duplicate_utr's job, not this detector's.
    decisions = [_decision("bl_1", ["order_1"]), _decision("bl_2", ["order_1"])]
    bank_lines_by_id = {"bl_1": {"utr": "UTR-A"}, "bl_2": {"utr": "UTR-A"}}

    assert detect_genuine_double_settlement(decisions, bank_lines_by_id) == []


def test_detect_genuine_double_settlement_does_not_fire_on_a_single_match():
    decisions = [_decision("bl_1", ["order_1"])]
    bank_lines_by_id = {"bl_1": {"utr": "UTR-A"}}
    assert detect_genuine_double_settlement(decisions, bank_lines_by_id) == []


def test_detect_missing_settlement_flags_overdue_unmatched_payments():
    payments = [LedgerPayment(payment_id="pay_1", order_id="order_1", net_paise=1000, captured_at=BASE)]
    decisions: list[Decision] = []  # nothing ever matched order_1
    as_of = BASE + timedelta(days=10)

    flags = detect_missing_settlement(payments, decisions, as_of)

    assert len(flags) == 1
    assert flags[0].bank_line_id is None
    assert flags[0].reason_code == "MISSING_SETTLEMENT"


def test_detect_missing_settlement_does_not_flag_matched_payments():
    payments = [LedgerPayment(payment_id="pay_1", order_id="order_1", net_paise=1000, captured_at=BASE)]
    decisions = [_decision("bl_1", ["order_1"])]
    as_of = BASE + timedelta(days=10)

    assert detect_missing_settlement(payments, decisions, as_of) == []


def test_detect_missing_settlement_does_not_flag_recent_payments():
    payments = [LedgerPayment(payment_id="pay_1", order_id="order_1", net_paise=1000, captured_at=BASE)]
    as_of = BASE + timedelta(days=1)  # not overdue yet
    assert detect_missing_settlement(payments, [], as_of) == []


def test_detect_fee_tax_contract_violation_flags_out_of_band_fee_rate():
    payment = LedgerPayment(
        payment_id="pay_1", order_id="order_1", net_paise=0, captured_at=BASE,
        amount_paise=100_000, fee_paise=3_500, tax_paise=630,  # 3.5% fee, outside the 1.5-2.5% band
    )
    decisions = [_decision("bl_1", ["order_1"])]
    flags = detect_fee_tax_contract_violations(decisions, {"order_1": payment})
    assert len(flags) == 1
    assert flags[0].reason_code == "FEE_TAX_CONTRACT_VIOLATION"


def test_detect_fee_tax_contract_violation_does_not_fire_within_band():
    payment = LedgerPayment(
        payment_id="pay_1", order_id="order_1", net_paise=0, captured_at=BASE,
        amount_paise=100_000, fee_paise=2_000, tax_paise=360,  # 2% fee, 18% tax-on-fee -- in band
    )
    decisions = [_decision("bl_1", ["order_1"])]
    assert detect_fee_tax_contract_violations(decisions, {"order_1": payment}) == []
