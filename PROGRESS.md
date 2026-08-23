# PROGRESS.md

Updated by Claude Code at the end of each phase. See `phases.md` for full task/acceptance detail.

## Phase 0 — Verification & Skeleton

Status: **DONE** (2026-08-22)

- [x] `docs/razorpay-verification.md` answers R1 with a definitive yes/no and doc sources.
      **R1 answer: NO** — test mode is not expected to produce real settlement records; this is
      based on documentation/community-consensus research, not a live experiment (no Razorpay
      credentials were available to this session — see the doc's honesty caveat). Settlement leg
      will be synthesized in Phase 2 per `plan.md`'s own pre-planned mitigation.
- [x] `make test` passes locally (`test_smoke.py`).
- [x] CI green — confirmed on PR #1 (GitHub Actions `test` job passed on commit `cd00f90`).
- [x] No secret committed (`.env.example` has placeholders only; `.env` is gitignored).

Repo structure scaffolded per `plan.md` §14: all top-level directories, `pyproject.toml`, `Makefile`
(stub targets: `setup ingest gen close bench redteam demo test` — only `setup`/`test` do real work
yet), `.env.example`, `.gitignore`, `Dockerfile`, CI workflow.

**Note for the next session:** `CLAUDE.md` (conventions, chaos-case list, audit-line schema,
non-negotiables) is referenced throughout `plan.md`/`phases.md` as required reading but was not
supplied to this session and does not exist in this repo yet. It should be authored (by the user,
or a future session working from explicit instructions) before Phase 2, since Phase 2's chaos-case
generation and Phase 6's audit schema depend on it. This session did not fabricate it.

## Phase 1 — Foundation

Status: **DONE** (2026-08-22)

- [x] `uvicorn ledgerguard.api.app:app` starts; `GET /healthz` returns 200 with
      `{ok, version, budget_spent_usd}` (verified both via `TestClient` in `tests/test_api.py`
      and by actually running uvicorn and curling it).
- [x] Database file created with all 9 tables from `plan.md` §15 and the
      `idempotency_key UNIQUE` constraint present and enforced (`tests/test_db.py`).
- [x] `make test` passes (12 tests: smoke, config x2, audit writer x2, db x2, api x1, plus
      Phase 0's smoke test); CI to be confirmed green on push.
- [x] `docs/adr/001-single-ai-component.md` written, with a concrete two-part revisit condition.
- [x] `REAL_VS_SIMULATED.md` written; every source labelled; Settlements marked **SIMULATED**,
      consistent with the Phase 0 R1 finding (and its own caveat that R1 itself was not
      empirically confirmed with live credentials).

**Deviation from `phases.md`'s literal task list, flagged explicitly:** `audit/writer.py`'s
schema was supposed to follow `CLAUDE.md`, which does not exist (see Phase 0 note below). Instead
the audit line is defined as the `MatchDecision` Pydantic model (`models.py`), which already
carries every field `plan.md` §15/§19 require. If `CLAUDE.md` is written later with a conflicting
schema, `audit/writer.py` and `models.py` need to be reconciled against it.

New dependency: `pydantic-settings` (added to `pyproject.toml`) — needed for typed,
env-var-driven `Settings` per `plan.md` §13's already-chosen Pydantic v2 stack; it's the
standard companion package since `BaseSettings` moved out of `pydantic` core in v2.

## Phase 2 — Data + Ground Truth

Status: **DONE** (2026-08-23)

- [x] Byte-identical regeneration proven by test (`tests/test_generator.py::test_generation_is_byte_identical_for_same_seed`).
- [x] All 10 chaos categories present, each ≥5 instances, counted in a printed summary
      (`make gen` prints per-category counts; also written to `chaos_manifest.json`).
- [x] Holdout contains the duplicate-UTR-vs-genuine-double-settlement matched pair (plan.md J4,
      the demo climax): same amount, same value_date, near-identical (one-character-different)
      narration, both forced into the holdout split.
- [x] Sample dataset committed at `data/samples/` (300 bank lines, 160KB, well under 1MB).
- [x] `make test` passes (24 tests); CI to be confirmed on push.

**Two gaps flagged explicitly, consistent with this repo's running honesty pattern (Phase 0/1):**

1. **Chaos-case taxonomy is not from `CLAUDE.md`.** `CLAUDE.md` still does not exist (flagged
   since Phase 0). `data/generator.py`'s 10-category taxonomy (`EASY_EXACT_MATCH`,
   `SPLIT_SETTLEMENT`, `LATE_REFUND`, `FEE_TAX_VARIANT`, `DATE_SKEW_BOUNDARY`,
   `TRUNCATED_NARRATION`, `NO_MATCH_EXISTS`, `AMBIGUOUS_MULTI_CANDIDATE`, `DUPLICATE_UTR`,
   `GENUINE_DOUBLE_SETTLEMENT`) is instead derived directly from cases `plan.md` itself names
   (§2, §8 J2/J4, §12). See the module docstring for the full rationale. Reconcile against
   `CLAUDE.md` if it is authored later with a different or additional list.
2. **`razorpay/ingest.py` has not been run against a live account.** No credentials and no
   network egress to razorpay.com were available in this session (same constraint as Phase 0).
   The module is written and unit-tested against a fake client, but "creates N real test orders"
   is unverified against the real API. Order creation is pure server-side API and should work
   as written; getting to a *captured* payment in test mode requires completing checkout with a
   test card, which this module cannot itself automate (documented in its own docstring) — that
   is a discovered constraint of Razorpay's test mode, not an oversight.
3. Settlements remain **SIMULATED** in every generated record, per the Phase 0 R1 finding —
   `data/generator.py` always synthesizes settlements regardless of whether the order/payment
   side came from a real ingest run or the built-in synthetic fixture.

New dependency: none (Phase 2 uses only what Phase 0/1 already added).

## Phase 3 — L0 + L1 Deterministic Matcher

Status: **DONE** (2026-08-23)

- [x] Rules-only accuracy measured on **validation** (not holdout) and printed by
      `python -m ledgerguard.l1_deterministic.matcher --data-dir <dir>`.
      At default full scale (seed=42, 3,000 bank lines): **validation resolved 596/600 (99.3%),
      precision among resolved 99.8%.** On the smaller committed `data/samples/` (300 lines):
      validation resolved 58/60 (96.7%), precision 96.6%. Both clear the ≥85% bar with margin.
- [x] Residual set written to disk (`residual.jsonl`) with the reason each record was unresolved
      (`NO_CANDIDATE_FOUND`, `AMOUNT_GAP_EXCEEDS_TOLERANCE`, `AMBIGUOUS_NARRATION_MULTI_CANDIDATE`,
      or `SUBSET_SUM_OVER_BUDGET` — all four are exercised by tests).
- [x] No network call occurs in L0/L1 (`tests/test_l1_no_network.py` patches `socket.socket.connect`
      to raise and runs the full pipeline against `data/samples/`).
- [x] `make test` passes (48 tests).

**A real bug caught and fixed before committing:** the first implementation added a fourth rule,
`rule_exact_utr_duplicate`, to resolve DUPLICATE_UTR's "reporting artifact" bank line by treating
whichever line sorted first *alphabetically by bank-line id* as "the original." That's wrong on
two counts, found by diagnosing an unexpectedly low precision number rather than accepting a
passing test suite as sufficient: (1) alphabetical id order has no relationship to which credit
is real, and for this project's own id-naming scheme it actually picked the fake one as
"original" more often than not; (2) re-reading `phases.md` Phase 6 more carefully, duplicate-UTR
detection is explicitly assigned to **L4 anomaly detection** ("L4 has veto power over L1"), not
to L1 — so this rule was also scope-misplaced. It has been removed; see the module docstring in
`src/ledgerguard/l1_deterministic/rules/__init__.py` and `BROKE.md` for the full account.

**Known, intentional gaps, flagged rather than hidden:**

1. **"Exact UTR" (one of plan.md §9's four named L1 rules) is not implemented.** As a
   *positive*-matching rule it has no data to run on: the internal ledger carries no UTR field
   (real Razorpay payments don't have one; only settlements do), and no UTR→order-group registry
   exists yet (that only starts to exist once D1's learned rules are promoted, Phase 8). As a
   *duplicate-detection* rule, it belongs to L4 (see the bug above). Fee/tax-adjusted amount
   matching, the T+2 date-tolerance band, bounded subset-sum for split settlements, and
   rapidfuzz-based narration plausibility scoring are all implemented and tested.
2. **DUPLICATE_UTR's "duplicate" bank line is currently matched incorrectly.** Without L4
   (Phase 6) to veto it, L1 alone matches both the real and the fake credit to the same order,
   since it has no way yet to know only one of them is genuine. This is the single known source
   of L1's residual precision gap and is expected to close once L4 exists — not something to
   patch around at L1.
3. **Chaos categories use a fixed count, not a proportion of the dataset size.**
   `data/generator.py`'s `chaos_min_count` (default 8) doesn't scale with `total_bank_lines`, so
   the chaos share of the dataset shrinks as size grows (e.g. ~18% chaos at 300 lines vs. ~3% at
   3,000). This is why the full-scale resolution rate (99.2%) is noticeably higher than the
   samples-scale one (94.7%) — it isn't L1 getting better, it's chaos becoming a smaller fraction
   of the total. Worth revisiting before Phase 9's ablation, where the residual's difficulty
   composition matters more than its raw size.

New dependency: none (`rapidfuzz` was already added in Phase 0's tech-stack pyproject.toml).

## Phase 4 — L2 LLM Triage

Status: **DONE** (2026-08-23)

- [x] L2 processes only the residual set — `tests/test_l2_never_sees_resolved.py` proves the
      residual file's bank-line-id set is exactly L1's unresolved set, disjoint from resolved.
- [x] All required adversarial-response tests pass (`tests/test_schema_failure_abstains.py`):
      malformed JSON, empty/truncated response, out-of-set candidate id, injected instruction in
      narration, and (added, since it's a real current-model outcome) a safety-classifier
      refusal — every one produces `candidate_id: None` / abstained, none crash, none "match."
      Two positive controls (valid response; malformed-then-valid-on-retry) confirm the retry
      path isn't just always failing closed.
- [x] Second run of the same batch makes zero API calls — `tests/test_l2_cache.py` swaps in a
      client that raises on any call and proves the cache hit skips it entirely.
- [x] Spend is printed at the end of a run and visible at `/healthz` —
      `l2_llm_triage/run.py` prints a summary and persists `data/cache/l2/last_run_spend.json`;
      `api/app.py`'s `/healthz` now reads that file instead of a hardcoded zero.
- [x] `make test` passes (69 tests).

**Two deviations from plan.md's literal L2 spec, made because verified current Claude API
behavior doesn't support what was originally written, not by choice:**

1. **`temperature 0` is not available.** Current Claude models run adaptive thinking by default
   and reject sampling parameters while it's active; disabling thinking to regain temperature
   control has documented failure modes (stray `<thinking>`/tool-call-shaped text leaking into
   the visible response) that would undermine the schema-validation safety net this module
   depends on. `l2_llm_triage/client.py` instead uses a low `output_config.effort` and structured
   JSON output, and leans on the prompt-hash response **cache** — not live sampling — for
   cross-run reproducibility. This is not a new idea invented to paper over the gap: plan.md #20
   already frames the cache as something that "doubles as a reproducibility guarantee," so the
   mechanism the project actually needs was already the right one.
2. **Model defaults to `claude-opus-5`**, per current Anthropic guidance to never downgrade to a
   cheaper model preemptively — cost control is enforced by the budget guard aborting the run,
   not by picking a smaller model up front. `PRICE_PER_MTOK_USD` in `client.py` is a point-in-time
   snapshot flagged for re-verification before a large benchmark run, per plan.md #20's own
   instruction not to assume pricing from memory.

**Small necessary extension to Phase 3's (already-merged) output, not a rewrite:** L1's
`MatchOutcome` now carries `candidate_payment_ids` on every unresolved result, and
`matcher.write_residual()` enriches each residual line with the actual bounded candidate set
(payment_id/order_id/net_paise/captured_at, closest-by-date first, capped at 10) instead of just
a reason string. This is what makes "hand L2 the bounded candidate set L1 produced" (plan.md #11)
concretely possible — Phase 3's residual output alone didn't carry enough structure for L2 to
act on.

New dependency: `anthropic` (official SDK) — the one LLM call site plan.md #11 specifies.

## Phase 5 — L3 Calibration + Abstention Gate — NEVER CUT

Status: **DONE** (2026-08-23)

- [x] ECE reported on holdout with a reliability diagram saved to `eval/output/`:
      `python -m eval.calibration --data-dir data/samples` → raw-confidence ECE **0.0452**,
      calibrated ECE **0.0237** on the committed sample dataset (calibration measurably helps).
- [x] Cost curve plotted with the chosen threshold marked:
      `python -m eval.cost_model --data-dir data/samples` → cost-optimal threshold **0.92**
      (selected on validation only), plotted against the holdout cost curve.
- [x] Exception queue populated, ranked by ₹ at risk, every entry with evidence — built from the
      *actual* holdout decisions (not a synthetic example): on the sample dataset the two
      highest-value entries are, unprompted, the duplicate-UTR and genuine-double-settlement
      demo-pair bank lines from Phase 2 (`plan.md` §8 J4's cold open) — same amount, both
      correctly refused, for two different reason codes. This wasn't engineered; it's what the
      pipeline actually produces end to end.
- [x] Threshold value is derived from `cost_model.find_optimal_threshold`, never hardcoded.
- [x] `make test` passes (94 tests).

**Design decisions worth recording:**

- The calibrator is `sklearn.linear_model.LogisticRegression` fit on the full six-feature vector
  (`partial_rule_agreement_count`, `absolute_amount_gap_paise`, `date_skew_days`,
  `narration_similarity_score`, `candidate_set_size`, `model_self_rated_confidence`) — never on
  raw confidence alone, per phases.md's explicit instruction. Fit strictly on validation;
  holdout is only ever scored, never fit on.
- The cost model's two cost terms are **documented assumptions, not measured figures** — plan.md
  gives no real number for either: a false AUTO_POST costs the full misallocated amount
  (definitional, not assumed), while an ESCALATE costs a flat ₹50 analyst-review fee
  (`ESCALATION_COST_PAISE` in `cost_model.py`, explicitly flagged in its docstring as something
  to replace once real analyst-time data exists).
- `gate.py` reuses `AMBIGUOUS_NARRATION_MULTI_CANDIDATE` as the reason code for "a candidate was
  proposed but didn't clear the threshold," rather than inventing a new code — this exactly
  matches plan.md §8 J2's own worked example ("Calibrated confidence 0.62, threshold 0.94...
  Reason: `AMBIGUOUS_NARRATION_MULTI_CANDIDATE`").
- Because this repo still has no live Anthropic credentials (Phases 0/4), `decisions.py` builds
  L2's half of the training data using the **free fallback**, not a real model call. The
  calibrator only ever sees the feature vector, so this doesn't change what's being
  demonstrated — calibrating and gating over decisions with a real raw confidence — but it does
  mean L2's actual raw confidences in this dataset are the fallback's, not a live model's. This
  should be revisited once real credentials exist, to confirm the calibrator behaves the same
  way over live-model confidences.

New dependency: `matplotlib` — needed for the reliability diagram and cost-curve plots this
phase's acceptance criteria explicitly require.

## Phase 6 — L4 Anomaly + L5 Executor + Audit

Status: **DONE** (2026-08-23)

- [x] Rerun produces zero double-posts, proven by test: `tests/test_idempotency.py` runs
      `ledgerguard.close.run_close` on the same `batch_id` twice and asserts the audit file is
      **byte-identical** and `match_decisions` gains **zero new rows** the second time.
- [x] Authority policy enforced and unit-tested (`tests/test_authority_policy.py`): amounts over
      `AUTHORITY_LIMIT_PAISE` never auto-post even when the gate itself said AUTO_POST.
- [x] `audit.jsonl` line count equals total decision count: verified directly in
      `tests/test_idempotency.py`, and on the full sample dataset via `make close`
      (300 decisions → 300 audit lines).
- [x] Both twin cases (the Phase 2 demo pair) correctly refused with **distinct** reason codes:
      confirmed both as a unit test (`tests/test_anomaly_veto.py`) and by directly querying the
      DB after a real `make close` run — `DUPLICATE_UTR` / `FLAG_ANOMALY` for one line,
      `GENUINE_DOUBLE_SETTLEMENT` / `FLAG_ANOMALY` for the other, neither `AUTO_POST`.
  - `python -m ledgerguard.close` on the sample dataset: **198 AUTO_POST, 77 ESCALATE,
    25 FLAG_ANOMALY** (300 total, matching the decision count).
- [x] `make test` passes (116 tests).

**Two real, previously-undetected bugs in the already-merged Phase 2 generator, found and fixed
while building this phase's anomaly detectors** (not by inspection — by running `make close`
against the sample data and checking the demo pair's actual DB rows, since the acceptance
criterion is specifically about *that* pair):

1. The demo pair's bank lines had a **forced `value_date`** (so the duplicate-UTR and
   genuine-double-settlement scenarios could share an identical date, per the demo's own
   design) but the underlying order/payment's `captured_at` was left randomly drawn from
   `data/generator.py`'s normal 0-120-day range — completely decoupled from the forced date. For
   many seeds this puts `captured_at` *after* the bank line's `value_date`, making the demo pair
   structurally impossible for L1 to match at all, regardless of any Phase 6 logic.
2. After fixing (1) by forcing `captured_at` too, the pair still failed — `_make_order_payment`
   separately adds a random 1-30 minute offset on top of the forced value to produce the actual
   stored `captured_at`, which was enough on its own to push the gap under the T+2 tolerance
   floor by single-digit minutes.
   Full account of both, and the fix (a documented `DEMO_CAPTURED_AT` constant with an explicit
   safety margin), in `BROKE.md`.

**New anomaly reason codes**, extending `models.py`'s `ReasonCode` enum exactly as its Phase 5
comment anticipated: `DUPLICATE_UTR`, `GENUINE_DOUBLE_SETTLEMENT`, `MISSING_SETTLEMENT`,
`FEE_TAX_CONTRACT_VIOLATION`. All four detectors are implemented in `l4_anomaly/detectors.py`
and, on the real sample dataset, all four actually fire against the chaos categories built for
them in Phase 2 (duplicate-UTR pairs, genuine-double-settlement pairs, the never-settled
AMBIGUOUS_MULTI_CANDIDATE decoy orders, and the FEE_TAX_VARIANT alternate-fee-rate payments) —
not just against synthetic unit-test fixtures.

**`ledgerguard/close.py`** is the full L0→L5 pipeline (`make close`'s target, previously a stub
since Phase 0). It deliberately does **not** call `config.get_settings()` for
`authority_limit_paise`, since that would require the Razorpay/LLM secrets this repo has never
had in any session (Phases 0/4) just to read one non-secret numeric constant — it takes
`authority_limit_paise` as a parameter (defaulting to `.env.example`'s value) and only reaches
for real `Settings` opportunistically, falling back cleanly if unavailable, matching the pattern
already used in `l2_llm_triage/run.py`.

**Known, honest gap:** the fee/tax contract band (`FEE_RATE_BAND`, `TAX_RATE_ON_FEE_BAND` in
`detectors.py`) is a documented assumption centered on the generator's own nominal rate, not a
measured real-world merchant contract — flagged in the module docstring for whoever can supply
the real figures.

New dependency: none (this phase only uses what earlier phases already added).

## Phase 7 — D2 Red Team

Status: **DONE** (2026-08-23)

- [x] ≥50 adversarial cases across ≥4 attack categories: `data/redteam.py` generates 60 cases
      (15 each) across `NEAR_COLLISION_PAIR`, `PLAUSIBLE_WRONG_SUBSET_SUM`,
      `PROMPT_INJECTION_NARRATION`, `REFUND_TIMED_TO_LOOK_PERFECT` — asserted directly by
      `tests/test_redteam.py::test_at_least_50_cases_across_at_least_4_categories`.
- [x] Survival rate measured and reported separately from holdout metrics: `eval/redteam_eval.py`
      (`make redteam`) fits the calibrator/threshold on `data/samples`' own validation split
      (never on red-team data) and evaluates red-team decisions from an entirely separate
      directory it writes to a temp dir per run. Current measured result: **48/60 (80.0%)**
      overall survival — `NEAR_COLLISION_PAIR` 3/15, `PLAUSIBLE_WRONG_SUBSET_SUM` 15/15,
      `PROMPT_INJECTION_NARRATION` 15/15, `REFUND_TIMED_TO_LOOK_PERFECT` 15/15. Never touches
      `data/samples`' or `data/raw`'s own holdout split, confirmed by
      `tests/test_redteam.py::test_redteam_dataset_never_reuses_the_production_holdout_split`.
- [x] The injection case provably results in ABSTAIN: `PROMPT_INJECTION_NARRATION` pairs the
      injected narration with two payments of the exact same amount and *identical* `captured_at`
      — a structurally tied candidate set, not just a semantically ambiguous one. `fallback_triage`
      abstains outright whenever more than one candidate survives amount/date filtering,
      regardless of narration content, so this is a structural property of the bounded-candidate-
      set design, not an empirical hope that a model resists a clever prompt. Verified directly:
      `tests/test_redteam.py::test_injection_case_provably_abstains` (15/15, 100% survival).
- [x] Any attack that succeeds is written into `BROKE.md` and the fix is described: both findings
      below are logged there with full diagnosis.
- [x] `make test` passes (123 tests, 7 new).

**Two real findings, not hypothetical ones — both surfaced by actually running the red team
against the shipped pipeline and inspecting per-case results, not by trusting an aggregate
survival number:**

1. **Found and fixed:** `PLAUSIBLE_WRONG_SUBSET_SUM` broke `rule_subset_sum_split_settlement` on
   the very first run — L1 confidently (0.93 raw confidence) resolved to a decoy 2-payment group
   in all 15 cases instead of the true 3-payment group, because `subset_sum.find_subset`'s
   "first sum found" search had no check for whether a different, equally-valid group existed
   elsewhere in the same candidate pool. Fixed by searching the remaining pool for an alternate
   exact-sum group after the first is found, and escalating (`AMBIGUOUS_NARRATION_MULTI_CANDIDATE`)
   instead of guessing when one exists. Re-verified: `PLAUSIBLE_WRONG_SUBSET_SUM` now survives
   15/15, and L1's precision on `data/samples/` is unchanged (97.6% overall / 98.3% validation) —
   the fix only ever changes behavior when a genuine second exact-sum group exists, which doesn't
   happen by chance in production's continuous random amounts. Full diagnosis in `BROKE.md`.
2. **Found, honestly left unfixed:** `NEAR_COLLISION_PAIR` (a stray, unbacked bank credit whose
   amount+date coincidentally collides with an unrelated real payment) clears L1, L3's calibrated
   gate, and L4 (no detector covers "two different orders happen to share an amount") in 12/15
   cases (80% attack success). This is a structural limit of amount+date+narration matching with
   no independent per-order reference field in the ledger — not a bug with a code-level fix
   available in this data model. Documented in `BROKE.md` with the specific reasoning for why a
   heuristic patch would just move the trade-off around rather than close the gap, and what real
   signal (an order reference in the bank narration) would actually be needed.

**Scope decision:** L4 anomaly detection is intentionally excluded from `eval/redteam_eval.py`'s
own gate/authority evaluation (`has_anomaly` always `False`) — none of the four attack categories
targets duplicate-UTR/double-settlement/missing-settlement/fee-tax-band detection specifically,
and folding L4 in would blur which layer a given survival/failure result is actually exercising.
This does **not** mean L4 was ignored when deciding which attacks counted as genuine findings:
`NEAR_COLLISION_PAIR`'s design was checked against all four L4 detectors by reading
`l4_anomaly/detectors.py` directly to confirm none of them would catch it in the *real* `make
close` pipeline either — reporting an 80% attack success rate for a gap that L4 already closes in
production would have been dishonest.

**Reuses `data/generator.py`'s `GeneratedDataset`/`write_dataset` unchanged**: red-team entities
are ordinary `Order`/`Payment`/`BankLine`/`GroundTruth` objects written with the same CSV/JSON
shape, so `build_decision_dataset` consumes a red-team directory exactly like any other. Every
red-team case's `GroundTruth.split` is labeled `"holdout"` as a harmless placeholder —
`models.py`'s closed `Split` Literal has no `"redteam"` value, and nothing in this phase reads
red-team decisions by split (only by `bank_line_id`, against `RedTeamCase` records), so this
never risks contaminating a real holdout metric.

New dependency: none (this phase only uses what earlier phases already added).

## Phase 8 — D1 Rule Learning

Status: **NOT STARTED**

## Phase 9 — Ablation, Report, README

Status: **NOT STARTED**

## Phase 10 — Demo & Submission

Status: **NOT STARTED**
