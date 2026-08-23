"""Writes decisions into `match_decisions` (plan.md #15, phases.md Phase 6 task 4).

Insertion is idempotent: the `idempotency_key UNIQUE` constraint (db.py) turns a duplicate
insert into a no-op rather than a duplicate row, which is what makes rerunning a batch safe
(phases.md Phase 6's core safety property, exercised end-to-end by tests/test_idempotency.py).
"""
from __future__ import annotations

import json
import sqlite3

from ledgerguard.models import MatchDecision


def post_decision(conn: sqlite3.Connection, decision: MatchDecision) -> bool:
    """Returns True if a new row was inserted, False if the idempotency key already existed."""
    try:
        conn.execute(
            "INSERT INTO match_decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                decision.decision_id,
                decision.batch_id,
                decision.bank_line_id,
                decision.resolver,
                decision.rule_id,
                decision.model,
                decision.prompt_hash,
                decision.raw_confidence,
                decision.calibrated_confidence,
                decision.threshold,
                decision.action,
                decision.reason_code,
                json.dumps(decision.evidence, sort_keys=True),
                decision.idempotency_key,
                decision.created_at,
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        conn.rollback()
        return False
