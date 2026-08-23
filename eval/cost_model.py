"""L3 evaluation: the cost curve and the cost-optimal threshold (phases.md Phase 5 task 3/4/6).

The threshold is selected on validation only; the curve is then plotted on **holdout** with
that threshold marked, showing how the validation-chosen threshold generalizes rather than
re-selecting it on holdout (phases.md's holdout discipline: "Fit on validation. Report on
holdout."). Run as `python -m eval.cost_model`.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ledgerguard.l3_calibrate_gate.calibrator import Calibrator
from ledgerguard.l3_calibrate_gate.cost_model import CostDecision, expected_cost_paise, find_optimal_threshold
from ledgerguard.l3_calibrate_gate.decisions import Decision, build_decision_dataset
from ledgerguard.l3_calibrate_gate.exception_queue import ExceptionQueueEntry, build_exception_queue
from ledgerguard.l3_calibrate_gate.gate import ESCALATE, GateInput, gate

DEFAULT_OUTPUT_DIR = Path("eval/output")


def _cost_decisions(decisions: list[Decision], confidences: list[float]) -> list[CostDecision]:
    return [
        CostDecision(credit_paise=d.credit_paise, calibrated_confidence=c, correct=d.correct)
        for d, c in zip(decisions, confidences)
    ]


def build_holdout_exception_queue(
    decisions: list[Decision], calibrated_confidences: list[float], threshold: float
) -> list[ExceptionQueueEntry]:
    """Runs the real gate over holdout decisions and ranks everything it escalates by rupees
    at risk (phases.md Phase 5 task 5) -- not a synthetic example, the actual holdout output.
    """
    entries = []
    for d, calibrated in zip(decisions, calibrated_confidences):
        outcome = gate(
            GateInput(
                has_candidate=bool(d.order_ids),
                calibrated_confidence=calibrated,
                existing_reason_code=d.reason_code,
            ),
            threshold=threshold,
        )
        if outcome.action != ESCALATE:
            continue
        entries.append(
            ExceptionQueueEntry(
                bank_line_id=d.bank_line_id,
                amount_paise=d.credit_paise,
                reason_code=outcome.reason_code,
                calibrated_confidence=calibrated,
                evidence=d.evidence,
            )
        )
    return build_exception_queue(entries)


def plot_cost_curve(
    decisions: list[CostDecision], chosen_threshold: float, out_path: Path, grid_step: float = 0.01
) -> None:
    thresholds = [i * grid_step for i in range(int(round(1.0 / grid_step)) + 1)]
    costs_rupees = [expected_cost_paise(t, decisions) / 100 for t in thresholds]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(thresholds, costs_rupees, label="expected cost")
    ax.axvline(chosen_threshold, color="red", linestyle="--", label=f"chosen threshold = {chosen_threshold:.2f}")
    ax.set_xlabel("AUTO_POST threshold (calibrated confidence)")
    ax.set_ylabel("Expected cost (Rs.)")
    ax.set_title("L3 Cost Curve (holdout)")
    ax.legend()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Derive L3's cost-optimal threshold and plot the cost curve.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    data_dir = args.data_dir
    if not (data_dir / "bank_statement.csv").exists():
        data_dir = Path("data/samples")

    decisions = build_decision_dataset(data_dir)
    validation = [d for d in decisions if d.split == "validation"]
    holdout = [d for d in decisions if d.split == "holdout"]

    calibrator = Calibrator()
    calibrator.fit([d.features for d in validation], [d.correct for d in validation])

    validation_costs = _cost_decisions(validation, calibrator.predict_proba([d.features for d in validation]))
    threshold = find_optimal_threshold(validation_costs)

    holdout_calibrated = calibrator.predict_proba([d.features for d in holdout])
    holdout_costs = _cost_decisions(holdout, holdout_calibrated)

    out_path = args.out_dir / "cost_curve.png"
    plot_cost_curve(holdout_costs, threshold, out_path)

    queue = build_holdout_exception_queue(holdout, holdout_calibrated, threshold)
    queue_path = args.out_dir / "exception_queue.json"
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(
        json.dumps([vars(e) for e in queue], indent=2, sort_keys=True), encoding="utf-8"
    )

    print(f"L3 cost model, {data_dir}/:")
    print(f"  cost-optimal threshold (selected on validation): {threshold:.2f}")
    print(f"  expected cost on holdout at that threshold: Rs.{expected_cost_paise(threshold, holdout_costs) / 100:.2f}")
    print(f"  cost curve written to {out_path}")
    print(f"  exception queue: {len(queue)} escalated holdout cases, written to {queue_path}")
    for entry in queue[:5]:
        print(f"    Rs.{entry.amount_paise / 100:>10.2f}  {entry.reason_code:<40}  {entry.bank_line_id}")


if __name__ == "__main__":
    main()
