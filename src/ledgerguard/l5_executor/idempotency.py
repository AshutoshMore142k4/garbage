"""Idempotency key derivation (plan.md #12/#15, phases.md Phase 6 task 3).

Derived purely from stable source IDs -- `batch_id` and `bank_line_id` -- so it is identical
across reruns regardless of wall-clock time. The `match_decisions.idempotency_key UNIQUE`
constraint (db.py, Phase 1) is the database-level guarantee that a rerun can never double-post
the same decision; this function is what makes that guarantee actually line up run over run.
"""
from __future__ import annotations

import hashlib


def derive_idempotency_key(batch_id: str, bank_line_id: str) -> str:
    raw = f"{batch_id}:{bank_line_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
