"""The full reconciliation pipeline: L0 -> L1 -> L2 -> L3 -> L4 -> L5 -> audit (plan.md #9).
This is what `make close` runs.

Idempotency, end to end: `idempotency.derive_idempotency_key` is pure function of
`(batch_id, bank_line_id)` -- no wall clock, no randomness -- so rerunning the same batch_id
derives the exact same keys. `ledger.post_decision` only inserts a `match_decisions` row the
first time a key is seen (the DB's UNIQUE constraint enforces this even if this code didn't
check first). An audit line is appended **only when the DB insert was new**, so a rerun of an
already-posted batch appends nothing further -- `audit.jsonl` stays byte-identical, and
`match_decisions` gains zero duplicate rows. Both are checked by tests/test_idempotency.py.

`created_at` is deliberately the bank line's own `value_date`, not `datetime.now()` -- this
pipeline has no wall-clock dependency anywhere else (data/generator.py's own rule), and it
would be inconsistent to introduce one here purely for a log timestamp.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ledgerguard.audit.writer import AuditWriter
from ledgerguard.db import init_db
from ledgerguard.l1_deterministic.matcher import load_bank_lines, load_ledger_payments
from ledgerguard.l3_calibrate_gate.calibrator import Calibrator
from ledgerguard.l3_calibrate_gate.cost_model import CostDecision, find_optimal_threshold
from ledgerguard.l3_calibrate_gate.decisions import TriageFn, build_decision_dataset
from ledgerguard.l3_calibrate_gate.gate import GateInput, gate
from ledgerguard.l4_anomaly.detectors import detect_anomalies
from ledgerguard.l5_executor.authority import AuthorityInput, authorize
from ledgerguard.l5_executor.idempotency import derive_idempotency_key
from ledgerguard.l5_executor.ledger import post_decision
from ledgerguard.models import MatchDecision


DEFAULT_AUTHORITY_LIMIT_PAISE = 10_000_000  # matches .env.example; not a secret, so this module
# never needs config.get_settings() (which requires Razorpay/LLM credentials this pipeline has
# no use for -- see PROGRESS.md/BROKE.md on this repo having no credentials in any session).


def run_close(
    batch_id: str,
    data_dir: Path,
    db_path: Path,
    audit_path: Path,
    authority_limit_paise: int = DEFAULT_AUTHORITY_LIMIT_PAISE,
    triage_fn: Optional[TriageFn] = None,
) -> dict:
    """`triage_fn` defaults to `None` (the free fallback) -- pass a real provider client's
    `.triage` method (`l2_llm_triage/factory.py`) to have L2 answer from a live model. The CLI
    below never does this: a public demo/API should stay deterministic and free to run on every
    cold start, not spend real money or vary run to run on every judge's visit.
    """
    decisions = build_decision_dataset(data_dir, triage_fn=triage_fn)
    bank_lines = load_bank_lines(data_dir / "bank_statement.csv")
    payments = load_ledger_payments(data_dir / "internal_ledger.csv")
    bank_lines_by_id = {row["id"]: row for row in bank_lines}

    # L3: fit strictly on validation, select the threshold on validation, apply to everyone.
    validation = [d for d in decisions if d.split == "validation"]
    calibrator = Calibrator()
    calibrator.fit([d.features for d in validation], [d.correct for d in validation])

    calibrated_by_id = dict(
        zip((d.bank_line_id for d in decisions), calibrator.predict_proba([d.features for d in decisions]))
    )
    validation_costs = [
        CostDecision(credit_paise=d.credit_paise, calibrated_confidence=calibrated_by_id[d.bank_line_id], correct=d.correct)
        for d in validation
    ]
    threshold = find_optimal_threshold(validation_costs)

    # L4: anomaly flags have veto power, applied below regardless of gate/authority outcome.
    anomalies_by_bank_line: dict[str, list] = {}
    for flag in detect_anomalies(decisions, bank_lines, payments):
        if flag.bank_line_id:
            anomalies_by_bank_line.setdefault(flag.bank_line_id, []).append(flag)

    conn = init_db(db_path)
    audit = AuditWriter(audit_path)

    counts = {"AUTO_POST": 0, "ESCALATE": 0, "FLAG_ANOMALY": 0, "posted_new": 0, "already_posted": 0}

    for d in decisions:
        calibrated = calibrated_by_id[d.bank_line_id]
        anomaly_flags = anomalies_by_bank_line.get(d.bank_line_id, [])

        gate_outcome = gate(
            GateInput(
                has_candidate=bool(d.order_ids),
                calibrated_confidence=calibrated,
                existing_reason_code=d.reason_code,
            ),
            threshold=threshold,
        )
        final_action = authorize(
            AuthorityInput(
                gate_action=gate_outcome.action,
                amount_paise=d.credit_paise,
                authority_limit_paise=authority_limit_paise,
                has_anomaly=bool(anomaly_flags),
            )
        )

        if anomaly_flags:
            resolver = "L4_ANOMALY"
            rule_id = None
            model = None
            prompt_hash = None
            reason_code = anomaly_flags[0].reason_code
            evidence = [e for flag in anomaly_flags for e in flag.evidence]
        else:
            resolver = d.resolver if d.order_ids else "ABSTAIN"
            rule_id = d.rule_id
            model = d.model
            prompt_hash = d.prompt_hash
            reason_code = gate_outcome.reason_code
            evidence = d.evidence

        idempotency_key = derive_idempotency_key(batch_id, d.bank_line_id)
        decision = MatchDecision(
            decision_id=f"dec_{idempotency_key}",
            batch_id=batch_id,
            bank_line_id=d.bank_line_id,
            resolver=resolver,
            rule_id=rule_id,
            model=model,
            prompt_hash=prompt_hash,
            raw_confidence=d.raw_confidence,
            calibrated_confidence=calibrated,
            threshold=threshold,
            action=final_action,
            reason_code=reason_code,
            evidence=evidence,
            idempotency_key=idempotency_key,
            created_at=bank_lines_by_id[d.bank_line_id]["value_date"],
        )

        if post_decision(conn, decision):
            audit.append(decision)
            counts["posted_new"] += 1
        else:
            counts["already_posted"] += 1
        counts[final_action] = counts.get(final_action, 0) + 1

    conn.close()
    return counts


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the full L0-L5 reconciliation pipeline.")
    parser.add_argument("--batch-id", default="batch-default")
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--db-path", type=Path, default=Path("ledgerguard.db"))
    parser.add_argument("--audit-path", type=Path, default=Path("audit.jsonl"))
    args = parser.parse_args()

    data_dir = args.data_dir
    if not (data_dir / "bank_statement.csv").exists():
        data_dir = Path("data/samples")

    authority_limit_paise = DEFAULT_AUTHORITY_LIMIT_PAISE
    try:
        from ledgerguard.config import get_settings

        authority_limit_paise = get_settings().authority_limit_paise
    except Exception:
        pass  # no .env / Razorpay+LLM secrets in this environment -- use the documented default

    counts = run_close(args.batch_id, data_dir, args.db_path, args.audit_path, authority_limit_paise)

    total = counts["AUTO_POST"] + counts["ESCALATE"] + counts["FLAG_ANOMALY"]
    print(f"make close, batch={args.batch_id}, {data_dir}/:")
    print(f"  AUTO_POST {counts['AUTO_POST']}, ESCALATE {counts['ESCALATE']}, FLAG_ANOMALY {counts['FLAG_ANOMALY']} (total {total})")
    print(f"  newly posted {counts['posted_new']}, already posted (idempotent no-op) {counts['already_posted']}")
    print(f"  db: {args.db_path}")
    print(f"  audit: {args.audit_path}")


if __name__ == "__main__":
    main()
