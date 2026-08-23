from ledgerguard.l3_calibrate_gate.cost_model import (
    ESCALATION_COST_PAISE,
    CostDecision,
    expected_cost_paise,
    find_optimal_threshold,
)


def _decisions():
    return [
        CostDecision(credit_paise=100_000, calibrated_confidence=0.99, correct=True),
        CostDecision(credit_paise=200_000, calibrated_confidence=0.95, correct=True),
        CostDecision(credit_paise=500_000, calibrated_confidence=0.6, correct=False),  # a costly false positive
        CostDecision(credit_paise=10_000, calibrated_confidence=0.2, correct=True),
    ]


def test_expected_cost_at_threshold_zero_counts_every_wrong_amount():
    decisions = _decisions()
    cost = expected_cost_paise(0.0, decisions)
    assert cost == 500_000  # only the incorrect one contributes; correct auto-posts are free


def test_expected_cost_at_threshold_one_counts_only_escalation_fees():
    decisions = _decisions()
    cost = expected_cost_paise(1.0, decisions)
    assert cost == ESCALATION_COST_PAISE * len(decisions)


def test_find_optimal_threshold_is_strictly_inside_0_1():
    # Constructed so neither extreme wins: auto-posting everything eats the large false
    # positive's amount, escalating everything pays four small fees, but a mid threshold
    # (letting the two very-high-confidence correct ones through, escalating the rest) is cheapest.
    decisions = _decisions()
    threshold = find_optimal_threshold(decisions)
    assert 0.0 < threshold < 1.0


def test_find_optimal_threshold_actually_minimizes_cost():
    decisions = _decisions()
    threshold = find_optimal_threshold(decisions)
    chosen_cost = expected_cost_paise(threshold, decisions)
    assert chosen_cost <= expected_cost_paise(0.0, decisions)
    assert chosen_cost <= expected_cost_paise(1.0, decisions)
