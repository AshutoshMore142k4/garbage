import itertools

from ledgerguard.l3_calibrate_gate.gate import AUTO_POST, ESCALATE, GateInput, gate
from ledgerguard.models import ReasonCode

REASON_CODES = set(ReasonCode.__args__)


def test_gate_auto_posts_at_or_above_threshold_with_a_candidate():
    outcome = gate(GateInput(has_candidate=True, calibrated_confidence=0.95, existing_reason_code=None), threshold=0.9)
    assert outcome.action == AUTO_POST
    assert outcome.reason_code is None


def test_gate_never_auto_posts_below_threshold():
    for confidence in (0.0, 0.1, 0.5, 0.89, 0.8999):
        outcome = gate(
            GateInput(has_candidate=True, calibrated_confidence=confidence, existing_reason_code=None),
            threshold=0.9,
        )
        assert outcome.action == ESCALATE, confidence


def test_gate_never_auto_posts_without_a_candidate_even_at_high_confidence():
    outcome = gate(
        GateInput(has_candidate=False, calibrated_confidence=0.99, existing_reason_code="NO_CANDIDATE_FOUND"),
        threshold=0.5,
    )
    assert outcome.action == ESCALATE


def test_gate_preserves_existing_reason_code_when_no_candidate_was_found():
    outcome = gate(
        GateInput(has_candidate=False, calibrated_confidence=0.0, existing_reason_code="NO_CANDIDATE_FOUND"),
        threshold=0.9,
    )
    assert outcome.action == ESCALATE
    assert outcome.reason_code == "NO_CANDIDATE_FOUND"


def test_gate_assigns_ambiguous_reason_code_when_candidate_exists_but_under_threshold():
    outcome = gate(
        GateInput(has_candidate=True, calibrated_confidence=0.62, existing_reason_code=None),
        threshold=0.94,
    )
    assert outcome.action == ESCALATE
    assert outcome.reason_code == "AMBIGUOUS_NARRATION_MULTI_CANDIDATE"


def test_every_escalated_outcome_carries_a_reason_code_from_the_closed_enum():
    has_candidate_options = (True, False)
    confidences = (0.0, 0.3, 0.5, 0.7, 0.94, 0.99, 1.0)
    existing_reason_codes = (None, "NO_CANDIDATE_FOUND", "SUBSET_SUM_OVER_BUDGET", "AMOUNT_GAP_EXCEEDS_TOLERANCE")
    threshold = 0.9

    for has_candidate, confidence, reason_code in itertools.product(
        has_candidate_options, confidences, existing_reason_codes
    ):
        outcome = gate(
            GateInput(has_candidate=has_candidate, calibrated_confidence=confidence, existing_reason_code=reason_code),
            threshold=threshold,
        )
        if outcome.action == ESCALATE:
            assert outcome.reason_code is not None
            assert outcome.reason_code in REASON_CODES
