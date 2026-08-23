"""D1 task 1 (phases.md Phase 8): from one human-resolved exception, propose a candidate rule
spec -- a narration transform, a match key, and a date tolerance. This is data (a JSON-shaped
dict), never generated code: no `eval`, no `exec` anywhere in this package.

**Why a widened date tolerance is the thing worth learning here.** L1's built-in
`rule_single_payment_net_match` already requires no narration at all -- it resolves purely on
exact net-amount + a fixed [2,4]-day settlement window (`l1_deterministic/tolerance.py`).
Everything in this project's residual set that escalates *and* has one clean, single-order
correct answer turns out to escalate for exactly one reason: the real settlement landed outside
that fixed window (a specific counterparty settling a few days later than the general default --
a realistic reconciliation pattern, not an artifact of synthetic data). A learned rule therefore
only ever *widens* the built-in window, and only within a narration-scoped safety boundary (the
same counterparty the resolved example came from) -- it can never override or narrow what the
built-ins already do, since matcher.py always tries the built-ins first.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from rapidfuzz import fuzz

from ledgerguard.l0_normalize.normalize import normalize_narration
from ledgerguard.l1_deterministic.rules import KNOWN_MERCHANT_TOKENS
from ledgerguard.l1_deterministic.tolerance import MAX_SETTLEMENT_DAYS, MIN_SETTLEMENT_DAYS


@dataclass
class ResolvedException:
    """A human's answer to one escalated bank line. This environment has never had a live
    operator (or the Anthropic credentials that would make a real L2 call in the first place --
    see PROGRESS.md/BROKE.md Phases 0/4), so eval/rule_learning.py simulates "a human resolved
    this" using ground truth's own known-correct answer -- the same substitution already used to
    stand in for a live L2 call in `l3_calibrate_gate/decisions.py`.
    """

    bank_line_id: str
    narration: str
    credit_paise: int
    value_date: datetime
    chosen_payment_id: str
    chosen_order_id: str
    chosen_captured_at: datetime


def best_matching_merchant_token(narration: str, known_tokens: tuple[str, ...] = KNOWN_MERCHANT_TOKENS) -> str:
    normalized = normalize_narration(narration)
    return max(known_tokens, key=lambda token: fuzz.partial_ratio(normalized, token))


def propose_rule(resolved: ResolvedException) -> dict:
    observed_days = (resolved.value_date - resolved.chosen_captured_at).total_seconds() / 86400
    return {
        "narration_prefix": best_matching_merchant_token(resolved.narration),
        "match_key": "single_net_amount_exact",
        "date_tolerance_days": {
            "min": min(MIN_SETTLEMENT_DAYS, math.floor(observed_days)),
            "max": max(MAX_SETTLEMENT_DAYS, math.ceil(observed_days)),
        },
    }
