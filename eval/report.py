"""Renders `report.md` + `report.html` from a single `make bench` run (phases.md Phase 9 task
5). Every number here comes from `benchmark/ablation.py`'s and `eval/metrics.py`'s own committed
output -- this module does no independent computation, so nothing here can drift from the numbers
`make bench` actually produced.

Run as `python -m eval.report` (after `make bench`).
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Template

from eval.metrics import STRATA, run_full_pipeline_metrics
from benchmark.ablation import run_ablation, apply_decision_rule

MD_TEMPLATE = """\
# LedgerGuard — Benchmark Report

Generated from a single `make bench` run against `{{ data_dir }}` (split: `{{ split }}`). Every
number below traces to `eval/output/ablation.json`; nothing here is hand-edited.

## Pre-registered ablation (see `PREREGISTRATION.md`)

| Stratum | n | Rules-only F1 | Hybrid F1 | LLM-only F1 | LLM calls | ₹/1,000 |
|---|---|---|---|---|---|---|
{%- for row in ablation_rows %}
| {{ row.stratum }} | {{ row.n }} | {{ "%.3f"|format(row.rules_f1) }} | {{ "%.3f"|format(row.hybrid_f1) }} | {{ "%.3f"|format(row.llm_f1) }} | {{ row.llm_calls }} | {{ "%.2f"|format(row.cost) }} |
{%- endfor %}

**Δ (HARD+ADVERSARIAL) = {{ "%.3f"|format(decision.delta_hard_adversarial) }}** — band: **{{ decision.band }}**

> {{ decision.verdict }}

**Δ (EASY) = {{ "%.3f"|format(decision.delta_easy) }}**{% if decision.easy_gap_flagged %} — **flagged**: materially different from the pre-registered Δ≈0 expectation; see `BROKE.md`.{% endif %}

## Operational metrics (full shipped pipeline, per stratum)

| Stratum | n | Auto-match % | Precision (auto-posted) | Recall | F1 | False auto-match % | Exception-queue precision | LLM calls | ₹/1,000 |
|---|---|---|---|---|---|---|---|---|---|
{%- for row in metrics_rows %}
| {{ row.stratum }} | {{ row.n }} | {{ "%.1f"|format(row.auto_match_rate * 100) }}% | {{ "%.1f"|format(row.precision_auto_posted * 100) }}% | {{ "%.1f"|format(row.recall * 100) }}% | {{ "%.2f"|format(row.f1) }} | {{ "%.1f"|format(row.false_auto_match_rate * 100) }}% | {{ "%.1f"|format(row.exception_queue_precision * 100) }}% | {{ row.llm_call_count }} | {{ "%.2f"|format(row.cost_per_1000_inr) }} |
{%- endfor %}

## Charts

- `reliability_diagram.png` — L3 calibration (Phase 5)
- `cost_curve.png` — L3 cost-optimal threshold (Phase 5)
- `invocation_decay.png` — D1 rule-learning LLM invocation decline (Phase 8)

(Regenerate all of the above via `make bench`, `python -m eval.calibration`, `python -m
eval.cost_model`, and `python -m eval.rule_learning` respectively — none are committed to git,
per `.gitignore`'s `eval/output/*` rule; they are reproducible from source, not stored artifacts.)
"""

HTML_TEMPLATE = """\
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>LedgerGuard Benchmark Report</title>
<style>
body { font-family: -apple-system, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
h1, h2 { border-bottom: 1px solid #ddd; padding-bottom: 0.3rem; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: 0.9rem; }
th, td { border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: right; }
th:first-child, td:first-child { text-align: left; }
blockquote { background: #f5f5f5; border-left: 4px solid #888; padding: 0.5rem 1rem; margin: 1rem 0; }
.band-HEADLINE { border-left-color: #2a7d2a; }
.band-MODEST { border-left-color: #b8860b; }
.band-NEGATIVE { border-left-color: #a33; }
img { max-width: 100%; margin: 0.5rem 0; }
</style>
</head>
<body>
<h1>LedgerGuard — Benchmark Report</h1>
<p>Generated from a single <code>make bench</code> run against <code>{{ data_dir }}</code>
(split: <code>{{ split }}</code>). Every number below traces to
<code>eval/output/ablation.json</code>; nothing here is hand-edited.</p>

<h2>Pre-registered ablation (see <code>PREREGISTRATION.md</code>)</h2>
<table>
<tr><th>Stratum</th><th>n</th><th>Rules-only F1</th><th>Hybrid F1</th><th>LLM-only F1</th><th>LLM calls</th><th>₹/1,000</th></tr>
{%- for row in ablation_rows %}
<tr><td>{{ row.stratum }}</td><td>{{ row.n }}</td><td>{{ "%.3f"|format(row.rules_f1) }}</td><td>{{ "%.3f"|format(row.hybrid_f1) }}</td><td>{{ "%.3f"|format(row.llm_f1) }}</td><td>{{ row.llm_calls }}</td><td>{{ "%.2f"|format(row.cost) }}</td></tr>
{%- endfor %}
</table>

<p><strong>Δ (HARD+ADVERSARIAL) = {{ "%.3f"|format(decision.delta_hard_adversarial) }}</strong> — band: <strong>{{ decision.band }}</strong></p>
<blockquote class="band-{{ decision.band }}">{{ decision.verdict }}</blockquote>
<p><strong>Δ (EASY) = {{ "%.3f"|format(decision.delta_easy) }}</strong>{% if decision.easy_gap_flagged %} — <strong>flagged</strong>: materially different from the pre-registered Δ≈0 expectation; see <code>BROKE.md</code>.{% endif %}</p>

<h2>Operational metrics (full shipped pipeline, per stratum)</h2>
<table>
<tr><th>Stratum</th><th>n</th><th>Auto-match %</th><th>Precision (auto-posted)</th><th>Recall</th><th>F1</th><th>False auto-match %</th><th>Exception-queue precision</th><th>LLM calls</th><th>₹/1,000</th></tr>
{%- for row in metrics_rows %}
<tr><td>{{ row.stratum }}</td><td>{{ row.n }}</td><td>{{ "%.1f"|format(row.auto_match_rate * 100) }}%</td><td>{{ "%.1f"|format(row.precision_auto_posted * 100) }}%</td><td>{{ "%.1f"|format(row.recall * 100) }}%</td><td>{{ "%.2f"|format(row.f1) }}</td><td>{{ "%.1f"|format(row.false_auto_match_rate * 100) }}%</td><td>{{ "%.1f"|format(row.exception_queue_precision * 100) }}%</td><td>{{ row.llm_call_count }}</td><td>{{ "%.2f"|format(row.cost_per_1000_inr) }}</td></tr>
{%- endfor %}
</table>

<h2>Charts</h2>
<img src="eval/output/reliability_diagram.png" alt="L3 reliability diagram">
<img src="eval/output/cost_curve.png" alt="L3 cost curve">
<img src="eval/output/invocation_decay.png" alt="D1 invocation decay">
<p><em>Regenerate via <code>make bench</code>, <code>python -m eval.calibration</code>,
<code>python -m eval.cost_model</code>, and <code>python -m eval.rule_learning</code> -- none are
committed to git (<code>.gitignore</code>'s <code>eval/output/*</code> rule); they are
reproducible from source, not stored artifacts.</em></p>
</body>
</html>
"""


def _ablation_rows(table: dict) -> list[dict]:
    rows = []
    for stratum in (*STRATA, "Overall"):
        r, h, l = table["rules_only"][stratum], table["hybrid"][stratum], table["llm_only"][stratum]
        rows.append(
            {
                "stratum": stratum,
                "n": h["n"],
                "rules_f1": r["f1"],
                "hybrid_f1": h["f1"],
                "llm_f1": l["f1"],
                "llm_calls": h["llm_calls"],
                "cost": h["cost_inr_per_1000"],
            }
        )
    return rows


def _metrics_rows(metrics: dict) -> list[dict]:
    rows = []
    for stratum in (*STRATA, "Overall"):
        m = metrics[stratum]
        rows.append(
            {
                "stratum": stratum,
                "n": m.n,
                "auto_match_rate": m.auto_match_rate,
                "precision_auto_posted": m.precision_auto_posted,
                "recall": m.recall,
                "f1": m.f1,
                "false_auto_match_rate": m.false_auto_match_rate,
                "exception_queue_precision": m.exception_queue_precision,
                "llm_call_count": m.llm_call_count,
                "cost_per_1000_inr": m.cost_per_1000_inr,
            }
        )
    return rows


def render_report(data_dir: Path, split: str, out_dir: Path) -> tuple[Path, Path]:
    table = run_ablation(data_dir, split=split)
    decision = apply_decision_rule(table)
    metrics = run_full_pipeline_metrics(data_dir, split=split)

    context = {
        "data_dir": str(data_dir),
        "split": split,
        "ablation_rows": _ablation_rows(table),
        "decision": decision,
        "metrics_rows": _metrics_rows(metrics),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "report.md"
    html_path = out_dir / "report.html"

    md_path.write_text(Template(MD_TEMPLATE).render(**context), encoding="utf-8")
    html_path.write_text(Template(HTML_TEMPLATE).render(**context), encoding="utf-8")
    return md_path, html_path


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Render report.md + report.html from a make bench run.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--split", default="holdout")
    parser.add_argument("--out-dir", type=Path, default=Path("."))
    args = parser.parse_args()

    data_dir = args.data_dir
    if not (data_dir / "bank_statement.csv").exists():
        data_dir = Path("data/samples")

    md_path, html_path = render_report(data_dir, args.split, args.out_dir)
    print(f"report written to {md_path} and {html_path}")


if __name__ == "__main__":
    main()
