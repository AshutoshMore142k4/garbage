"""One-off generator for docs/architecture.png (phases.md Phase 9: "docs/architecture.md +
diagram image"). Not part of the reproducible benchmark pipeline -- this draws a static
illustration of the L0-L5 + D1 pipeline (plan.md #9's own ASCII diagram, rendered as an image),
and its output is committed directly to docs/, unlike eval/output/'s regenerated-and-gitignored
run charts.

Run as `python docs/generate_architecture_diagram.py` to regenerate after an architecture change.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT_PATH = Path(__file__).parent / "architecture.png"

STAGES = [
    ("L0", "Normalization", "paise ints, UTC,\nnarration clean"),
    ("L1", "Deterministic Matcher", "amount+date tolerance,\nbounded subset-sum"),
    ("L2", "LLM Triage (residual only)", "~8-15% of records,\nschema-validated, bounded"),
    ("L3", "Calibrated Gate", "cost-optimal threshold,\nexception queue"),
    ("L4", "Anomaly Detection", "veto power over L1 & L3"),
    ("L5", "Bounded Executor", "authority policy,\nidempotency key"),
]

DECISIONS = ["AUTO_POST\n→ ledger", "ESCALATE\n→ exception queue"]


def _box(ax, xy, w, h, title, subtitle, color):
    box = FancyBboxPatch(
        xy, w, h, boxstyle="round,pad=0.02,rounding_size=0.06",
        linewidth=1.4, edgecolor="#333333", facecolor=color,
    )
    ax.add_patch(box)
    cx, cy = xy[0] + w / 2, xy[1] + h / 2
    ax.text(cx, cy + h * 0.16, title, ha="center", va="center", fontsize=11, fontweight="bold")
    ax.text(cx, cy - h * 0.22, subtitle, ha="center", va="center", fontsize=8, color="#333333")


def _arrow(ax, start, end, label=None, color="#333333", style="-"):
    arrow = FancyArrowPatch(
        start, end, arrowstyle="-|>", mutation_scale=14, linewidth=1.3, color=color, linestyle=style,
    )
    ax.add_patch(arrow)
    if label:
        mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
        ax.text(mx + 0.15, my, label, fontsize=7.5, color=color, va="center")


def main() -> None:
    fig, ax = plt.subplots(figsize=(6.5, 11.8))
    ax.set_xlim(0, 6)
    ax.set_ylim(0, 23.2)
    ax.axis("off")

    box_w, box_h = 4.4, 1.7
    x0 = (6 - box_w) / 2
    ys = [19.5, 17.0, 14.0, 11.5, 9.0, 6.5]
    colors = ["#dbe9f6", "#dbe9f6", "#fde2c8", "#dbe9f6", "#f6d6d6", "#dbe9f6"]

    for (code, title, subtitle), y, color in zip(STAGES, ys, colors):
        _box(ax, (x0, y), box_w, box_h, f"{code}  {title}", subtitle, color)

    for i in range(len(ys) - 1):
        top = ys[i]
        bottom_next = ys[i + 1] + box_h
        label = None
        if i == 1:
            label = "residual only\n(~8-15%)"
        _arrow(ax, (3, top), (3, bottom_next), label=label)

    # sources feeding L0
    _box(ax, (0.1, 21.4), 2.5, 1.0, "Razorpay TEST MODE", "orders/payments/refunds*", "#eef2ee")
    _box(ax, (3.4, 21.4), 2.5, 1.0, "Synthetic generator", "bank statement + chaos", "#eef2ee")
    _arrow(ax, (1.35, 21.4), (2.0, 21.2))
    _arrow(ax, (4.65, 21.4), (4.0, 21.2))

    # decision fork under L5
    l5_bottom = ys[5]
    for dx, label in zip((-1.4, 1.4), DECISIONS):
        cx = 3 + dx
        _box(ax, (cx - 1.0, 4.0), 2.0, 1.2, label, "", "#e3f0da")
        _arrow(ax, (3, l5_bottom), (cx, 5.2))

    # audit + D1
    _box(ax, (x0, 1.8), box_w, 1.1, "audit.jsonl", "append-only, replayable", "#eef2ee")
    _arrow(ax, (1.6, 4.0), (2.6, 2.9))
    _arrow(ax, (4.4, 4.0), (4.0, 2.9))

    _box(ax, (x0, 0.0), box_w, 1.1, "D1 Rule Learning", "resolved exception → candidate → promote to L1", "#fdeec8")
    _arrow(ax, (3, 1.8), (3, 1.1))
    _arrow(ax, (x0, 0.55), (x0 - 0.15, 15.5), color="#8a6d1a", style="--")
    ax.text(x0 - 0.5, 8.0, "promoted rules\nfeed back into L1", fontsize=7, color="#8a6d1a", rotation=90, ha="center")

    ax.set_title("LedgerGuard: L0→L5 + D1 (plan.md #9)", fontsize=13, fontweight="bold", pad=10)
    fig.tight_layout()
    fig.savefig(OUT_PATH, dpi=150)
    plt.close(fig)
    print(f"architecture diagram written to {OUT_PATH}")


if __name__ == "__main__":
    main()
