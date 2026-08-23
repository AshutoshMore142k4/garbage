# PREREGISTRATION.md — the ablation's decision rule, committed before the holdout run

Per `plan.md` §24 and `phases.md` Phase 9: this file locks the ablation's analysis plan — what
gets measured, how the strata are defined, and what the verdict is allowed to say for each
possible outcome — **before `benchmark/ablation.py` is run against holdout for the first time.**
The commit that introduces this file, and its timestamp in `git log`, is the evidence that the
rule below was fixed in advance and not fitted to the numbers afterward.

Nothing in this file was chosen by looking at ablation results. The three strata, the metric, the
Δ thresholds, and the permitted language for each outcome band are transcribed verbatim from
`plan.md` §24.1/§24.2, written during this project's Phase 0/1 planning — long before any holdout
number existed to peek at.

-----

## 1. What is being tested

Whether L2 (the single LLM call site, currently served by the free rapidfuzz fallback in every
session so far — see `PROGRESS.md`/`BROKE.md` Phases 0/4/9 for why there has never been a live
Anthropic call in this environment) is **load-bearing**: does routing L1's residual through it
measurably improve match quality over rules alone, on the cases that are actually hard?

This is not a test of whether *a real Claude model* would do better than the fallback — this
environment has never had credentials to run that experiment (see `REAL_VS_SIMULATED.md`). It is
a test of whether *this system's current L2 path, whatever serves it*, earns its place over
just stopping at L1. That distinction is stated plainly in the README wherever this ablation's
numbers are quoted.

## 2. Stratified reporting (`plan.md` §24.1)

A single global F1 hides the only interesting question. Every ablation number is reported broken
out by the difficulty stratum `data/generator.py` (Phase 2) already assigns to every bank line in
`ground_truth.json` — EASY, MEDIUM, HARD, ADVERSARIAL — plus an overall row:

| Stratum     | n | Rules-only F1 | Hybrid F1 | **Δ** | LLM-only F1 | LLM calls | ₹ cost | p50 latency |
|-------------|---|---------------|-----------|-------|-------------|-----------|--------|-------------|
| EASY        |   |               |           |       |             |           |        |             |
| MEDIUM      |   |               |           |       |             |           |        |             |
| HARD        |   |               |           |       |             |           |        |             |
| ADVERSARIAL |   |               |           |       |             |           |        |             |
| **Overall** |   |               |           |       |             |           |        |             |

This table shape is fixed now. `benchmark/ablation.py` fills in every cell from a real holdout
run; no column is added or removed after seeing numbers.

**The three configs, defined now, before any is run:**

- **Rules-only**: L1's built-in deterministic rules only (`l1_deterministic/rules.BUILTIN_RULES`).
  A bank line L1 does not resolve counts as "no match predicted" for scoring purposes — L2 is not
  consulted at all.
- **Hybrid**: the full shipped pipeline — L1 first, L2 (fallback-served) triage on whatever L1
  leaves unresolved. This is what `l3_calibrate_gate.decisions.build_decision_dataset` already
  computes for every other phase's reporting.
- **LLM-only**: L1 is skipped entirely. Every bank line, including ones L1 would trivially
  resolve, gets the same bounded candidate window (`PaymentIndex.candidates_before`, unchanged)
  and is triaged directly by L2. This isolates what the model (or its fallback stand-in) can do
  unaided by deterministic pre-filtering.

**Metric**: precision/recall/F1 over exact-match correctness against `ground_truth.json`'s
`correct_match`, using the standard entity-matching convention: a wrong non-empty proposal counts
as both a false positive (the proposed match is wrong) and a false negative (the true match, if
one exists, was not found) — not scored as a "partial credit" case, and not merely folded into a
single accuracy number. A bank line ground truth marks as unmatchable (`correct_match: null`) on
which the system correctly proposes nothing is a true negative and does not enter precision or
recall, per the standard convention for retrieval-style F1.

## 3. The decision rule (`plan.md` §24.2) — binding

Let **Δ = Hybrid F1 − Rules-only F1**, computed on the **HARD + ADVERSARIAL** strata combined, on
**holdout only**.

| Outcome | Interpretation | What the README and pitch are allowed to claim |
|---|---|---|
| **Δ ≥ 0.08** | The LLM is load-bearing on ambiguous cases | Headline claim permitted: the hybrid architecture is justified by measurement |
| **0.03 ≤ Δ < 0.08** | Measurable but modest | Claim must be scoped to the named case class (e.g. "on truncated-narration cases only"). No general claim about AI. |
| **Δ < 0.03** | **The LLM is not justified.** | **Report it as a negative result.** Keep the abstention gate and the rules; state plainly that the deterministic layer does the work and the LLM was cut or confined. This becomes the story. |

**Prediction registered in advance:** on the **EASY** stratum, Δ ≈ 0 is expected. If the LLM
measurably helps on EASY, that is **not a win** — it means L1 is under-built, and the correct
response is to fix L1, not credit the model. If EASY-stratum Δ comes back materially above 0,
that gap gets filed in `BROKE.md` as an L1 deficiency, per `phases.md` Phase 9's acceptance
criterion, not folded quietly into a "the LLM helps" narrative.

**LLM-only is reported regardless of outcome**, including its own cost and latency, even if it
wins outright — a bad result for the deterministic-first thesis is still reported.

## 4. Holdout discipline (`plan.md` §24.3)

- No threshold, prompt version, rule, or calibrator may be changed **after** the holdout run in
  this phase.
- If something must change: **the holdout is burned.** A fresh holdout is generated with a new
  seed, the burn is documented in `BROKE.md` with the reason, and the ablation is re-run from
  scratch on the new holdout — never silently re-run on the same holdout hoping for a different
  number.
- Every number that lands in `README.md` traces to a single committed `make bench` invocation's
  output. No hand-edited number, no cherry-picked run.

## 5. What happens after the run, regardless of outcome

The verdict this file's rule produces gets written into `README.md` using **only** the language
its outcome band above permits — never stronger, never hedged into sounding stronger than the
band allows. A `Δ < 0.03` result is not a failure of this project: `plan.md` §25 (R2) and
`phases.md` Phase 9 both call a negative result here "a valid, reportable outcome," and it is
scored as a direct hit on Razorpay's own "AI judgment — the right tool in the right place, and
where you chose NOT to use one" criterion, not as a shortfall.

-----

*Committed before the first holdout ablation run, per phases.md Phase 9 task 1. See `git log` for
this file's own commit, which precedes `benchmark/ablation.py`'s first execution against
holdout.*
