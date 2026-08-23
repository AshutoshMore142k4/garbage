# LedgerGuard — Benchmark Report

Generated from a single `make bench` run against `data/samples` (split: `holdout`). Every
number below traces to `eval/output/ablation.json`; nothing here is hand-edited.

## Pre-registered ablation (see `PREREGISTRATION.md`)

| Stratum | n | Rules-only F1 | Hybrid F1 | LLM-only F1 | LLM calls | ₹/1,000 |
|---|---|---|---|---|---|---|
| EASY | 49 | 1.000 | 1.000 | 0.000 | 0 | 0.00 |
| MEDIUM | 2 | 1.000 | 1.000 | 0.000 | 0 | 0.00 |
| HARD | 4 | 0.000 | 0.000 | 0.000 | 4 | 2384.49 |
| ADVERSARIAL | 5 | 0.667 | 0.667 | 0.000 | 0 | 0.00 |
| Overall | 60 | 0.964 | 0.964 | 0.000 | 4 | 158.97 |

**Δ (HARD+ADVERSARIAL) = 0.000** — band: **NEGATIVE**

> Delta = 0.000 < 0.03: the LLM is not justified on this holdout. Reported as a negative result, per PREREGISTRATION.md -- the deterministic layer does the work here.

**Δ (EASY) = 0.000**

## Operational metrics (full shipped pipeline, per stratum)

| Stratum | n | Auto-match % | Precision (auto-posted) | Recall | F1 | False auto-match % | Exception-queue precision | LLM calls | ₹/1,000 |
|---|---|---|---|---|---|---|---|---|---|
| EASY | 49 | 85.7% | 100.0% | 100.0% | 1.00 | 0.0% | 0.0% | 0 | 0.00 |
| MEDIUM | 2 | 0.0% | 0.0% | 100.0% | 1.00 | 0.0% | 0.0% | 0 | 0.00 |
| HARD | 4 | 0.0% | 0.0% | 0.0% | 0.00 | 0.0% | 25.0% | 4 | 2384.49 |
| ADVERSARIAL | 5 | 60.0% | 60.0% | 75.0% | 0.67 | 0.0% | 0.0% | 0 | 0.00 |
| Overall | 60 | 75.0% | 96.4% | 96.4% | 0.96 | 0.0% | 9.1% | 4 | 158.97 |

## Charts

- `reliability_diagram.png` — L3 calibration (Phase 5)
- `cost_curve.png` — L3 cost-optimal threshold (Phase 5)
- `invocation_decay.png` — D1 rule-learning LLM invocation decline (Phase 8)

(Regenerate all of the above via `make bench`, `python -m eval.calibration`, `python -m
eval.cost_model`, and `python -m eval.rule_learning` respectively — none are committed to git,
per `.gitignore`'s `eval/output/*` rule; they are reproducible from source, not stored artifacts.)