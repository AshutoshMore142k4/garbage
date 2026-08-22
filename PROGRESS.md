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

Status: **NOT STARTED**

## Phase 3 — L0 + L1 Deterministic Matcher

Status: **NOT STARTED**

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
