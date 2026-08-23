import json

from ledgerguard.l2_llm_triage.budget_guard import BudgetGuard
from ledgerguard.l2_llm_triage.cache import ResponseCache
from ledgerguard.l2_llm_triage.client import TriageClient
from ledgerguard.l2_llm_triage.run import run_l2


class _Usage:
    input_tokens = 100
    output_tokens = 50


class _TextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Response:
    def __init__(self, candidate_id):
        body = json.dumps({"candidate_id": candidate_id, "confidence": 0.9, "evidence": ["ok"]})
        self.content = [_TextBlock(body)]
        self.stop_reason = "end_turn"
        self.usage = _Usage()


class _CountTokens:
    input_tokens = 100


class FakeMessages:
    def __init__(self):
        self.create_call_count = 0

    def create(self, **kwargs):
        self.create_call_count += 1
        return _Response("pay_1")

    def count_tokens(self, **kwargs):
        return _CountTokens()


def _write_residual(path):
    record = {
        "bank_line_id": "bl_1",
        "credit_paise": 50000,
        "narration": "ACMEENTERP123",
        "value_date": "2026-01-07T00:00:00Z",
        "candidates": [
            {"payment_id": "pay_1", "order_id": "order_1", "net_paise": 50000, "captured_at": "2026-01-05T00:00:00Z"}
        ],
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


def test_run_l2_with_triage_client_reports_spend_and_writes_results(tmp_path, monkeypatch):
    from ledgerguard.l2_llm_triage import run as run_module

    monkeypatch.setattr(run_module, "SPEND_STATE_PATH", tmp_path / "spend.json")

    residual_path = tmp_path / "residual.jsonl"
    _write_residual(residual_path)
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("system prompt", encoding="utf-8")

    client = TriageClient(
        messages_client=FakeMessages(),
        budget_guard=BudgetGuard(max_spend_usd=10.0),
        cache=ResponseCache(tmp_path / "cache"),
        prompt_path=prompt_path,
    )

    out_path = tmp_path / "l2_results.jsonl"
    summary = run_l2(residual_path, out_path, client)

    assert summary == {
        "considered": 1,
        "resolved": 1,
        "abstained": 0,
        "budget_exhausted": False,
        "total_spend_usd": summary["total_spend_usd"],
    }
    assert summary["total_spend_usd"] > 0.0

    results = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
    assert results[0]["candidate_id"] == "pay_1"

    spend_state = json.loads((tmp_path / "spend.json").read_text(encoding="utf-8"))
    assert spend_state["last_run_spend_usd"] == summary["total_spend_usd"]


def test_run_l2_with_no_client_uses_free_fallback_only(tmp_path):
    residual_path = tmp_path / "residual.jsonl"
    _write_residual(residual_path)
    out_path = tmp_path / "l2_results.jsonl"

    summary = run_l2(residual_path, out_path, None)

    assert summary["total_spend_usd"] == 0.0
    results = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
    assert results[0]["model"] == "fallback_rapidfuzz"
