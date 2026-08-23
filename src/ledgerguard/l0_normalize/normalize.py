"""L0 -- normalization (plan.md #9). Paise integers, UTC timestamps, narration cleanup.

This layer only cleans representations; it never makes a matching decision and never touches
the network (plan.md #9's L0 -> L1 pipeline; verified in tests/test_l1_no_network.py alongside
L1, since L0 always runs immediately before it).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

_KNOWN_PREFIXES = ("RZPX*", "RZP*", "NEFT-", "IMPS-", "UPI-")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_amount_paise(value: int | str) -> int:
    return int(value)


def normalize_timestamp(value: str) -> datetime:
    """Parse the project's canonical "%Y-%m-%dT%H:%M:%SZ" shape into an aware UTC datetime."""
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_narration(raw: str) -> str:
    text = _WHITESPACE_RE.sub(" ", raw.upper()).strip()
    for prefix in _KNOWN_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return text


@dataclass
class NormalizedBankLine:
    id: str
    utr: str | None
    credit_paise: int
    narration: str
    value_date: datetime


def normalize_bank_line(row: Mapping[str, object]) -> NormalizedBankLine:
    utr = row.get("utr") or None
    return NormalizedBankLine(
        id=str(row["id"]),
        utr=str(utr) if utr else None,
        credit_paise=normalize_amount_paise(row["credit_paise"]),  # type: ignore[arg-type]
        narration=normalize_narration(str(row["narration"])),
        value_date=normalize_timestamp(str(row["value_date"])),
    )
