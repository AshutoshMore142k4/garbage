"""The committed snapshot is what a judge sees while the backend is waking up. If it drifts from
what the pipeline actually produces, the UI shows stale numbers with no indication anything is
wrong -- exactly the "manufactured number" failure this project's integrity rules exist to
prevent. So drift is a test failure, not a stale-file inconvenience.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = REPO_ROOT / "frontend" / "public" / "snapshot.json"


@pytest.fixture(scope="module")
def snapshot() -> dict:
    if not SNAPSHOT_PATH.exists():
        pytest.fail("frontend/public/snapshot.json is missing — regenerate it with `make snapshot`")
    return json.loads(SNAPSHOT_PATH.read_text())


def test_snapshot_dashboard_matches_a_live_pipeline_run(snapshot, monkeypatch):
    """The whole point: committed snapshot == what the pipeline computes right now."""
    monkeypatch.setenv("LEDGERGUARD_DATA_DIR", str(REPO_ROOT / "data" / "samples"))
    from ledgerguard.api.service import PipelineState

    live = json.loads(PipelineState().dashboard().model_dump_json())

    # `dataset` is a display string that differs between an absolute path (what this test sets)
    # and the relative one the generator runs with. Everything else is substantive and must match
    # exactly -- those are the numbers a judge reads off the screen.
    assert {k: v for k, v in snapshot["dashboard"].items() if k != "dataset"} == {
        k: v for k, v in live.items() if k != "dataset"
    }, "snapshot has drifted — regenerate with `make snapshot`"


def test_snapshot_carries_every_decision_so_the_offline_ui_can_drill_into_any_row(snapshot):
    total = snapshot["dashboard"]["total_bank_lines"]
    assert len(snapshot["investigations"]) == total
    assert snapshot["queue"]["total"] == total


def test_snapshot_names_the_demo_pair_and_refuses_both(snapshot):
    demo_pair = snapshot["dashboard"]["demo_pair"]
    assert len(demo_pair) == 2
    reasons = set()
    for bank_line_id in demo_pair:
        inv = snapshot["investigations"][bank_line_id]
        assert inv["action"] == "FLAG_ANOMALY"
        reasons.add(inv["reason_code"])
    assert reasons == {"DUPLICATE_UTR", "GENUINE_DOUBLE_SETTLEMENT"}


def test_snapshot_evaluation_reports_the_preregistered_band_verbatim(snapshot):
    """The UI must not be able to show a friendlier verdict than the pre-registered rule allows."""
    e = snapshot["evaluation"]
    assert e["band"] in {"HEADLINE", "MODEST", "NEGATIVE"}
    if e["delta_hard_adversarial"] < 0.03:
        assert e["band"] == "NEGATIVE"
        assert "negative result" in e["verdict"]
    assert len(e["ablation"]) == 5  # 4 strata + Overall
    assert len(e["rule_learning"]) == 3


def test_snapshot_provenance_never_claims_a_live_connection(snapshot):
    text = json.dumps(snapshot)
    assert "no live Razorpay connection" in text
    assert "Razorpay Test Mode Connected" not in text
