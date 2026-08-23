import json

from ledgerguard.audit.writer import AuditWriter
from ledgerguard.models import MatchDecision


def _decision(decision_id: str) -> MatchDecision:
    return MatchDecision(
        decision_id=decision_id,
        batch_id="batch-1",
        bank_line_id=f"bl-{decision_id}",
        resolver="L1_RULE",
        rule_id="exact_utr",
        action="AUTO_POST",
        idempotency_key=f"idem-{decision_id}",
        created_at="2026-08-22T00:00:00Z",
    )


def test_append_writes_one_line_per_decision(tmp_path):
    writer = AuditWriter(tmp_path / "audit.jsonl")

    writer.append(_decision("1"))
    writer.append(_decision("2"))

    lines = writer.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["decision_id"] == "1"
    assert json.loads(lines[1])["decision_id"] == "2"


def test_existing_content_is_never_modified(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    writer = AuditWriter(log_path)
    writer.append(_decision("1"))
    first_line_after_first_write = log_path.read_text(encoding="utf-8")

    # A second writer instance pointed at the same file must only append, never truncate.
    second_writer = AuditWriter(log_path)
    second_writer.append(_decision("2"))

    content = log_path.read_text(encoding="utf-8")
    assert content.startswith(first_line_after_first_write)
    assert len(content.splitlines()) == 2
