"""SQLite schema and migration, verbatim per plan.md #15.

`idempotency_key UNIQUE` on match_decisions is the database-level guarantee that a rerun of a
batch cannot double-post -- this is asserted directly in tests/test_db.py and is the foundation
of Phase 6's idempotency test.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    amount_paise INTEGER NOT NULL,
    currency TEXT NOT NULL,
    created_at TEXT NOT NULL,
    source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(id),
    amount_paise INTEGER NOT NULL,
    fee_paise INTEGER NOT NULL,
    tax_paise INTEGER NOT NULL,
    method TEXT NOT NULL,
    status TEXT NOT NULL,
    captured_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS refunds (
    id TEXT PRIMARY KEY,
    payment_id TEXT NOT NULL REFERENCES payments(id),
    amount_paise INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settlements (
    id TEXT PRIMARY KEY,
    utr TEXT,
    amount_paise INTEGER NOT NULL,
    settled_at TEXT NOT NULL,
    is_synthetic INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bank_lines (
    id TEXT PRIMARY KEY,
    utr TEXT,
    credit_paise INTEGER NOT NULL,
    narration TEXT NOT NULL,
    value_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS match_decisions (
    decision_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    bank_line_id TEXT NOT NULL,
    resolver TEXT NOT NULL,
    rule_id TEXT,
    model TEXT,
    prompt_hash TEXT,
    raw_confidence REAL,
    calibrated_confidence REAL,
    threshold REAL,
    action TEXT NOT NULL,
    reason_code TEXT,
    evidence_json TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exceptions (
    id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES match_decisions(decision_id),
    reason_code TEXT NOT NULL,
    status TEXT NOT NULL,
    human_resolution_json TEXT,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS learned_rules (
    rule_id TEXT PRIMARY KEY,
    spec_json TEXT NOT NULL,
    proposed_from TEXT NOT NULL,
    validation_hits INTEGER NOT NULL,
    validation_false_positives INTEGER NOT NULL,
    status TEXT NOT NULL,
    promoted_at TEXT
);

CREATE TABLE IF NOT EXISTS ground_truth (
    bank_line_id TEXT PRIMARY KEY,
    correct_match_json TEXT,
    difficulty TEXT NOT NULL,
    split TEXT NOT NULL
);
"""

TABLE_NAMES = (
    "orders",
    "payments",
    "refunds",
    "settlements",
    "bank_lines",
    "match_decisions",
    "exceptions",
    "learned_rules",
    "ground_truth",
)


def init_db(db_path: str | Path) -> sqlite3.Connection:
    """Create (if needed) and return a connection to the LedgerGuard SQLite database."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn
