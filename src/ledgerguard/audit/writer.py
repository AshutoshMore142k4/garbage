"""Append-only JSONL audit writer.

One line per reconciliation decision, per plan.md #19 ("every automated decision must be
answerable after the fact"). The line shape is `MatchDecision` (models.py) -- the same schema
as the match_decisions table row -- so an audit line and a posted decision are always the same
fact represented two ways.

Note: plan.md/phases.md say the audit-line schema is pinned in `CLAUDE.md`. That file was never
supplied to this repo (see PROGRESS.md / BROKE.md, Phase 0). In its absence this module treats
`MatchDecision` itself as the schema, since it already carries every field plan.md #15/#19
require (resolver, rule/model, confidence, threshold, action, reason code, evidence,
idempotency key). If `CLAUDE.md` is authored later with a different schema, reconcile here.
"""
from __future__ import annotations

from pathlib import Path

from ledgerguard.models import MatchDecision


class AuditWriter:
    """Opens the audit log in append mode only; never rewrites or truncates existing content."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, decision: MatchDecision) -> None:
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(decision.model_dump_json() + "\n")
