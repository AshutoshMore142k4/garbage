"""L1 deterministic rule registry (plan.md #9/#15, phases.md Phase 3).

Each rule is a plain, ordered function: given a normalized bank line and its candidate ledger
payments, it either declines (returns None, "try the next rule") or returns a terminal
`MatchOutcome` -- resolved with a rule_id and confidence, or an explicit escalation with a
reason code. The registry is deliberately just an ordered list of functions rather than a class
hierarchy or framework, so D1 (Phase 8) has a simple, auditable place to register learned rules
later without needing to touch these built-ins.

No rule here calls a model or the network -- everything is arithmetic, dict/set lookups, and
rapidfuzz string scoring (see tests/test_l1_no_network.py).

On "exact UTR", one of the four rules plan.md #9 names for L1: an earlier draft of this module
implemented it as bank-line-vs-bank-line duplicate detection (same UTR seen twice => the later
one is a reporting artifact). That turned out to be both buggy (it picked "the original" by
sorting bank-line IDs lexicographically, which reflects nothing real and can pick the wrong one
-- see BROKE.md) and architecturally misplaced: phases.md Phase 6 explicitly assigns duplicate-UTR
detection to L4 anomaly detection ("L4 has veto power over L1"), not to L1. The genuine positive
use of "exact UTR" -- matching a bank line straight to a previously-known UTR-to-order-group
mapping -- has no data to run on yet either: the internal ledger carries no UTR field (real
Razorpay payments don't carry one; only settlements do), and no such registry exists before D1's
learned-rule promotion (Phase 8). So this rule is deliberately not implemented at L1 in this
phase; both gaps are recorded in PROGRESS.md/BROKE.md rather than papered over with a rule that
either has no data or duplicates Phase 6's job.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from rapidfuzz import fuzz

from ledgerguard.l0_normalize.normalize import NormalizedBankLine
from ledgerguard.l1_deterministic import tolerance
from ledgerguard.l1_deterministic.subset_sum import find_subset

# A merchant's own known bank-narration aliases. Realistic and small: payment aggregators
# mangle/prefix the registered business name, so a merchant maintains a short list of what its
# credits are known to look like. Used as a plausibility signal, not a disambiguator (the ledger
# itself carries no per-order narration to fuzzy-match against -- see PROGRESS.md Phase 3 note).
KNOWN_MERCHANT_TOKENS = ("ACMEENTERP", "GLOBALTRADE", "SUNRISEMART", "APEXRETAIL", "NORTHSTARCO")
NARRATION_MATCH_THRESHOLD = 70.0


@dataclass
class LedgerPayment:
    payment_id: str
    order_id: str
    net_paise: int
    captured_at: datetime


@dataclass
class MatchOutcome:
    resolved: bool
    order_ids: list[str] = field(default_factory=list)
    payment_ids: list[str] = field(default_factory=list)
    rule_id: str | None = None
    confidence: float | None = None
    reason_code: str | None = None
    evidence: list[str] = field(default_factory=list)
    # Populated only when unresolved: the bounded set of candidate payment_ids L1 actually
    # considered, so L2 (Phase 4) can be handed exactly this set and never the full ledger.
    candidate_payment_ids: list[str] = field(default_factory=list)


def narration_similarity_score(narration: str, known_tokens: tuple[str, ...] = KNOWN_MERCHANT_TOKENS) -> float:
    """rapidfuzz partial-ratio of `narration` against the best-matching known merchant token."""
    if not narration:
        return 0.0
    return max(fuzz.partial_ratio(narration, token) for token in known_tokens)


def _closest(payments: list[LedgerPayment], value_date: datetime) -> list[LedgerPayment]:
    return sorted(payments, key=lambda p: abs((value_date - p.captured_at).total_seconds()))


def rule_single_payment_net_match(
    bank_line: NormalizedBankLine, candidates: list[LedgerPayment]
) -> MatchOutcome | None:
    matches = [
        p
        for p in candidates
        if p.net_paise == bank_line.credit_paise
        and tolerance.within_date_tolerance(p.captured_at, bank_line.value_date)
    ]
    if not matches:
        return None
    if len(matches) == 1:
        p = matches[0]
        return MatchOutcome(
            resolved=True,
            order_ids=[p.order_id],
            payment_ids=[p.payment_id],
            rule_id="single_payment_net_match",
            confidence=0.97,
            evidence=[f"payment {p.payment_id} net amount and date match within tolerance"],
        )

    ranked = _closest(matches, bank_line.value_date)
    best, second = ranked[0], ranked[1]
    best_delta = abs((bank_line.value_date - best.captured_at).total_seconds())
    second_delta = abs((bank_line.value_date - second.captured_at).total_seconds())
    if best_delta < second_delta:
        return MatchOutcome(
            resolved=True,
            order_ids=[best.order_id],
            payment_ids=[best.payment_id],
            rule_id="single_payment_net_match_date_tiebreak",
            confidence=0.75,
            evidence=[
                f"{len(matches)} candidates tied on amount within tolerance; "
                f"{best.payment_id} is uniquely closest by date"
            ],
        )
    return MatchOutcome(
        resolved=False,
        reason_code="AMBIGUOUS_NARRATION_MULTI_CANDIDATE",
        evidence=[
            f"{len(matches)} candidates fit amount and date within tolerance with no dominant one: "
            + ", ".join(p.payment_id for p in matches)
        ],
        candidate_payment_ids=[p.payment_id for p in matches],
    )


def rule_subset_sum_split_settlement(
    bank_line: NormalizedBankLine, candidates: list[LedgerPayment]
) -> MatchOutcome | None:
    pool = [
        (p.payment_id, p.net_paise)
        for p in candidates
        if tolerance.within_date_tolerance(p.captured_at, bank_line.value_date)
    ]
    result = find_subset(pool, bank_line.credit_paise)
    if result.over_budget:
        return MatchOutcome(
            resolved=False,
            reason_code="SUBSET_SUM_OVER_BUDGET",
            evidence=[f"candidate pool of {len(pool)} payments exceeded the bounded subset-sum search budget"],
            candidate_payment_ids=[pid for pid, _ in pool],
        )
    if result.found and len(result.payment_ids) > 1:
        by_id = {p.payment_id: p for p in candidates}
        matched = [by_id[pid] for pid in result.payment_ids]
        return MatchOutcome(
            resolved=True,
            order_ids=[p.order_id for p in matched],
            payment_ids=[p.payment_id for p in matched],
            rule_id="subset_sum_split_settlement",
            confidence=0.93,
            evidence=[f"{len(matched)} payments sum exactly to the bank credit within tolerance"],
        )
    return None


# Built-in registry, in firing order. D1 (Phase 8) appends learned rules here after this list,
# never before -- built-ins always get first refusal so a learned rule can only narrow, not
# override, what the hand-written rules already resolve confidently.
BUILTIN_RULES = (
    rule_single_payment_net_match,
    rule_subset_sum_split_settlement,
)

__all__ = [
    "BUILTIN_RULES",
    "KNOWN_MERCHANT_TOKENS",
    "NARRATION_MATCH_THRESHOLD",
    "LedgerPayment",
    "MatchOutcome",
    "narration_similarity_score",
    "rule_single_payment_net_match",
    "rule_subset_sum_split_settlement",
]
