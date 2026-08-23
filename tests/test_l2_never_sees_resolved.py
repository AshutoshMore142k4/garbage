import json
from pathlib import Path

from ledgerguard.l1_deterministic.matcher import load_bank_lines, load_ledger_payments, run_l1, write_residual

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"


def test_l2_never_sees_a_bank_line_l1_already_resolved(tmp_path):
    """The core invariant (plan.md #9, phases.md Phase 4): if L1 resolves a record, L2 must
    never receive it. Since L2 only ever consumes bank lines from L1's residual output, proving
    the residual file excludes every resolved id *is* the invariant.
    """
    bank_lines = load_bank_lines(SAMPLES_DIR / "bank_statement.csv")
    payments = load_ledger_payments(SAMPLES_DIR / "internal_ledger.csv")

    results = run_l1(bank_lines, payments)
    residual_path = tmp_path / "residual.jsonl"
    write_residual(results, bank_lines, payments, residual_path)

    resolved_ids = {bank_line_id for bank_line_id, outcome in results.items() if outcome.resolved}
    unresolved_ids = {bank_line_id for bank_line_id, outcome in results.items() if not outcome.resolved}

    residual_ids = set()
    with open(residual_path, encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            residual_ids.add(record["bank_line_id"])

    assert residual_ids == unresolved_ids
    assert residual_ids.isdisjoint(resolved_ids)
    assert len(resolved_ids) > 0 and len(unresolved_ids) > 0  # sanity: the test data has both


def test_residual_candidate_sets_are_bounded(tmp_path):
    bank_lines = load_bank_lines(SAMPLES_DIR / "bank_statement.csv")
    payments = load_ledger_payments(SAMPLES_DIR / "internal_ledger.csv")

    results = run_l1(bank_lines, payments)
    residual_path = tmp_path / "residual.jsonl"
    write_residual(results, bank_lines, payments, residual_path, max_candidates=10)

    with open(residual_path, encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            assert len(record["candidates"]) <= 10
            for candidate in record["candidates"]:
                assert set(candidate.keys()) == {"payment_id", "order_id", "net_paise", "captured_at"}
