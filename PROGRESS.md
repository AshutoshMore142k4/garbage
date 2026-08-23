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

Status: **NOT STARTED**

## Phase 5 — L3 Calibration + Abstention Gate

Status: **NOT STARTED**

## Phase 6 — L4 Anomaly + L5 Executor + Audit

Status: **NOT STARTED**

## Phase 7 — D2 Red Team

Status: **NOT STARTED**

## Phase 8 — D1 Rule Learning

Status: **NOT STARTED**

## Phase 9 — Ablation, Report, README

Status: **NOT STARTED**

## Phase 10 — Demo & Submission

Status: **NOT STARTED**
