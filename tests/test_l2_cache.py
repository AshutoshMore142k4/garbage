import json

from ledgerguard.l2_llm_triage.budget_guard import BudgetGuard
from ledgerguard.l2_llm_triage.cache import ResponseCache
from ledgerguard.l2_llm_triage.client import TriageClient

BANK_LINE = {"credit_paise": 50000, "value_date": "2026-01-07T00:00:00Z", "narration": "ACMEENTERP123"}
CANDIDATES = [
    {"payment_id": "pay_1", "order_id": "order_1", "net_paise": 50000, "captured_at": "2026-01-05T00:00:00Z"},
]


class _Usage:
    input_tokens = 100
    output_tokens = 50


class _TextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Response:
    def __init__(self, text):
        self.content = [_TextBlock(text)]
        self.stop_reason = "end_turn"
        self.usage = _Usage()


class _CountTokens:
    input_tokens = 100


class CountingMessages:
    def __init__(self):
        self.create_call_count = 0

    def create(self, **kwargs):
        self.create_call_count += 1
        return _Response(json.dumps({"candidate_id": "pay_1", "confidence": 0.9, "evidence": ["match"]}))

    def count_tokens(self, **kwargs):
        return _CountTokens()


class ExplodingMessages:
    """A second client instance pointed at the same cache dir -- if this is ever called, the
    cache did not work as intended."""

    def create(self, **kwargs):
        raise AssertionError("cache hit should have skipped this call")

    def count_tokens(self, **kwargs):
        raise AssertionError("cache hit should have skipped this call")


def test_second_identical_call_is_served_from_cache(tmp_path):
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("system prompt", encoding="utf-8")
    cache_dir = tmp_path / "cache"

    messages = CountingMessages()
    client = TriageClient(
        messages_client=messages,
        budget_guard=BudgetGuard(max_spend_usd=10.0),
        cache=ResponseCache(cache_dir),
        prompt_path=prompt_path,
    )
    first_response, first_meta = client.triage(BANK_LINE, CANDIDATES)
    assert messages.create_call_count == 1
    assert first_meta["from_cache"] is False

    second_client = TriageClient(
        messages_client=ExplodingMessages(),
        budget_guard=BudgetGuard(max_spend_usd=10.0),
        cache=ResponseCache(cache_dir),
        prompt_path=prompt_path,
    )
    second_response, second_meta = second_client.triage(BANK_LINE, CANDIDATES)

    assert second_meta["from_cache"] is True
    assert second_meta["usd_cost"] == 0.0
    assert second_response.candidate_id == first_response.candidate_id
