"""D1 task 3 (phases.md Phase 8): promote a validated candidate into the L1 registry, or reject
it. Promotion bar: `hits >= MIN_HITS` and `false_positives == 0`, always -- the zero-false-
positive requirement is never loosened (phases.md's own explicit failure-mode guidance), even if
`MIN_HITS` itself needs lowering from 3 to 2 to find anything to promote at all.

Persists to the `learned_rules` table `db.py` already provisions (Phase 1) -- `rule_id` is a
deterministic hash of the spec, so re-proposing the identical spec twice is a no-op (`INSERT OR
REPLACE`), the same idempotent-by-construction pattern `l5_executor/idempotency.py` uses for
`match_decisions`.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

from ledgerguard.d1_rule_learning.validate import ValidationResult
from ledgerguard.models import LearnedRule

MIN_HITS = 3


def spec_id(spec: dict) -> str:
    digest = hashlib.sha256(json.dumps(spec, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"learned_{digest}"


def decide_status(result: ValidationResult, min_hits: int = MIN_HITS) -> str:
    if result.false_positives == 0 and result.hits >= min_hits:
        return "PROMOTED"
    return "REJECTED"


def promote_rule(
    spec: dict,
    proposed_from: str,
    result: ValidationResult,
    promoted_at: str,
    min_hits: int = MIN_HITS,
) -> LearnedRule:
    status = decide_status(result, min_hits)
    return LearnedRule(
        rule_id=spec_id(spec),
        spec=spec,
        proposed_from=proposed_from,
        validation_hits=result.hits,
        validation_false_positives=result.false_positives,
        status=status,
        promoted_at=promoted_at if status == "PROMOTED" else None,
    )


def save_learned_rule(conn: sqlite3.Connection, rule: LearnedRule) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO learned_rules "
        "(rule_id, spec_json, proposed_from, validation_hits, validation_false_positives, status, promoted_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            rule.rule_id,
            json.dumps(rule.spec, sort_keys=True),
            rule.proposed_from,
            rule.validation_hits,
            rule.validation_false_positives,
            rule.status,
            rule.promoted_at,
        ),
    )
    conn.commit()


def load_learned_rules(conn: sqlite3.Connection, status: str | None = None) -> list[LearnedRule]:
    query = (
        "SELECT rule_id, spec_json, proposed_from, validation_hits, validation_false_positives, "
        "status, promoted_at FROM learned_rules"
    )
    params: tuple = ()
    if status is not None:
        query += " WHERE status = ?"
        params = (status,)
    rows = conn.execute(query, params).fetchall()
    return [
        LearnedRule(
            rule_id=r[0],
            spec=json.loads(r[1]),
            proposed_from=r[2],
            validation_hits=r[3],
            validation_false_positives=r[4],
            status=r[5],
            promoted_at=r[6],
        )
        for r in rows
    ]
