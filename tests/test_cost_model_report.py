from pathlib import Path

from eval.cost_model import build_holdout_exception_queue
from ledgerguard.l3_calibrate_gate.calibrator import Calibrator
from ledgerguard.l3_calibrate_gate.decisions import build_decision_dataset

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"


def test_holdout_exception_queue_is_ranked_and_carries_evidence():
    decisions = build_decision_dataset(SAMPLES_DIR)
    validation = [d for d in decisions if d.split == "validation"]
    holdout = [d for d in decisions if d.split == "holdout"]

    calibrator = Calibrator()
    calibrator.fit([d.features for d in validation], [d.correct for d in validation])
    holdout_calibrated = calibrator.predict_proba([d.features for d in holdout])

    queue = build_holdout_exception_queue(holdout, holdout_calibrated, threshold=0.92)

    assert len(queue) > 0
    amounts = [e.amount_paise for e in queue]
    assert amounts == sorted(amounts, reverse=True)
    for entry in queue:
        assert entry.reason_code
        assert isinstance(entry.evidence, list)
