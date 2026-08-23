"""Amount + date-tolerance band (plan.md #9's "amount + date-tolerance band (T+2 window)").

The synthetic generator (data/generator.py) always settles a payment at
`captured_at + 2 days` and then adds 0-3 days of bank posting delay (its DATE_SKEW_BOUNDARY
category uses exactly 2 or 3 days on purpose, to sit at and just past a tolerance boundary).
MAX_SETTLEMENT_DAYS=4 is therefore chosen deliberately to accept the "at boundary" case
(2 + 2 = 4) and reject the "one day over" case (2 + 3 = 5) -- see tests/test_l1_rules.py's
boundary cases.
"""
from __future__ import annotations

from datetime import datetime

MIN_SETTLEMENT_DAYS = 2
MAX_SETTLEMENT_DAYS = 4


def within_date_tolerance(
    captured_at: datetime,
    value_date: datetime,
    min_days: float = MIN_SETTLEMENT_DAYS,
    max_days: float = MAX_SETTLEMENT_DAYS,
) -> bool:
    delta_days = (value_date - captured_at).total_seconds() / 86400
    return min_days <= delta_days <= max_days
