"""Compiles a learned rule spec into the same callable shape as L1's built-in rules --
`(NormalizedBankLine, list[LedgerPayment]) -> MatchOutcome | None` -- so it can be appended to
`matcher.run_l1`'s rule chain via its `extra_rules` parameter (phases.md: "promote into the L1
registry"). The spec is *interpreted* here, never executed: no `eval`, no `exec`, no code stored
anywhere -- just three plain fields read as data (phases.md Phase 8's explicit implementation
detail).
"""
from __future__ import annotations

from typing import Callable

from rapidfuzz import fuzz

from ledgerguard.l0_normalize.normalize import NormalizedBankLine, normalize_narration
from ledgerguard.l1_deterministic import tolerance
from ledgerguard.l1_deterministic.rules import LedgerPayment, MatchOutcome, NARRATION_MATCH_THRESHOLD


def compile_rule(
    spec: dict, rule_id: str
) -> Callable[[NormalizedBankLine, list[LedgerPayment]], "MatchOutcome | None"]:
    narration_prefix = spec["narration_prefix"]
    min_days = spec["date_tolerance_days"]["min"]
    max_days = spec["date_tolerance_days"]["max"]

    def _learned_rule(bank_line: NormalizedBankLine, candidates: list[LedgerPayment]) -> MatchOutcome | None:
        # The narration transform: a conservative scope, not the reason a match is correct here
        # -- it limits this rule to bank lines from the same counterparty the resolved exception
        # came from, so a widened date tolerance never leaks into unrelated narrations.
        if fuzz.partial_ratio(normalize_narration(bank_line.narration), narration_prefix) < NARRATION_MATCH_THRESHOLD:
            return None

        matches = [
            p
            for p in candidates
            if p.net_paise == bank_line.credit_paise
            and tolerance.within_date_tolerance(p.captured_at, bank_line.value_date, min_days=min_days, max_days=max_days)
        ]
        if len(matches) != 1:
            return None  # only a clean single answer -- any tie stays escalated, same as the built-ins

        p = matches[0]
        return MatchOutcome(
            resolved=True,
            order_ids=[p.order_id],
            payment_ids=[p.payment_id],
            rule_id=rule_id,
            # Below the built-ins' hand-verified 0.97/0.93: this rule earned its place by
            # replaying cleanly against history, not by hand-verified design, so it gets a shade
            # less raw trust -- L3 still decides whether that clears the AUTO_POST bar.
            confidence=0.90,
            evidence=[
                f"learned rule {rule_id}: narration matches {narration_prefix!r}, payment "
                f"{p.payment_id} net amount matches within widened tolerance "
                f"[{min_days},{max_days}] days"
            ],
        )

    return _learned_rule
