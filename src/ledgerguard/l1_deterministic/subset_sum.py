"""Bounded subset-sum for split-settlement matching (plan.md #9 L1, phases.md Phase 3).

Given candidate (payment_id, net_paise) pairs and a target credit_paise, finds a subset whose
net amounts sum exactly to the target. Bounded by `max_group_size` (how many payments may be
combined) and `max_search_nodes` (how many partial-sum expansions may be explored), so a
pathological candidate pool can never hang the matcher -- exceeding either bound returns
`over_budget=True` rather than continuing to search. phases.md Phase 3 is explicit that
exceeding the budget must escalate "by design, never hang."
"""
from __future__ import annotations

from dataclasses import dataclass, field

MAX_GROUP_SIZE = 12
MAX_SEARCH_NODES = 20_000


@dataclass
class SubsetSumResult:
    found: bool
    payment_ids: list[str] = field(default_factory=list)
    over_budget: bool = False


def find_subset(
    candidates: list[tuple[str, int]],
    target_paise: int,
    max_group_size: int = MAX_GROUP_SIZE,
    max_search_nodes: int = MAX_SEARCH_NODES,
) -> SubsetSumResult:
    if target_paise <= 0:
        return SubsetSumResult(found=False)

    # sum -> the payment_ids that reach it (first way found; ties are not re-explored)
    reachable: dict[int, tuple[str, ...]] = {0: ()}
    nodes_explored = 0

    for payment_id, amount in candidates:
        if amount <= 0 or amount > target_paise:
            continue
        new_entries: dict[int, tuple[str, ...]] = {}
        for existing_sum, ids in reachable.items():
            if len(ids) >= max_group_size:
                continue
            nodes_explored += 1
            if nodes_explored > max_search_nodes:
                return SubsetSumResult(found=False, over_budget=True)
            new_sum = existing_sum + amount
            if new_sum > target_paise or new_sum in reachable or new_sum in new_entries:
                continue
            new_ids = ids + (payment_id,)
            if new_sum == target_paise:
                return SubsetSumResult(found=True, payment_ids=list(new_ids))
            new_entries[new_sum] = new_ids
        reachable.update(new_entries)

    return SubsetSumResult(found=False)
