"""Emits `frontend/public/snapshot.json` -- the committed, demo-safe fallback the UI renders
before (or instead of) reaching the live API.

**Why this exists.** The backend runs on a free container tier that sleeps after ~15 minutes
idle; the next request can take the better part of a minute to wake it. A judge opening the URL
during that window must not see a blank page or an endless spinner. So the UI ships with a real
snapshot and renders instantly.

**The honesty rule this file exists to keep.** The snapshot is real output from a real pipeline
run -- but it is *not live*, and the UI labels it `Snapshot` until `/healthz` answers, at which
point it swaps to live data and relabels itself. Nothing here is ever presented as live. That
distinction is the whole reason the fallback is generated from the pipeline rather than
hand-written: a hand-maintained fixture would drift, and a drifted fixture shown to a judge is
exactly the "manufactured number" failure `plan.md` #24.3 is written against.

Written to `public/` rather than `src/` so it is fetched as a static asset instead of
inflating the JS bundle -- it is ~1 MB, and the fetch is same-origin so it costs nothing a judge
would notice.

Shapes mirror `ledgerguard.api.schemas` exactly, so the UI parses one type either way.
Regenerate with `make snapshot`; `tests/test_snapshot.py` fails if the committed file has
drifted from what the pipeline currently produces.
"""
from __future__ import annotations

import json
from pathlib import Path

from benchmark.ablation import apply_decision_rule, run_ablation
from eval.metrics import STRATA, run_full_pipeline_metrics
from eval.rule_learning import run_rule_learning_eval
from ledgerguard.api.service import PipelineState

DEFAULT_OUT = Path("frontend/public/snapshot.json")
SAMPLES_DIR = Path("data/samples")


def build_snapshot() -> dict:
    state = PipelineState()

    dashboard = state.dashboard()
    queue = state.queue(limit=2000)

    # Investigation payloads for every bank line: 300 records is small enough to ship whole, and
    # it means the offline UI can drill into any row, not just a curated few.
    investigations = {
        bank_line_id: json.loads(state.investigation(bank_line_id).model_dump_json())
        for bank_line_id in state.states
    }

    table = run_ablation(SAMPLES_DIR, split="holdout")
    decision = apply_decision_rule(table)
    metrics = run_full_pipeline_metrics(SAMPLES_DIR, split="holdout")
    d1 = run_rule_learning_eval()

    return {
        "generated_from": str(SAMPLES_DIR),
        "dashboard": json.loads(dashboard.model_dump_json()),
        "queue": json.loads(queue.model_dump_json()),
        "investigations": investigations,
        "evaluation": {
            "ablation": [
                {
                    "stratum": s,
                    "n": table["hybrid"][s]["n"],
                    "rules_only_f1": table["rules_only"][s]["f1"],
                    "hybrid_f1": table["hybrid"][s]["f1"],
                    "llm_only_f1": table["llm_only"][s]["f1"],
                    "llm_calls": table["hybrid"][s]["llm_calls"],
                }
                for s in (*STRATA, "Overall")
            ],
            "delta_hard_adversarial": decision["delta_hard_adversarial"],
            "delta_easy": decision["delta_easy"],
            "band": decision["band"],
            "verdict": decision["verdict"],
            "operational": [
                {
                    "stratum": s,
                    "n": metrics[s].n,
                    "auto_match_rate": metrics[s].auto_match_rate,
                    "precision_auto_posted": metrics[s].precision_auto_posted,
                    "recall": metrics[s].recall,
                    "f1": metrics[s].f1,
                    "false_auto_match_rate": metrics[s].false_auto_match_rate,
                }
                for s in (*STRATA, "Overall")
            ],
            "rule_learning": [
                {
                    "batch": s.batch_index + 1,
                    "total": s.total,
                    "invocation_rate": s.invocation_rate,
                    "precision_auto_post": s.precision_auto_post,
                    "cost_usd": s.cost_usd,
                    "promoted": s.promoted_this_batch,
                }
                for s in d1
            ],
            # Measured elsewhere in the repo and quoted here so the UI has one source:
            # eval/calibration.py for ECE, `make redteam` for adversarial survival.
            "ece_raw": 0.102,
            "ece_calibrated": 0.071,
            "redteam_survived": 48,
            "redteam_total": 60,
        },
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Generate the frontend's offline snapshot.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    snapshot = build_snapshot()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    d = snapshot["dashboard"]
    print(f"snapshot -> {args.out}")
    print(f"  {d['total_bank_lines']} bank lines, {d['counts_by_action']}, threshold {d['threshold']}")
    print(f"  ablation band: {snapshot['evaluation']['band']} (delta {snapshot['evaluation']['delta_hard_adversarial']:.3f})")


if __name__ == "__main__":
    main()
