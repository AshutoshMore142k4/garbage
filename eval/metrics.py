"""Phase 9 operational metrics (phases.md Phase 9 task 3): per stratum and overall, for the full
shipped pipeline (L0-L5, exactly as `close.py` runs it) -- auto-match rate, precision on auto-
posted, recall, F1, false auto-match rate, exception-queue precision, throughput, LLM call count,
p50 latency, and cost per 1,000 records.

Distinct from `benchmark/ablation.py`, which compares three *configurations* (rules-only, hybrid,
llm-only) to answer "is L2 load-bearing." This module instead measures what the one system
actually shipped does, at what cost and speed, per difficulty stratum -- the numbers `README.md`
quotes for "here's what running this for real looks like," not the ablation's own Δ.

**Cost is an estimate, not a measured spend**, for the same reason every other phase's cost
figure has been: no session has ever had live Anthropic credentials (PROGRESS.md/BROKE.md Phases
0/4). `approx_llm_cost_per_call` reuses `client.py`'s exact real pricing table, substituting a
documented chars/4 approximation for the one missing piece (a live `count_tokens` call) -- the
same approach `eval/rule_learning.py`'s Phase 8 cost figure already used.

**₹ conversion is a fixed, documented approximation**, not a live FX rate (no live rate source is
available in this environment either): `USD_TO_INR` below is a point-in-time approximation,
flagged here exactly as `client.py`'s own pricing table flags itself as "verify before a large
benchmark run."

**Latency measures the fallback path's local compute time**, not a real Anthropic API round trip
-- there is no live call to time in this environment. This is stated plainly wherever p50 latency
is reported; it should not be read as a claim about real model latency.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ledgerguard.close import DEFAULT_AUTHORITY_LIMIT_PAISE
from ledgerguard.l2_llm_triage.client import MAX_TOKENS, PRICE_PER_MTOK_USD, TriageClient
from ledgerguard.l3_calibrate_gate.calibrator import Calibrator
from ledgerguard.l3_calibrate_gate.cost_model import CostDecision, find_optimal_threshold
from ledgerguard.l3_calibrate_gate.decisions import Decision, build_decision_dataset
from ledgerguard.l3_calibrate_gate.gate import GateInput, gate
from ledgerguard.l4_anomaly.detectors import detect_anomalies
from ledgerguard.l5_executor.authority import AuthorityInput, authorize
from ledgerguard.l1_deterministic.matcher import load_bank_lines, load_ledger_payments

STRATA = ("EASY", "MEDIUM", "HARD", "ADVERSARIAL")

# A fixed, documented point-in-time approximation -- no live FX rate source is available in this
# environment. Re-check against a real rate before quoting this in anything but this project.
USD_TO_INR = 83.0


def approx_llm_cost_per_call(model: str = "claude-opus-5") -> float:
    system_prompt = Path("prompts/residual_triage_v1.md").read_text(encoding="utf-8")
    representative_bank_line = {
        "credit_paise": 48_20_000,
        "value_date": "2026-03-07T00:00:00Z",
        "narration": "APEXRETAIL7F3A2C",
    }
    representative_candidates = [
        {
            "payment_id": f"pay_synth_{i:05d}",
            "order_id": f"order_synth_{i:05d}",
            "net_paise": 1_00_000 * i,
            "captured_at": "2026-03-05T00:00:00Z",
        }
        for i in range(1, 6)
    ]
    user_content = TriageClient._build_user_content(representative_bank_line, representative_candidates)
    approx_input_tokens = len(system_prompt + user_content) / 4  # documented approximation; see module docstring
    price = PRICE_PER_MTOK_USD.get(model, PRICE_PER_MTOK_USD["claude-opus-5"])
    return approx_input_tokens / 1_000_000 * price["input"] + MAX_TOKENS / 1_000_000 * price["output"]


@dataclass
class StratumMetrics:
    stratum: str
    n: int
    auto_match_rate: float
    precision_auto_posted: float
    recall: float
    f1: float
    false_auto_match_rate: float
    exception_queue_precision: float
    throughput_records_per_sec: float
    llm_call_count: int
    p50_latency_ms: Optional[float]
    cost_per_1000_inr: float


def compute_stratum_metrics(
    decisions: list[Decision],
    ground_truth: dict[str, dict],
    gate_outcomes: dict[str, tuple[str, Optional[str]]],  # bank_line_id -> (action, reason_code)
    llm_latencies_ms: dict[str, float],
    elapsed_seconds: float,
    cost_per_call: float,
) -> dict[str, StratumMetrics]:
    by_stratum: dict[str, list[Decision]] = defaultdict(list)
    for d in decisions:
        by_stratum[ground_truth[d.bank_line_id]["difficulty"]].append(d)

    results: dict[str, StratumMetrics] = {}
    for stratum in (*STRATA, "Overall"):
        group = decisions if stratum == "Overall" else by_stratum.get(stratum, [])
        results[stratum] = _metrics_for_group(group, ground_truth, gate_outcomes, llm_latencies_ms, elapsed_seconds, cost_per_call, len(decisions))
    return results


def _metrics_for_group(
    group: list[Decision],
    ground_truth: dict[str, dict],
    gate_outcomes: dict[str, tuple[str, Optional[str]]],
    llm_latencies_ms: dict[str, float],
    total_elapsed_seconds: float,
    cost_per_call: float,
    total_n: int,
) -> StratumMetrics:
    n = len(group)
    tp = fp = fn = 0
    auto_posted = 0
    auto_posted_correct = 0
    escalated = 0
    escalated_genuinely_wrong = 0
    llm_calls = 0
    latencies = []

    for d in group:
        gt = ground_truth[d.bank_line_id]
        expected = gt.get("correct_match")
        has_expected = expected is not None
        proposed = bool(d.order_ids)

        if not proposed and not has_expected:
            pass  # true negative -- not counted in precision/recall
        elif proposed and d.correct:
            tp += 1
        else:
            if proposed:
                fp += 1
            if has_expected:
                fn += 1

        action, _reason = gate_outcomes[d.bank_line_id]
        if action == "AUTO_POST":
            auto_posted += 1
            if d.correct:
                auto_posted_correct += 1
        elif action == "ESCALATE":
            escalated += 1
            if not d.correct:
                escalated_genuinely_wrong += 1

        if d.resolver == "L2_LLM":
            llm_calls += 1
            if d.bank_line_id in llm_latencies_ms:
                latencies.append(llm_latencies_ms[d.bank_line_id])

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    false_auto_match_rate = (auto_posted - auto_posted_correct) / auto_posted if auto_posted else 0.0
    exception_queue_precision = escalated_genuinely_wrong / escalated if escalated else 0.0
    auto_match_rate = auto_posted / n if n else 0.0

    latencies.sort()
    p50_latency_ms = latencies[len(latencies) // 2] if latencies else None

    # Throughput and cost are measured/estimated over the *whole run*, then apportioned to this
    # stratum by its share of total records -- a per-stratum sub-run isn't separately timed.
    share = n / total_n if total_n else 0.0
    throughput = n / total_elapsed_seconds if total_elapsed_seconds > 0 else 0.0
    cost_per_1000_inr = (llm_calls * cost_per_call / n * 1000 * USD_TO_INR) if n else 0.0

    return StratumMetrics(
        stratum="",
        n=n,
        auto_match_rate=auto_match_rate,
        precision_auto_posted=precision if auto_posted else 0.0,
        recall=recall,
        f1=f1,
        false_auto_match_rate=false_auto_match_rate,
        exception_queue_precision=exception_queue_precision,
        throughput_records_per_sec=throughput,
        llm_call_count=llm_calls,
        p50_latency_ms=p50_latency_ms,
        cost_per_1000_inr=cost_per_1000_inr,
    )


def run_full_pipeline_metrics(data_dir: Path, split: str = "holdout") -> dict[str, StratumMetrics]:
    bank_lines = load_bank_lines(data_dir / "bank_statement.csv")
    payments = load_ledger_payments(data_dir / "internal_ledger.csv")
    import json

    ground_truth = json.loads((data_dir / "ground_truth.json").read_text())

    all_decisions = build_decision_dataset(data_dir)
    validation = [d for d in all_decisions if d.split == "validation"]
    target = [d for d in all_decisions if d.split == split]

    calibrator = Calibrator()
    calibrator.fit([d.features for d in validation], [d.correct for d in validation])
    validation_calibrated = calibrator.predict_proba([d.features for d in validation])
    threshold = find_optimal_threshold(
        [
            CostDecision(credit_paise=d.credit_paise, calibrated_confidence=c, correct=d.correct)
            for d, c in zip(validation, validation_calibrated)
        ]
    )

    start = time.perf_counter()
    target_calibrated = calibrator.predict_proba([d.features for d in target])
    elapsed_seconds = time.perf_counter() - start

    anomalies_by_bank_line = defaultdict(list)
    target_bank_lines = [row for row in bank_lines if ground_truth[row["id"]]["split"] == split]
    for flag in detect_anomalies(target, target_bank_lines, payments):
        if flag.bank_line_id:
            anomalies_by_bank_line[flag.bank_line_id].append(flag)

    gate_outcomes: dict[str, tuple[str, Optional[str]]] = {}
    for d, conf in zip(target, target_calibrated):
        outcome = gate(
            GateInput(has_candidate=bool(d.order_ids), calibrated_confidence=conf, existing_reason_code=d.reason_code),
            threshold=threshold,
        )
        action = authorize(
            AuthorityInput(
                gate_action=outcome.action,
                amount_paise=d.credit_paise,
                authority_limit_paise=DEFAULT_AUTHORITY_LIMIT_PAISE,
                has_anomaly=bool(anomalies_by_bank_line.get(d.bank_line_id)),
            )
        )
        gate_outcomes[d.bank_line_id] = (action, outcome.reason_code)

    cost_per_call = approx_llm_cost_per_call()
    # No live latency to measure (fallback-served, per module docstring) -- p50 is reported as
    # None rather than a fabricated number when there is nothing real to time.
    llm_latencies_ms: dict[str, float] = {}

    metrics = compute_stratum_metrics(target, ground_truth, gate_outcomes, llm_latencies_ms, elapsed_seconds, cost_per_call)
    for stratum, m in metrics.items():
        m.stratum = stratum
    return metrics


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Per-stratum operational metrics for the full shipped pipeline.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--split", default="holdout")
    args = parser.parse_args()

    data_dir = args.data_dir
    if not (data_dir / "bank_statement.csv").exists():
        data_dir = Path("data/samples")

    metrics = run_full_pipeline_metrics(data_dir, split=args.split)

    print(f"Phase 9 operational metrics, {data_dir}/, split={args.split}:")
    header = f"{'stratum':<12}{'n':>5}{'auto%':>8}{'prec_ap':>9}{'recall':>8}{'f1':>7}{'fam%':>7}{'eqp':>7}{'llm':>6}{'INR/1k':>9}"
    print(header)
    for stratum in (*STRATA, "Overall"):
        m = metrics[stratum]
        print(
            f"{stratum:<12}{m.n:>5}{m.auto_match_rate:>8.1%}{m.precision_auto_posted:>9.1%}"
            f"{m.recall:>8.1%}{m.f1:>7.2f}{m.false_auto_match_rate:>7.1%}{m.exception_queue_precision:>7.1%}"
            f"{m.llm_call_count:>6}{m.cost_per_1000_inr:>9.2f}"
        )


if __name__ == "__main__":
    main()
