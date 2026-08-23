from ledgerguard.l5_executor.authority import (
    AUTO_POST,
    ESCALATE,
    FLAG_ANOMALY,
    AuthorityInput,
    authorize,
)

AUTHORITY_LIMIT_PAISE = 10_000_000  # matches .env.example


def test_authorizes_auto_post_when_all_conditions_hold():
    action = authorize(
        AuthorityInput(gate_action=AUTO_POST, amount_paise=500_000, authority_limit_paise=AUTHORITY_LIMIT_PAISE, has_anomaly=False)
    )
    assert action == AUTO_POST


def test_over_authority_limit_never_auto_posts_even_with_gate_approval():
    action = authorize(
        AuthorityInput(
            gate_action=AUTO_POST,
            amount_paise=AUTHORITY_LIMIT_PAISE + 1,
            authority_limit_paise=AUTHORITY_LIMIT_PAISE,
            has_anomaly=False,
        )
    )
    assert action == ESCALATE


def test_over_authority_limit_never_auto_posts_even_at_near_certain_confidence():
    # The gate itself would have said AUTO_POST at confidence 0.99 -- authority still refuses.
    for amount in (AUTHORITY_LIMIT_PAISE + 1, AUTHORITY_LIMIT_PAISE * 10):
        action = authorize(
            AuthorityInput(gate_action=AUTO_POST, amount_paise=amount, authority_limit_paise=AUTHORITY_LIMIT_PAISE, has_anomaly=False)
        )
        assert action == ESCALATE, amount


def test_amount_exactly_at_limit_is_allowed():
    action = authorize(
        AuthorityInput(
            gate_action=AUTO_POST, amount_paise=AUTHORITY_LIMIT_PAISE, authority_limit_paise=AUTHORITY_LIMIT_PAISE, has_anomaly=False
        )
    )
    assert action == AUTO_POST


def test_gate_escalation_is_never_overridden_to_auto_post():
    action = authorize(
        AuthorityInput(gate_action=ESCALATE, amount_paise=1_000, authority_limit_paise=AUTHORITY_LIMIT_PAISE, has_anomaly=False)
    )
    assert action == ESCALATE


def test_anomaly_forces_flag_anomaly_regardless_of_gate_and_amount():
    action = authorize(
        AuthorityInput(gate_action=AUTO_POST, amount_paise=1_000, authority_limit_paise=AUTHORITY_LIMIT_PAISE, has_anomaly=True)
    )
    assert action == FLAG_ANOMALY
