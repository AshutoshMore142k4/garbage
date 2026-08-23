"""The pre-registered ablation (phases.md Phase 9 task 2; decision rule in PREREGISTRATION.md,
committed before this file's first holdout run -- verify with `git log`).

Three configs, same holdout, stratified by difficulty (EASY/MEDIUM/HARD/ADVERSARIAL):

- **rules-only**: L1's built-in rules only. Whatever L1 doesn't resolve counts as "no match
  predicted" -- L2 is never consulted.
- **hybrid**: the full shipped pipeline -- L1 first, L2 (fallback-served; see module docstring in
  `l3_calibrate_gate/decisions.py` for why there's no live model call in this environment) on
  whatever L1 leaves unresolved.
- **llm-only**: L1 is skipped entirely. Every bank line gets the same bounded candidate window
  L1 would have computed (`PaymentIndex.candidates_before`, unchanged) and goes straight to L2.

Run as `python -m benchmark.ablation` (`make bench`).
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ledgerguard.l0_normalize.normalize import normalize_timestamp
from ledgerguard.l1_deterministic.matcher import (
    MAX_CANDIDATES_FOR_L2,
    PaymentIndex,
    load_bank_lines,
    load_ledger_payments,
    run_l1,
)
from ledgerguard.l2_llm_triage.fallback import fallback_triage
from eval.metrics import STRATA, approx_llm_cost_per_call, USD_TO_INR

CONFIGS = ("rules_only", "hybrid", "llm_only")

# plan.md #24.2's binding decision rule -- transcribed once here, verbatim, from
# PREREGISTRATION.md #3. Never edited after seeing a result.
DELTA_HEADLINE = 0.08
DELTA_MODEST = 0.03


@dataclass
class Prediction:
    bank_line_id: str
    difficulty: str
    order_ids: list[str]
    correct_match: Optional[dict]
    llm_called: bool


def _candidate_dicts(payments_by_id: dict, payment_ids: list[str], value_date) -> list[dict]:
    bounded = sorted(
        (payments_by_id[pid] for pid in payment_ids if pid in payments_by_id),
        key=lambda p: abs((value_date - p.captured_at).total_seconds()),
    )[:MAX_CANDIDATES_FOR_L2]
    return [
        {
            "payment_id": p.payment_id,
            "order_id": p.order_id,
            "net_paise": p.net_paise,
            "captured_at": p.captured_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        for p in bounded
    ]


def predict_rules_only(bank_lines: list[dict], payments: list, ground_truth: dict) -> list[Prediction]:
    results = run_l1(bank_lines, payments)
    preds = []
    for row in bank_lines:
        gt = ground_truth[row["id"]]
        outcome = results[row["id"]]
        order_ids = outcome.order_ids if outcome.resolved else []
        preds.append(Prediction(row["id"], gt["difficulty"], order_ids, gt.get("correct_match"), False))
    return preds


def predict_hybrid(bank_lines: list[dict], payments: list, ground_truth: dict) -> list[Prediction]:
    payments_by_id = {p.payment_id: p for p in payments}
    results = run_l1(bank_lines, payments)
    preds = []
    for row in bank_lines:
        bl_id = row["id"]
        gt = ground_truth[bl_id]
        outcome = results[bl_id]
        if outcome.resolved:
            preds.append(Prediction(bl_id, gt["difficulty"], outcome.order_ids, gt.get("correct_match"), False))
            continue
        value_date = normalize_timestamp(row["value_date"])
        candidates = _candidate_dicts(payments_by_id, outcome.candidate_payment_ids, value_date)
        response = fallback_triage(row["narration"], candidates)
        order_ids = [payments_by_id[response.candidate_id].order_id] if response.candidate_id else []
        preds.append(Prediction(bl_id, gt["difficulty"], order_ids, gt.get("correct_match"), True))
    return preds


def predict_llm_only(bank_lines: list[dict], payments: list, ground_truth: dict) -> list[Prediction]:
    payments_by_id = {p.payment_id: p for p in payments}
    index = PaymentIndex(payments)
    preds = []
    for row in bank_lines:
        bl_id = row["id"]
        gt = ground_truth[bl_id]
        value_date = normalize_timestamp(row["value_date"])
        window_payments = index.candidates_before(value_date)
        candidates = _candidate_dicts(payments_by_id, [p.payment_id for p in window_payments], value_date)
        response = fallback_triage(row["narration"], candidates)
        order_ids = [payments_by_id[response.candidate_id].order_id] if response.candidate_id else []
        preds.append(Prediction(bl_id, gt["difficulty"], order_ids, gt.get("correct_match"), True))
    return preds


PREDICTORS = {"rules_only": predict_rules_only, "hybrid": predict_hybrid, "llm_only": predict_llm_only}


def score(preds: list[Prediction]) -> dict:
    """Standard entity-matching convention (PREREGISTRATION.md #2): a wrong non-empty proposal
    counts as both a false positive and a false negative; a correctly-abstained-on unmatchable
    line is a true negative and does not enter precision/recall.
    """
    tp = fp = fn = 0
    for p in preds:
        expected = set(p.correct_match["order_ids"]) if p.correct_match else set()
        proposed = set(p.order_ids)
        if not proposed and not expected:
            continue
        if proposed and proposed == expected:
            tp += 1
        else:
            if proposed:
                fp += 1
            if expected:
                fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"n": len(preds), "tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def run_ablation(data_dir: Path, split: str = "holdout") -> dict:
    bank_lines_all = load_bank_lines(data_dir / "bank_statement.csv")
    payments = load_ledger_payments(data_dir / "internal_ledger.csv")
    ground_truth = json.loads((data_dir / "ground_truth.json").read_text())

    bank_lines = [row for row in bank_lines_all if ground_truth[row["id"]]["split"] == split]
    cost_per_call = approx_llm_cost_per_call()

    table: dict[str, dict[str, dict]] = {}  # config -> stratum -> score dict (+ llm_calls, cost, latency)
    for config, predictor in PREDICTORS.items():
        start = time.perf_counter()
        preds = predictor(bank_lines, payments, ground_truth)
        elapsed = time.perf_counter() - start

        by_stratum = defaultdict(list)
        for p in preds:
            by_stratum[p.difficulty].append(p)

        table[config] = {}
        for stratum in (*STRATA, "Overall"):
            group = preds if stratum == "Overall" else by_stratum.get(stratum, [])
            s = score(group)
            llm_calls = sum(1 for p in group if p.llm_called)
            s["llm_calls"] = llm_calls
            s["cost_inr_per_1000"] = (llm_calls * cost_per_call / s["n"] * 1000 * USD_TO_INR) if s["n"] else 0.0
            s["p50_latency_ms"] = None  # fallback-served, no live call to time -- see eval/metrics.py
            table[config][stratum] = s

        # HARD+ADVERSARIAL combined, for the Δ decision rule (never per-stratum-averaged).
        hard_adversarial = by_stratum.get("HARD", []) + by_stratum.get("ADVERSARIAL", [])
        table[config]["HARD+ADVERSARIAL"] = score(hard_adversarial)
        table[config]["_elapsed_seconds"] = elapsed

    return table


def apply_decision_rule(table: dict) -> dict:
    delta_hard_adv = table["hybrid"]["HARD+ADVERSARIAL"]["f1"] - table["rules_only"]["HARD+ADVERSARIAL"]["f1"]
    delta_easy = table["hybrid"]["EASY"]["f1"] - table["rules_only"]["EASY"]["f1"]

    if delta_hard_adv >= DELTA_HEADLINE:
        band = "HEADLINE"
        verdict = (
            f"Delta = {delta_hard_adv:.3f} >= {DELTA_HEADLINE}: the LLM is load-bearing on ambiguous "
            "cases. The hybrid architecture is justified by measurement."
        )
    elif delta_hard_adv >= DELTA_MODEST:
        band = "MODEST"
        verdict = (
            f"Delta = {delta_hard_adv:.3f} is in [{DELTA_MODEST}, {DELTA_HEADLINE}): measurable but "
            "modest. Any claim must be scoped to the specific case class it was measured on -- no "
            "general claim about AI."
        )
    else:
        band = "NEGATIVE"
        verdict = (
            f"Delta = {delta_hard_adv:.3f} < {DELTA_MODEST}: the LLM is not justified on this holdout. "
            "Reported as a negative result, per PREREGISTRATION.md -- the deterministic layer does the "
            "work here."
        )

    easy_flag = abs(delta_easy) > 0.03  # "materially > 0" per PREREGISTRATION.md's own prediction
    return {
        "delta_hard_adversarial": delta_hard_adv,
        "delta_easy": delta_easy,
        "band": band,
        "verdict": verdict,
        "easy_gap_flagged": easy_flag,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the pre-registered rules-only/hybrid/llm-only ablation.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--split", default="holdout")
    parser.add_argument("--out", type=Path, default=Path("eval/output/ablation.json"))
    args = parser.parse_args()

    data_dir = args.data_dir
    if not (data_dir / "bank_statement.csv").exists():
        data_dir = Path("data/samples")

    table = run_ablation(data_dir, split=args.split)
    decision = apply_decision_rule(table)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"table": table, "decision": decision}, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Pre-registered ablation, {data_dir}/, split={args.split}:")
    print(f"{'stratum':<12}{'n':>5}{'rules F1':>10}{'hybrid F1':>11}{'llm F1':>9}{'llm calls':>11}{'INR/1k':>9}")
    for stratum in (*STRATA, "Overall"):
        r = table["rules_only"][stratum]
        h = table["hybrid"][stratum]
        l = table["llm_only"][stratum]
        print(
            f"{stratum:<12}{h['n']:>5}{r['f1']:>10.3f}{h['f1']:>11.3f}{l['f1']:>9.3f}"
            f"{h['llm_calls']:>11}{h['cost_inr_per_1000']:>9.2f}"
        )
    print()
    print(f"HARD+ADVERSARIAL: rules-only F1={table['rules_only']['HARD+ADVERSARIAL']['f1']:.3f}, "
          f"hybrid F1={table['hybrid']['HARD+ADVERSARIAL']['f1']:.3f}")
    print(f"Delta (HARD+ADVERSARIAL) = {decision['delta_hard_adversarial']:.3f}  [{decision['band']}]")
    print(f"Delta (EASY) = {decision['delta_easy']:.3f}" + ("  ** FLAGGED: materially != 0, see BROKE.md **" if decision["easy_gap_flagged"] else ""))
    print(f"Verdict: {decision['verdict']}")
    print(f"Full table written to {args.out}")


if __name__ == "__main__":
    main()
