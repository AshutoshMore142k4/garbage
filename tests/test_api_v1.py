"""The /api/v1 surface the deployed UI runs against.

The load-bearing assertions here are the safety ones: the twin case must never be executable, and
executing twice must post once. Those are the two claims the demo makes on screen, so they are
pinned in the suite rather than left to a manual click-through.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ledgerguard.api import service
from ledgerguard.api.app import app

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = REPO_ROOT / "data" / "samples"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Points every write at a temp dir and rebuilds the cached pipeline, so tests never touch
    the repo and never inherit another test's posted ledger.
    """
    monkeypatch.setenv("LEDGERGUARD_DATA_DIR", str(SAMPLES_DIR))
    monkeypatch.setenv("LEDGERGUARD_DB_PATH", str(tmp_path / "ledgerguard.db"))
    monkeypatch.setenv("LEDGERGUARD_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    service.get_state.cache_clear()
    yield TestClient(app)
    service.get_state.cache_clear()


@pytest.fixture()
def demo_pair() -> list[str]:
    manifest = json.loads((SAMPLES_DIR / "chaos_manifest.json").read_text())
    return list(manifest["demo_pair"].values())


def test_healthz_does_no_pipeline_work_and_answers(client):
    body = client.get("/healthz").json()
    assert body["ok"] is True


def test_dashboard_matches_the_pipeline_make_close_reports(client):
    d = client.get("/api/v1/dashboard").json()
    # Identical to `python -m ledgerguard.close` on data/samples -- the API must not be a
    # differently-tuned copy of the system.
    assert d["total_bank_lines"] == 300
    assert d["counts_by_action"] == {"AUTO_POST": 198, "ESCALATE": 77, "FLAG_ANOMALY": 25}
    assert d["refused"] == 102
    assert d["threshold"] == pytest.approx(0.98)
    assert d["false_auto_match_rate"] == 0.0


def test_every_response_carries_honest_provenance(client, demo_pair):
    """No surface may imply a live payment connection: this project has never had credentials."""
    for path in ["/api/v1/dashboard", "/api/v1/reconciliation", f"/api/v1/reconciliation/{demo_pair[0]}"]:
        body = client.get(path).json()
        assert "Synthetic" in body["data_provenance"]
        assert "no live Razorpay connection" in body["data_provenance"]


def test_queue_ranks_refused_first_then_by_rupees_at_risk(client):
    items = client.get("/api/v1/reconciliation").json()["items"]
    actions = [i["action"] for i in items]

    # Every refused decision precedes every auto-posted one.
    first_auto = actions.index("AUTO_POST")
    last_refused = max(i for i, a in enumerate(actions) if a != "AUTO_POST")
    assert last_refused < first_auto

    # ...and within each group, largest rupees at risk first.
    refused = [i["credit_paise"] for i in items[:first_auto]]
    posted = [i["credit_paise"] for i in items[first_auto:]]
    assert refused == sorted(refused, reverse=True)
    assert posted == sorted(posted, reverse=True)


def test_queue_filters(client):
    flagged = client.get("/api/v1/reconciliation", params={"action": "FLAG_ANOMALY"}).json()
    assert flagged["total"] == 25
    assert all(i["action"] == "FLAG_ANOMALY" for i in flagged["items"])

    adversarial = client.get("/api/v1/reconciliation", params={"difficulty": "ADVERSARIAL"}).json()
    assert all(i["difficulty"] == "ADVERSARIAL" for i in adversarial["items"])


def test_unknown_bank_line_is_404_not_a_500(client):
    assert client.get("/api/v1/reconciliation/nope").status_code == 404
    assert client.post("/api/v1/reconciliation/nope/execute").status_code == 404


def test_twin_case_is_flagged_with_distinct_reason_codes(client, demo_pair):
    reasons = []
    for bank_line_id in demo_pair:
        body = client.get(f"/api/v1/reconciliation/{bank_line_id}").json()
        assert body["action"] == "FLAG_ANOMALY"
        reasons.append(body["reason_code"])
        # The demo's whole point: the gate cleared it, and L4 overrode the gate.
        assert body["calibrated_confidence"] >= body["threshold"]
        confidence_clause = next(c for c in body["policy"] if c["label"] == "Calibrated confidence")
        anomaly_clause = next(c for c in body["policy"] if c["label"] == "No anomaly flag")
        assert confidence_clause["passed"] is True
        assert anomaly_clause["passed"] is False
    assert set(reasons) == {"DUPLICATE_UTR", "GENUINE_DOUBLE_SETTLEMENT"}


def test_twin_case_can_never_be_executed(client, demo_pair):
    """The single most important assertion in this file. If this ever passes an execution, the
    system posted money against a duplicate report or a double settlement.
    """
    for bank_line_id in demo_pair:
        r = client.post(f"/api/v1/reconciliation/{bank_line_id}/execute").json()
        assert r["authorized"] is False
        assert r["idempotency_key"] is None
        assert "BLOCKED" in r["message"]


def test_executing_twice_posts_once(client):
    auto = client.get("/api/v1/reconciliation", params={"action": "AUTO_POST"}).json()["items"][0]
    bank_line_id = auto["bank_line_id"]

    first = client.post(f"/api/v1/reconciliation/{bank_line_id}/execute").json()
    second = client.post(f"/api/v1/reconciliation/{bank_line_id}/execute").json()

    assert first["authorized"] and second["authorized"]
    assert first["newly_posted"] is True
    assert second["newly_posted"] is False  # the idempotency guarantee, over HTTP
    assert first["idempotency_key"] == second["idempotency_key"]

    audit = client.get("/api/v1/audit").json()
    assert len([e for e in audit["events"] if e["bank_line_id"] == bank_line_id]) == 1


def test_escalated_decisions_are_refused_with_the_failing_clause_named(client):
    escalated = client.get("/api/v1/reconciliation", params={"action": "ESCALATE"}).json()["items"][0]
    r = client.post(f"/api/v1/reconciliation/{escalated['bank_line_id']}/execute").json()
    assert r["authorized"] is False
    assert any(not c["passed"] for c in r["policy"])


def test_investigation_signals_are_structured_not_free_text(client, demo_pair):
    """Decision factors must be a typed list a UI can render as pass/warn/fail -- never a prose
    blob, and never model chain-of-thought.
    """
    body = client.get(f"/api/v1/reconciliation/{demo_pair[0]}").json()
    assert len(body["signals"]) >= 4
    for s in body["signals"]:
        assert s["status"] in {"pass", "warn", "fail"}
        assert s["label"] and s["value"]
    assert any(s["status"] == "fail" for s in body["signals"])  # the anomaly


def test_api_request_path_never_imports_matplotlib():
    """matplotlib is ~36 MB and belongs to the eval/report tooling, not to serving requests.
    Pinned because an accidental import would be invisible locally and expensive in deployment.
    """
    import sys

    for module in list(sys.modules):
        if module.startswith("matplotlib"):
            del sys.modules[module]

    import importlib

    importlib.import_module("ledgerguard.api.app")
    assert not any(m.startswith("matplotlib") for m in sys.modules)
