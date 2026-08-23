"""D1 task 2 (phases.md Phase 8): replay a candidate rule against train+validation history,
counting hits and false positives. Holdout is never touched here, same discipline L3's
calibrator already follows (plan.md: holdout is never tuned on) -- a rule's promotion bar is a
tuned decision exactly like a calibration threshold is.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ledgerguard.d1_rule_learning.compile import compile_rule
from ledgerguard.l0_normalize.normalize import normalize_bank_line
from ledgerguard.l1_deterministic.matcher import PaymentIndex
from ledgerguard.l1_deterministic.rules import BUILTIN_RULES, LedgerPayment


@dataclass
class ValidationResult:
    hits: int = 0
    false_positives: int = 0
    fired_bank_line_ids: list[str] = field(default_factory=list)


def validate_rule(
    spec: dict,
    bank_lines: list[dict],
    payments: list[LedgerPayment],
    ground_truth: dict[str, dict],
    splits: tuple[str, ...] = ("train", "validation"),
) -> ValidationResult:
    index = PaymentIndex(payments)
    rule = compile_rule(spec, rule_id="candidate")
    result = ValidationResult()

    for row in bank_lines:
        gt = ground_truth.get(row["id"])
        if gt is None or gt["split"] not in splits:
            continue

        bl = normalize_bank_line(row)
        candidates = index.candidates_before(bl.value_date)

        # Built-ins always get first refusal (rules/__init__.py's registry comment) -- a
        # candidate is only ever evaluated on what they didn't already resolve, exactly matching
        # the real firing order it would run under once promoted.
        if any(builtin(bl, candidates) is not None for builtin in BUILTIN_RULES):
            continue

        outcome = rule(bl, candidates)
        if outcome is None or not outcome.resolved:
            continue

        result.fired_bank_line_ids.append(row["id"])
        expected = gt.get("correct_match")
        expected_orders = set(expected["order_ids"]) if expected else set()
        if set(outcome.order_ids) == expected_orders:
            result.hits += 1
        else:
            result.false_positives += 1

    return result
