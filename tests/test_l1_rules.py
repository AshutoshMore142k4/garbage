from datetime import datetime, timedelta, timezone

from ledgerguard.l0_normalize.normalize import NormalizedBankLine
from ledgerguard.l1_deterministic import tolerance
from ledgerguard.l1_deterministic.rules import (
    KNOWN_MERCHANT_TOKENS,
    LedgerPayment,
    narration_similarity_score,
    rule_single_payment_net_match,
    rule_subset_sum_split_settlement,
)

BASE = datetime(2026, 1, 5, tzinfo=timezone.utc)


def _bank_line(**overrides) -> NormalizedBankLine:
    defaults = dict(
        id="bl_1", utr="UTR1", credit_paise=100_000, narration="ACMEENTERP7F3A2C",
        value_date=BASE + timedelta(days=4),
    )
    defaults.update(overrides)
    return NormalizedBankLine(**defaults)


def _payment(payment_id, order_id, net_paise, captured_at=BASE) -> LedgerPayment:
    return LedgerPayment(payment_id=payment_id, order_id=order_id, net_paise=net_paise, captured_at=captured_at)


# ---- tolerance ----


def test_tolerance_boundary_exactly_at_min_and_max_is_accepted():
    assert tolerance.within_date_tolerance(BASE, BASE + timedelta(days=2))
    assert tolerance.within_date_tolerance(BASE, BASE + timedelta(days=4))


def test_tolerance_just_outside_boundary_is_rejected():
    assert not tolerance.within_date_tolerance(BASE, BASE + timedelta(days=1, hours=23))
    assert not tolerance.within_date_tolerance(BASE, BASE + timedelta(days=4, hours=1))


# ---- rule_single_payment_net_match ----


def test_single_payment_net_match_positive():
    bl = _bank_line(credit_paise=50_000, value_date=BASE + timedelta(days=3))
    candidates = [_payment("pay_1", "order_1", 50_000)]
    outcome = rule_single_payment_net_match(bl, candidates)
    assert outcome is not None
    assert outcome.resolved
    assert outcome.order_ids == ["order_1"]
    assert outcome.rule_id == "single_payment_net_match"


def test_single_payment_net_match_negative_amount_mismatch():
    bl = _bank_line(credit_paise=50_000, value_date=BASE + timedelta(days=3))
    candidates = [_payment("pay_1", "order_1", 49_000)]
    assert rule_single_payment_net_match(bl, candidates) is None


def test_single_payment_net_match_negative_outside_date_tolerance():
    bl = _bank_line(credit_paise=50_000, value_date=BASE + timedelta(days=10))
    candidates = [_payment("pay_1", "order_1", 50_000)]
    assert rule_single_payment_net_match(bl, candidates) is None


def test_single_payment_net_match_ambiguous_when_two_equally_close_candidates():
    value_date = BASE + timedelta(days=3)
    bl = _bank_line(credit_paise=50_000, value_date=value_date)
    candidates = [
        _payment("pay_1", "order_1", 50_000, captured_at=BASE),
        _payment("pay_2", "order_2", 50_000, captured_at=BASE + timedelta(hours=0)),
    ]
    outcome = rule_single_payment_net_match(bl, candidates)
    assert outcome is not None
    assert not outcome.resolved
    assert outcome.reason_code == "AMBIGUOUS_NARRATION_MULTI_CANDIDATE"


def test_single_payment_net_match_tiebreaks_on_date_when_not_equally_close():
    value_date = BASE + timedelta(days=3)
    bl = _bank_line(credit_paise=50_000, value_date=value_date)
    candidates = [
        _payment("pay_close", "order_close", 50_000, captured_at=BASE),
        _payment("pay_far", "order_far", 50_000, captured_at=BASE - timedelta(days=1)),
    ]
    outcome = rule_single_payment_net_match(bl, candidates)
    assert outcome is not None
    assert outcome.resolved
    assert outcome.order_ids == ["order_close"]
    assert outcome.rule_id == "single_payment_net_match_date_tiebreak"


# ---- rule_subset_sum_split_settlement ----


def test_subset_sum_split_settlement_positive():
    value_date = BASE + timedelta(days=3)
    bl = _bank_line(credit_paise=1500, value_date=value_date)
    candidates = [
        _payment("pay_1", "order_1", 500),
        _payment("pay_2", "order_2", 700),
        _payment("pay_3", "order_3", 300),
    ]
    outcome = rule_subset_sum_split_settlement(bl, candidates)
    assert outcome is not None
    assert outcome.resolved
    assert set(outcome.order_ids) == {"order_1", "order_2", "order_3"}
    assert outcome.rule_id == "subset_sum_split_settlement"


def test_subset_sum_split_settlement_negative_no_combination_fits():
    value_date = BASE + timedelta(days=3)
    bl = _bank_line(credit_paise=999_999, value_date=value_date)
    candidates = [_payment("pay_1", "order_1", 500), _payment("pay_2", "order_2", 700)]
    assert rule_subset_sum_split_settlement(bl, candidates) is None


def test_subset_sum_split_settlement_over_budget_escalates_with_reason_code(monkeypatch):
    value_date = BASE + timedelta(days=3)
    bl = _bank_line(credit_paise=10_000, value_date=value_date)
    candidates = [_payment(f"pay_{i}", f"order_{i}", 7 + i) for i in range(60)]

    from ledgerguard.l1_deterministic import rules as rules_module
    from ledgerguard.l1_deterministic.subset_sum import SubsetSumResult

    monkeypatch.setattr(
        rules_module, "find_subset", lambda *a, **k: SubsetSumResult(found=False, over_budget=True)
    )

    outcome = rule_subset_sum_split_settlement(bl, candidates)
    assert outcome is not None
    assert not outcome.resolved
    assert outcome.reason_code == "SUBSET_SUM_OVER_BUDGET"


# ---- narration_similarity_score ----


def test_narration_similarity_score_positive_for_known_merchant_token():
    score = narration_similarity_score("ACMEENTERP7F3A2C", KNOWN_MERCHANT_TOKENS)
    assert score >= 90


def test_narration_similarity_score_negative_for_unrelated_text():
    score = narration_similarity_score("ZZZQQQXXX999", KNOWN_MERCHANT_TOKENS)
    assert score < 70
