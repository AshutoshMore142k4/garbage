from pathlib import Path

from ledgerguard.l3_calibrate_gate.decisions import build_decision_dataset
from ledgerguard.l3_calibrate_gate.features import FEATURE_NAMES

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"


def test_build_decision_dataset_covers_every_bank_line():
    import csv

    with open(SAMPLES_DIR / "bank_statement.csv", newline="", encoding="utf-8") as f:
        bank_line_ids = {row["id"] for row in csv.DictReader(f)}

    decisions = build_decision_dataset(SAMPLES_DIR)

    assert {d.bank_line_id for d in decisions} == bank_line_ids


def test_every_decision_has_a_complete_feature_vector_and_a_split():
    decisions = build_decision_dataset(SAMPLES_DIR)
    for d in decisions:
        assert set(d.features.keys()) == set(FEATURE_NAMES)
        assert d.split in ("train", "validation", "holdout")


def test_l1_resolved_decisions_have_no_reason_code():
    decisions = build_decision_dataset(SAMPLES_DIR)
    for d in decisions:
        if d.resolver == "L1_RULE":
            assert d.reason_code is None
