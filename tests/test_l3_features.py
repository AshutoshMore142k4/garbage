from ledgerguard.l3_calibrate_gate.features import DecisionInput, extract_features


def test_exact_match_scores_full_agreement():
    features = extract_features(
        DecisionInput(
            credit_paise=50_000,
            narration="RZPX*ACMEENTERP123",
            value_date="2026-01-07T00:00:00Z",
            candidate_set_size=1,
            chosen_net_paise=50_000,
            chosen_captured_at="2026-01-05T00:00:00Z",
            raw_confidence=0.97,
        )
    )
    assert features["absolute_amount_gap_paise"] == 0.0
    assert features["partial_rule_agreement_count"] == 3.0
    assert features["model_self_rated_confidence"] == 0.97


def test_no_candidate_maximizes_amount_gap_and_zero_agreement():
    features = extract_features(
        DecisionInput(
            credit_paise=50_000,
            narration="RANDOM TEXT",
            value_date="2026-01-07T00:00:00Z",
            candidate_set_size=0,
            chosen_net_paise=None,
            chosen_captured_at=None,
            raw_confidence=0.0,
        )
    )
    assert features["absolute_amount_gap_paise"] == 50_000.0
    assert features["partial_rule_agreement_count"] == 0.0


def test_date_skew_outside_tolerance_reduces_agreement():
    features = extract_features(
        DecisionInput(
            credit_paise=50_000,
            narration="RZPX*ACMEENTERP123",
            value_date="2026-01-20T00:00:00Z",  # far from captured_at
            candidate_set_size=1,
            chosen_net_paise=50_000,
            chosen_captured_at="2026-01-05T00:00:00Z",
            raw_confidence=0.9,
        )
    )
    assert features["date_skew_days"] > 4
    assert features["partial_rule_agreement_count"] == 2.0  # amount + narration, not date
