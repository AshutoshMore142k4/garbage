"""An anomaly flag must override a high-confidence match (phases.md Phase 6) -- exercised here
both as a direct authority-policy check and end to end against the real committed sample
dataset's duplicate-UTR / genuine-double-settlement demo pair (plan.md #8 J4).
"""
import json
import sqlite3
from pathlib import Path

from ledgerguard.close import run_close
from ledgerguard.l5_executor.authority import FLAG_ANOMALY, AuthorityInput, authorize

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"


def test_anomaly_flag_overrides_a_high_confidence_auto_post():
    action = authorize(
        AuthorityInput(gate_action="AUTO_POST", amount_paise=1_000, authority_limit_paise=10_000_000, has_anomaly=True)
    )
    assert action == FLAG_ANOMALY


def test_demo_pair_both_refused_with_distinct_reason_codes(tmp_path):
    manifest = json.loads((SAMPLES_DIR / "chaos_manifest.json").read_text())
    demo_pair = manifest["demo_pair"]

    db_path = tmp_path / "ledgerguard.db"
    audit_path = tmp_path / "audit.jsonl"
    run_close("test-batch", SAMPLES_DIR, db_path, audit_path)

    conn = sqlite3.connect(db_path)
    rows = {}
    for bank_line_id in demo_pair.values():
        rows[bank_line_id] = conn.execute(
            "SELECT action, reason_code FROM match_decisions WHERE bank_line_id = ?", (bank_line_id,)
        ).fetchone()
    conn.close()

    dup_action, dup_reason = rows[demo_pair["duplicate_utr_bank_line_id"]]
    dbl_action, dbl_reason = rows[demo_pair["genuine_double_settlement_bank_line_id"]]

    assert dup_action != "AUTO_POST"
    assert dbl_action != "AUTO_POST"
    assert dup_reason == "DUPLICATE_UTR"
    assert dbl_reason == "GENUINE_DOUBLE_SETTLEMENT"
    assert dup_reason != dbl_reason
