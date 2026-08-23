"""The idempotency test that carries this project's thesis (plan.md #18): rerunning the full
batch must be byte-identical and must never double-post. See ledgerguard/close.py's module
docstring for how the design guarantees this (deterministic idempotency keys + insert-then-audit
ordering, no wall clock anywhere).
"""
import sqlite3
from pathlib import Path

from ledgerguard.close import run_close

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"


def test_rerunning_the_full_batch_is_byte_identical_and_double_post_free(tmp_path):
    db_path = tmp_path / "ledgerguard.db"
    audit_path = tmp_path / "audit.jsonl"

    first_counts = run_close("batch-1", SAMPLES_DIR, db_path, audit_path)
    first_audit_bytes = audit_path.read_bytes()

    conn = sqlite3.connect(db_path)
    first_row_count = conn.execute("SELECT COUNT(*) FROM match_decisions").fetchone()[0]
    conn.close()

    second_counts = run_close("batch-1", SAMPLES_DIR, db_path, audit_path)
    second_audit_bytes = audit_path.read_bytes()

    conn = sqlite3.connect(db_path)
    second_row_count = conn.execute("SELECT COUNT(*) FROM match_decisions").fetchone()[0]
    distinct_idempotency_keys = conn.execute(
        "SELECT COUNT(DISTINCT idempotency_key) FROM match_decisions"
    ).fetchone()[0]
    conn.close()

    assert first_audit_bytes == second_audit_bytes
    assert first_row_count == second_row_count  # zero new rows on rerun
    assert distinct_idempotency_keys == first_row_count  # zero duplicate ledger rows, ever
    assert first_counts["posted_new"] == first_row_count
    assert second_counts["posted_new"] == 0
    assert second_counts["already_posted"] == first_row_count


def test_audit_line_count_equals_total_decision_count(tmp_path):
    db_path = tmp_path / "ledgerguard.db"
    audit_path = tmp_path / "audit.jsonl"

    run_close("batch-1", SAMPLES_DIR, db_path, audit_path)

    conn = sqlite3.connect(db_path)
    decision_count = conn.execute("SELECT COUNT(*) FROM match_decisions").fetchone()[0]
    conn.close()

    audit_line_count = sum(1 for _ in open(audit_path, encoding="utf-8"))
    assert audit_line_count == decision_count


def test_different_batch_ids_do_not_collide():
    from ledgerguard.l5_executor.idempotency import derive_idempotency_key

    key_a = derive_idempotency_key("batch-1", "bl_1")
    key_b = derive_idempotency_key("batch-2", "bl_1")
    assert key_a != key_b


def test_idempotency_key_is_stable_across_calls():
    from ledgerguard.l5_executor.idempotency import derive_idempotency_key

    assert derive_idempotency_key("batch-1", "bl_1") == derive_idempotency_key("batch-1", "bl_1")
