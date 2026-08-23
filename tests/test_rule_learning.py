"""D1 tests (phases.md Phase 8): the three specific tests the phase names, plus direct unit
coverage of propose/validate/promote and an end-to-end check of the measured decline
eval/rule_learning.py reports. See PROGRESS.md Phase 8 for the measured numbers this pins.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ledgerguard.d1_rule_learning.compile import compile_rule
from ledgerguard.d1_rule_learning.promote import decide_status, load_learned_rules, promote_rule, save_learned_rule, spec_id
from ledgerguard.d1_rule_learning.propose import ResolvedException, best_matching_merchant_token, propose_rule
from ledgerguard.d1_rule_learning.validate import ValidationResult, validate_rule
from ledgerguard.db import init_db
from ledgerguard.l0_normalize.normalize import normalize_bank_line
from ledgerguard.l1_deterministic.matcher import PaymentIndex, run_l1
from ledgerguard.l1_deterministic.rules import LedgerPayment

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _payment(payment_id, order_id, net_paise, captured_at):
    return LedgerPayment(payment_id=payment_id, order_id=order_id, net_paise=net_paise, captured_at=captured_at)


def _bank_line(bank_line_id, credit_paise, narration, value_date):
    return {
        "id": bank_line_id,
        "utr": "",
        "credit_paise": str(credit_paise),
        "narration": narration,
        "value_date": value_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def test_propose_rule_widens_tolerance_and_picks_the_matching_merchant_token():
    resolved = ResolvedException(
        bank_line_id="bl_1",
        narration="RZPX*APEXRETAIL7F3A2C",
        credit_paise=100_000,
        value_date=BASE + timedelta(days=5),
        chosen_payment_id="pay_1",
        chosen_order_id="order_1",
        chosen_captured_at=BASE,  # observed gap: 5 days, past the built-in [2,4] window
    )
    spec = propose_rule(resolved)
    assert spec["narration_prefix"] == "APEXRETAIL"
    assert spec["match_key"] == "single_net_amount_exact"
    assert spec["date_tolerance_days"] == {"min": 2, "max": 5}
    assert best_matching_merchant_token("RZPX*APEXRETAIL7F3A2C") == "APEXRETAIL"


def test_validate_counts_hits_and_false_positives_and_skips_what_builtins_already_resolve():
    # bl_a and bl_b: genuinely learnable -- 5 days late, unique candidate, narration matches.
    # bl_c: the rule's amount+narration+widened-window condition fires, but the true answer
    # (per ground truth) is a *different* order -- a genuine false positive.
    # bl_d: within the built-in [2,4] window already -- built-ins resolve it first, so the
    # candidate rule must never even be evaluated against it.
    payments = [
        _payment("pay_a", "order_a", 100_000, BASE),
        _payment("pay_b", "order_b", 200_000, BASE + timedelta(days=10)),
        _payment("pay_c_wrong", "order_c_wrong", 300_000, BASE + timedelta(days=20)),
        _payment("pay_d", "order_d", 400_000, BASE + timedelta(days=30, hours=3)),
    ]
    bank_lines = [
        _bank_line("bl_a", 100_000, "RZPX*APEXRETAIL7F3A2C", BASE + timedelta(days=5)),
        _bank_line("bl_b", 200_000, "RZPX*APEXRETAIL9K2L1M", BASE + timedelta(days=15)),
        # ground truth says order_c is correct, but the only candidate in the widened window is
        # order_c_wrong -- the rule fires and gets it wrong.
        _bank_line("bl_c", 300_000, "RZPX*APEXRETAIL5Q8R3T", BASE + timedelta(days=25)),
        _bank_line("bl_d", 400_000, "RZPX*APEXRETAIL2W7Y4U", BASE + timedelta(days=32)),
    ]
    ground_truth = {
        "bl_a": {"split": "train", "correct_match": {"order_ids": ["order_a"]}},
        "bl_b": {"split": "train", "correct_match": {"order_ids": ["order_b"]}},
        "bl_c": {"split": "train", "correct_match": {"order_ids": ["order_c_actually_correct"]}},
        "bl_d": {"split": "train", "correct_match": {"order_ids": ["order_d"]}},
    }
    spec = {
        "narration_prefix": "APEXRETAIL",
        "match_key": "single_net_amount_exact",
        "date_tolerance_days": {"min": 2, "max": 5},
    }

    result = validate_rule(spec, bank_lines, payments, ground_truth)
    assert result.hits == 2  # bl_a, bl_b
    assert result.false_positives == 1  # bl_c
    assert "bl_d" not in result.fired_bank_line_ids  # built-ins already resolved it


def test_a_rule_with_a_single_false_positive_is_rejected_even_with_enough_hits():
    result = ValidationResult(hits=5, false_positives=1)
    assert decide_status(result) == "REJECTED"

    clean_result = ValidationResult(hits=3, false_positives=0)
    assert decide_status(clean_result) == "PROMOTED"

    insufficient_result = ValidationResult(hits=2, false_positives=0)
    assert decide_status(insufficient_result) == "REJECTED"


def test_promoted_rule_resolves_at_l1_on_the_next_batch_and_drops_invocation_rate():
    # Three payments settling 5 days late for the same counterparty -- batch 1 resolves none of
    # them at L1 (outside the built-in [2,4] window), all three would need L2. A rule proposed
    # from the *first* one, once promoted, should resolve the remaining two directly at L1.
    payments = [
        _payment("pay_1", "order_1", 100_000, BASE),
        _payment("pay_2", "order_2", 150_000, BASE + timedelta(days=10)),
        _payment("pay_3", "order_3", 175_000, BASE + timedelta(days=20)),
    ]
    bank_lines = [
        _bank_line("bl_1", 100_000, "RZPX*APEXRETAIL7F3A2C", BASE + timedelta(days=5)),
        _bank_line("bl_2", 150_000, "RZPX*APEXRETAIL9K2L1M", BASE + timedelta(days=15)),
        _bank_line("bl_3", 175_000, "RZPX*APEXRETAIL5Q8R3T", BASE + timedelta(days=25)),
    ]
    ground_truth = {
        "bl_1": {"split": "train", "correct_match": {"order_ids": ["order_1"]}},
        "bl_2": {"split": "train", "correct_match": {"order_ids": ["order_2"]}},
        "bl_3": {"split": "train", "correct_match": {"order_ids": ["order_3"]}},
    }

    # Before any rule: all three escalate (nothing resolves at L1).
    baseline = run_l1(bank_lines, payments)
    assert all(not outcome.resolved for outcome in baseline.values())

    resolved = ResolvedException(
        bank_line_id="bl_1",
        narration="RZPX*APEXRETAIL7F3A2C",
        credit_paise=100_000,
        value_date=BASE + timedelta(days=5),
        chosen_payment_id="pay_1",
        chosen_order_id="order_1",
        chosen_captured_at=BASE,
    )
    spec = propose_rule(resolved)
    result = validate_rule(spec, bank_lines, payments, ground_truth)
    assert decide_status(result) == "PROMOTED"

    learned = compile_rule(spec, rule_id=spec_id(spec))
    with_rule = run_l1(bank_lines, payments, extra_rules=(learned,))
    assert all(outcome.resolved for outcome in with_rule.values())
    for bank_line_id, outcome in with_rule.items():
        assert set(outcome.order_ids) == set(ground_truth[bank_line_id]["correct_match"]["order_ids"])

    # The metric this phase is about: 3/3 would have needed L2 before, 0/3 need it after.
    invocations_before = sum(1 for o in baseline.values() if not o.resolved)
    invocations_after = sum(1 for o in with_rule.values() if not o.resolved)
    assert invocations_before == 3
    assert invocations_after == 0


def test_the_registry_survives_a_restart(tmp_path):
    db_path = tmp_path / "ledgerguard.db"

    spec = {
        "narration_prefix": "APEXRETAIL",
        "match_key": "single_net_amount_exact",
        "date_tolerance_days": {"min": 2, "max": 5},
    }
    result = ValidationResult(hits=3, false_positives=0)
    rule = promote_rule(spec, proposed_from="bl_1", result=result, promoted_at="batch-0")
    assert rule.status == "PROMOTED"

    conn = init_db(db_path)
    save_learned_rule(conn, rule)
    conn.close()

    # A fresh connection to the same file -- simulating a process restart.
    reopened = init_db(db_path)
    reloaded = load_learned_rules(reopened, status="PROMOTED")
    reopened.close()

    assert len(reloaded) == 1
    assert reloaded[0].rule_id == rule.rule_id
    assert reloaded[0].spec == spec
    assert reloaded[0].validation_hits == 3
    assert reloaded[0].validation_false_positives == 0


def test_rule_learning_eval_shows_a_measured_declining_invocation_rate():
    from eval.rule_learning import run_rule_learning_eval

    stats = run_rule_learning_eval()

    assert len(stats) == 3
    assert stats[0].invocation_rate > stats[-1].invocation_rate  # the headline metric: it falls
    assert stats[-1].precision_auto_post >= stats[0].precision_auto_post - 0.01  # doesn't degrade
    assert stats[-1].cost_usd / stats[-1].total < stats[0].cost_usd / stats[0].total  # cost/record falls too
    assert any(s.promoted_this_batch for s in stats)  # at least one rule actually got promoted
