"""L3 evaluation: ECE + reliability diagram (phases.md Phase 5 task 6). Fits the calibrator on
validation only, reports on holdout. Run as `python -m eval.calibration`.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ledgerguard.l3_calibrate_gate.calibrator import Calibrator
from ledgerguard.l3_calibrate_gate.decisions import Decision, build_decision_dataset

DEFAULT_OUTPUT_DIR = Path("eval/output")
N_BINS = 10


def compute_ece(confidences: list[float], labels: list[bool], n_bins: int = N_BINS) -> float:
    conf = np.asarray(confidences, dtype=float)
    lab = np.asarray(labels, dtype=float)
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    n = len(conf)
    if n == 0:
        return 0.0

    ece = 0.0
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        mask = (conf >= lo) & (conf <= hi if i == n_bins - 1 else conf < hi)
        if not mask.any():
            continue
        ece += (mask.sum() / n) * abs(conf[mask].mean() - lab[mask].mean())
    return float(ece)


def plot_reliability_diagram(
    confidences: list[float], labels: list[bool], out_path: Path, n_bins: int = N_BINS
) -> None:
    conf = np.asarray(confidences, dtype=float)
    lab = np.asarray(labels, dtype=float)
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)

    centers, accuracies = [], []
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        mask = (conf >= lo) & (conf <= hi if i == n_bins - 1 else conf < hi)
        if not mask.any():
            continue
        centers.append((lo + hi) / 2)
        accuracies.append(lab[mask].mean())

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="perfect calibration")
    if centers:
        ax.bar(centers, accuracies, width=(1 / n_bins) * 0.9, alpha=0.7, label="observed accuracy")
    ax.set_xlabel("Calibrated confidence")
    ax.set_ylabel("Observed accuracy")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_title("L3 Reliability Diagram (holdout)")
    ax.legend()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def fit_and_evaluate(decisions: list[Decision]) -> dict:
    validation = [d for d in decisions if d.split == "validation"]
    holdout = [d for d in decisions if d.split == "holdout"]

    calibrator = Calibrator()
    calibrator.fit([d.features for d in validation], [d.correct for d in validation])

    holdout_calibrated = calibrator.predict_proba([d.features for d in holdout])
    holdout_labels = [d.correct for d in holdout]
    holdout_raw = [d.raw_confidence for d in holdout]

    return {
        "calibrator": calibrator,
        "validation": validation,
        "holdout": holdout,
        "holdout_calibrated": holdout_calibrated,
        "holdout_labels": holdout_labels,
        "ece_calibrated": compute_ece(holdout_calibrated, holdout_labels),
        "ece_raw": compute_ece(holdout_raw, holdout_labels),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Fit L3's calibrator on validation, report ECE on holdout.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    data_dir = args.data_dir
    if not (data_dir / "bank_statement.csv").exists():
        data_dir = Path("data/samples")

    decisions = build_decision_dataset(data_dir)
    result = fit_and_evaluate(decisions)

    out_path = args.out_dir / "reliability_diagram.png"
    plot_reliability_diagram(result["holdout_calibrated"], result["holdout_labels"], out_path)

    print(f"L3 calibration, {data_dir}/:")
    print(f"  validation examples: {len(result['validation'])}, holdout examples: {len(result['holdout'])}")
    print(f"  ECE (raw confidence, holdout):        {result['ece_raw']:.4f}")
    print(f"  ECE (calibrated confidence, holdout): {result['ece_calibrated']:.4f}")
    print(f"  reliability diagram written to {out_path}")


if __name__ == "__main__":
    main()
