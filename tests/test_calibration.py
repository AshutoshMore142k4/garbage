import random
from pathlib import Path

import pytest

from eval.calibration import compute_ece, fit_and_evaluate
from ledgerguard.l3_calibrate_gate.calibrator import Calibrator
from ledgerguard.l3_calibrate_gate.decisions import build_decision_dataset
from ledgerguard.l3_calibrate_gate.features import FEATURE_NAMES

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"


def _feature_dict(**overrides):
    base = {name: 0.0 for name in FEATURE_NAMES}
    base.update(overrides)
    return base


def test_compute_ece_is_zero_for_perfect_calibration():
    confidences = [0.0, 0.0, 1.0, 1.0]
    labels = [False, False, True, True]
    assert compute_ece(confidences, labels) == pytest.approx(0.0, abs=1e-9)


def test_compute_ece_detects_gross_miscalibration():
    confidences = [0.95] * 10
    labels = [False] * 9 + [True]  # says 95% confident, right only 10% of the time
    ece = compute_ece(confidences, labels)
    assert ece > 0.5


def test_calibrator_requires_both_classes_to_fit():
    calibrator = Calibrator()
    with pytest.raises(ValueError):
        calibrator.fit([_feature_dict()], [True])


def test_calibrator_predict_before_fit_raises():
    calibrator = Calibrator()
    with pytest.raises(RuntimeError):
        calibrator.predict_proba([_feature_dict()])


def test_calibrator_learns_a_separating_feature():
    rng = random.Random(0)
    features, labels = [], []
    for _ in range(200):
        agreement = rng.choice([0, 1, 2, 3])
        correct = agreement >= 2  # deterministic-ish rule the calibrator should recover
        features.append(_feature_dict(partial_rule_agreement_count=float(agreement), model_self_rated_confidence=0.5))
        labels.append(correct)

    calibrator = Calibrator()
    calibrator.fit(features, labels)

    low_agreement = calibrator.predict_proba([_feature_dict(partial_rule_agreement_count=0.0)])[0]
    high_agreement = calibrator.predict_proba([_feature_dict(partial_rule_agreement_count=3.0)])[0]
    assert high_agreement > low_agreement


def test_calibrator_improves_ece_over_raw_confidence_on_the_committed_sample_dataset():
    decisions = build_decision_dataset(SAMPLES_DIR)
    result = fit_and_evaluate(decisions)

    assert len(result["validation"]) > 0
    assert len(result["holdout"]) > 0
    assert result["ece_calibrated"] <= result["ece_raw"]
