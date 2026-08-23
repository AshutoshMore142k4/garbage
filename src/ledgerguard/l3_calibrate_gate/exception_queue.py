"""The ranked exception queue (plan.md #9/#19, phases.md Phase 5 task 5): every escalated
decision, ranked by rupees at risk, each carrying its reason code and evidence so an operator
can triage the highest-value cases first.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExceptionQueueEntry:
    bank_line_id: str
    amount_paise: int
    reason_code: str
    calibrated_confidence: float
    evidence: list[str]


def build_exception_queue(entries: list[ExceptionQueueEntry]) -> list[ExceptionQueueEntry]:
    return sorted(entries, key=lambda e: e.amount_paise, reverse=True)
