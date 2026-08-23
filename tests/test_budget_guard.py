import json

import pytest

from ledgerguard.l2_llm_triage.budget_guard import BudgetExhaustedError, BudgetGuard
from ledgerguard.l2_llm_triage.cache import ResponseCache
from ledgerguard.l2_llm_triage.client import TriageClient

BANK_LINE = {"credit_paise": 50000, "value_date": "2026-01-07T00:00:00Z", "narration": "ACMEENTERP123"}
CANDIDATES = [
    {"payment_id": "pay_1", "order_id": "order_1", "net_paise": 50000, "captured_at": "2026-01-05T00:00:00Z"},
]


def test_check_raises_when_projected_spend_exceeds_cap():
    guard = BudgetGuard(max_spend_usd=1.0)
    guard.spent_usd = 0.9

    with pytest.raises(BudgetExhaustedError):
        guard.check(0.2)


def test_check_does_not_mutate_spend():
    guard = BudgetGuard(max_spend_usd=1.0)
    with pytest.raises(BudgetExhaustedError):
        guard.check(2.0)
    assert guard.spent_usd == 0.0


def test_charge_commits_spend_when_within_cap():
    guard = BudgetGuard(max_spend_usd=1.0)
    guard.charge(0.3)
    guard.charge(0.3)
    assert guard.spent_usd == pytest.approx(0.6)


def test_charge_raises_and_does_not_partially_commit_over_cap():
    guard = BudgetGuard(max_spend_usd=1.0)
    guard.charge(0.9)
    with pytest.raises(BudgetExhaustedError):
        guard.charge(0.2)
    assert guard.spent_usd == pytest.approx(0.9)


class _Usage:
    input_tokens = 1_000_000  # deliberately huge, to force the pre-flight estimate over cap
    output_tokens = 1_000_000


class _TextBlock:
    type = "text"
    text = json.dumps({"candidate_id": "pay_1", "confidence": 0.9, "evidence": ["ok"]})


class _Response:
    content = [_TextBlock()]
    stop_reason = "end_turn"
    usage = _Usage()


class _CountTokens:
    input_tokens = 1_000_000  # ~$5 of input alone at claude-opus-5 pricing


class ExpensiveMessages:
    def __init__(self):
        self.create_call_count = 0

    def create(self, **kwargs):
        self.create_call_count += 1
        return _Response()

    def count_tokens(self, **kwargs):
        return _CountTokens()


def test_triage_client_aborts_loudly_before_calling_when_over_budget(tmp_path):
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("system prompt", encoding="utf-8")
    messages = ExpensiveMessages()
    client = TriageClient(
        messages_client=messages,
        budget_guard=BudgetGuard(max_spend_usd=0.01),  # far below the ~$5+ worst-case estimate
        cache=ResponseCache(tmp_path / "cache"),
        prompt_path=prompt_path,
    )

    with pytest.raises(BudgetExhaustedError):
        client.triage(BANK_LINE, CANDIDATES)

    assert messages.create_call_count == 0
