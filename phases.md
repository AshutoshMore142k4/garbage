# phases.md — LedgerGuard Execution Roadmap

## How Claude Code must use this file

At the start of every session:

1. Read `plan.md` (architecture and constraints — the source of truth)
1. Read `CLAUDE.md` (conventions and non-negotiables)
1. Read this file and `PROGRESS.md`
1. Identify the **first phase whose Definition of Done is not met**
1. Implement **only that phase**
1. Run `make test`
1. Verify every acceptance criterion explicitly, one by one
1. Fix failures
1. Update `PROGRESS.md` and append to `BROKE.md` if anything broke
1. **Stop and wait for the next instruction**

**Hard rules:**

- Do not implement future phases, even if they seem trivial.
- Do not change architecture decisions in `plan.md`. If a decision looks wrong, **say so and stop** —
  do not unilaterally refactor.
- Do not add a dependency without a one-line justification in the commit message.
- Every phase ends with a working, committed, test-passing artifact.
- Never write a number into `README.md` that was not produced by `make bench`.

**Calendar (13 days, Aug 23 → submit Sep 3, buffer Sep 4–5):**

|Phase                             |Days     |Cuttable?                |
|----------------------------------|---------|-------------------------|
|0 Verification & skeleton         |Aug 23   |No                       |
|1 Foundation                      |Aug 23   |No                       |
|2 Data + ground truth             |Aug 24–25|No                       |
|3 L1 deterministic                |Aug 26–27|No                       |
|4 L2 LLM triage                   |Aug 28   |No                       |
|5 L3 calibration + gate           |Aug 29   |**Never cut**            |
|6 L4 anomaly + L5 executor + audit|Aug 30   |L4 cuttable, L5/audit not|
|7 D2 red team                     |Aug 31   |Cut 2nd                  |
|8 D1 rule learning                |Sep 1    |Cut 1st                  |
|9 Ablation + report + README      |Sep 2    |**Never cut**            |
|10 Demo + submission              |Sep 3    |No                       |

**Cut order if behind: D1 → D2 → L4.** Never cut calibration, ablation, audit log, or the
idempotency test — those four carry the entire thesis.

-----

## Phase 0 — Verification & Skeleton

**Goal:** Establish what is actually true about Razorpay test mode before any code depends on it, and
stand up an empty but CI-green repository.

**Tasks**

1. Verify against **current official Razorpay documentation**: Orders API, Payments API, Refunds API,
   Settlements API, webhook signature scheme, test-mode key format, rate limits.
1. **Answer R1 explicitly: does Razorpay test mode return settlement records with UTRs?** Create a
   handful of test orders, capture payments, and query settlements. Record the literal answer.
1. Record all findings in `docs/razorpay-verification.md` with the doc URL and the date checked.
1. Scaffold the repo structure from `plan.md` §14 — directories, `pyproject.toml`, `Makefile` with
   stub targets, `.env.example`, `.gitignore`, `Dockerfile`, CI workflow, `PROGRESS.md`, `BROKE.md`.

**Files:** `docs/razorpay-verification.md`, `pyproject.toml`, `Makefile`, `.env.example`,
`.gitignore`, `Dockerfile`, `.github/workflows/ci.yml`, `PROGRESS.md`, `BROKE.md`,
`src/ledgerguard/__init__.py`, `tests/test_smoke.py`

**Implementation details**

- `.gitignore` must cover `.env`, `*.db`, `__pycache__`, `data/raw/`
- CI: install, `pytest`, on push and PR
- `Makefile` targets (stubs for now): `setup ingest gen close bench redteam demo test`

**Tests:** `test_smoke.py` imports the package and asserts version is a string.

**Acceptance criteria**

- [ ] `docs/razorpay-verification.md` answers R1 with a definitive yes/no and a doc URL
- [ ] `make test` passes locally
- [ ] CI is green on the first push
- [ ] No secret is committed

**Failure modes:** test-mode settlements unavailable → **this is an expected outcome, not a blocker**;
record it, and Phase 2 synthesizes the settlement leg from real payment data with an honest README note.

**Definition of done:** repo pushed, CI green, R1 answered in writing.

-----

## Phase 1 — Foundation

**Goal:** A running application with typed schemas, config, database, and audit writer.

**Tasks**

1. `config.py` — settings via env: `RAZORPAY_KEY_ID/SECRET`, `WEBHOOK_SECRET`, `LLM_API_KEY`,
   `MAX_SPEND_USD`, `SEED`, `CONFIDENCE_THRESHOLD`, `AUTHORITY_LIMIT_PAISE`
1. `models.py` — Pydantic models for every entity and every boundary in `plan.md` §15/§16
1. SQLite schema + migration script (`plan.md` §15 verbatim, including `idempotency_key UNIQUE`)
1. `audit/writer.py` — append-only JSONL writer, schema per `CLAUDE.md`
1. FastAPI app with `/healthz` returning `{ok, version, budget_spent_usd}`
1. **`docs/adr/001-single-ai-component.md`** — the architecture decision record for why LedgerGuard has
   **one** LLM call site rather than a multi-agent pipeline. Structure: Context → Decision → Rationale
   → Consequences → Revisit condition. The rationale must state the bar explicitly: *every additional
   agent must justify itself with a measured delta on a named case class; none currently can.* The
   revisit condition must be concrete (e.g. “revisit if the residual set splits into ≥2 case classes
   that need different reasoning and the stratified ablation shows a per-class gain”).
1. **`REAL_VS_SIMULATED.md`** — the honesty ledger. One table, one row per data source:

   |Source                     |Status           |How produced               |What this means for the metrics              |
   |---------------------------|-----------------|---------------------------|---------------------------------------------|
   |Orders / Payments / Refunds|REAL             |Razorpay test-mode API     |real IDs, amounts, fee/tax fields            |
   |Settlements                |REAL or SIMULATED|per Phase 0 finding (R1)   |if simulated, say so and say how             |
   |Bank statement             |SYNTHETIC        |seeded generator           |narration mangling is modelled, not observed |
   |Internal ledger            |SYNTHETIC        |derived from real orders   |                                             |
   |Ground truth labels        |SYNTHETIC        |generator knows the answer |metrics are exact but distribution is ours   |
   |Red-team cases             |SYNTHETIC        |adversarial by construction|survival rate is not a real-world attack rate|

**Files:** `src/ledgerguard/config.py`, `models.py`, `db.py`, `audit/writer.py`, `api/app.py`,
`docs/adr/001-single-ai-component.md`, `REAL_VS_SIMULATED.md`,
`tests/test_config.py`, `tests/test_audit_writer.py`

**Implementation details**

- All money is **integer paise**. No floats anywhere in money paths. Add a lint check if practical.
- All timestamps stored as ISO-8601 UTC strings.
- The audit writer opens in append mode only and never rewrites or truncates.

**Tests**

- Config loads from env with sane defaults; missing required secret raises clearly
- Audit writer appends; two writes produce two lines; existing content is never modified
- `/healthz` returns 200

**Acceptance criteria**

- [ ] `uvicorn` starts; `/healthz` returns 200
- [ ] Database file created with all tables and the UNIQUE constraint present
- [ ] `make test` passes; CI green
- [ ] `docs/adr/001-single-ai-component.md` written with a concrete revisit condition
- [ ] `REAL_VS_SIMULATED.md` written; every source labelled; the Settlements row reflects the actual
  Phase 0 finding, not an assumption

**Failure modes:** float money creeping in — catch it now, not in Phase 6.

**Definition of done:** app runs, DB initialized, audit writer tested.

-----

## Phase 2 — Data + Ground Truth

**Goal:** The benchmark. This phase *is* the project’s credibility — do not rush it.

**Tasks**

1. `razorpay/ingest.py` — create N test orders, capture payments, create partial refunds; persist raw
   JSON to `data/raw/`
1. `data/generator.py` — seeded, **difficulty-stratified** generator producing the bank statement and
   internal ledger, plus `ground_truth.json`
1. Implement **every** chaos case from `CLAUDE.md` §Chaos
1. Split 60/20/20 by seed into train / validation / **holdout**
1. Commit a small sample dataset to `data/samples/` so the repo runs with no API keys

**Files:** `src/ledgerguard/razorpay/client.py`, `razorpay/ingest.py`, `data/generator.py`,
`data/samples/*`, `tests/test_generator.py`

**Implementation details**

- Target ~3,000 records total
- Difficulty labels on every record: `EASY | MEDIUM | HARD | ADVERSARIAL`, stored in `ground_truth`
- **Every record must have exactly one correct answer in ground truth**, including “no match exists”
- Split settlements: group sizes drawn from a realistic distribution, not uniform
- **The duplicate-UTR case and the genuine-double-settlement case must be generated as a matched
  pair** that is visually near-identical — this is the demo climax and must exist in holdout
- Generator must be pure given a seed: no wall-clock, no `random` without the seeded instance

**Tests**

- `make gen SEED=42` run twice → **byte-identical** output files
- Every chaos case from `CLAUDE.md` appears at least 5 times in the generated set
- Ground truth covers 100% of bank lines
- Split proportions are correct and **disjoint**

**Acceptance criteria**

- [ ] Byte-identical regeneration proven by test
- [ ] All chaos categories present and counted in a printed summary
- [ ] Holdout contains at least one duplicate-vs-double-settlement pair
- [ ] Sample dataset committed and small (<1 MB)

**Failure modes:** a generator that is subtly too easy (everything matches on UTR) → assert a minimum
count of records where no exact UTR match exists.

**Definition of done:** `make gen` reproducible, ground truth complete, sample committed.

-----

## Phase 3 — L0 + L1 Deterministic Matcher

**Goal:** Resolve the large majority with **zero AI**.

**Tasks**

1. `l0_normalize/` — paise integers, UTC timestamps, narration cleanup (uppercase, strip known
   prefixes, collapse whitespace)
1. `l1_deterministic/rules/` — a **rule registry**: each rule is an object with `rule_id`, a predicate,
   and a confidence contribution. This registry is what D1 will later write into.
1. Rules: exact UTR; amount + date-tolerance band (T+2 window); fee/tax-adjusted amount matching;
   narration prefix/substring matching via `rapidfuzz`
1. `subset_sum.py` — **bounded** subset-sum for split settlements (cap group size and search width;
   over-cap → escalate by design, never hang)
1. Emit the residual set to disk for L2

**Files:** `src/ledgerguard/l0_normalize/*`, `l1_deterministic/*`, `tests/test_l1_rules.py`,
`tests/test_subset_sum.py`

**Implementation details**

- Rules are **ordered and each records which rule fired** — required for the audit trail
- Subset-sum is bounded by `MAX_GROUP_SIZE` and a node budget; exceeding either returns “unresolved”
- No rule may consult the LLM. No network calls in this layer.

**Tests**

- Each rule unit-tested with a positive and a negative case
- Subset-sum: correct on known groups; terminates within budget on a pathological input
- Tolerance bands: boundary cases at exactly ±tolerance

**Acceptance criteria**

- [ ] Rules-only accuracy measured on **validation** (not holdout) and printed
- [ ] Residual set written to disk with the reason each record was unresolved
- [ ] Rules-only resolves ≥85% of validation, **or** the shortfall is explained in `BROKE.md`
- [ ] No network call occurs in this layer (assert in test)

**Failure modes:** subset-sum blowing up combinatorially → the node budget exists for this.

**Definition of done:** measured rules-only baseline recorded in `PROGRESS.md`.

-----

## Phase 4 — L2 LLM Triage (residual only)

**Goal:** Add the model to the ~8–15% that determinism could not resolve, safely and cheaply.

**Tasks**

1. `l2_llm_triage/client.py` — single interface, temperature 0, hard per-call token cap
1. `prompts/` — versioned prompt files, content-hashed; the hash goes in the audit line
1. Pydantic-validated response: `{candidate_id | null, confidence, evidence[]}`
1. `cache.py` — prompt-hash keyed response cache, committed to `data/cache/`
1. `budget_guard.py` — running spend counter, hard cap, **abort loudly** on breach
1. `fallback.py` — `rapidfuzz` scorer used when budget trips or the API is unavailable

**Files:** `src/ledgerguard/l2_llm_triage/*`, `prompts/residual_triage_v1.md`,
`tests/test_schema_failure_abstains.py`, `tests/test_budget_guard.py`,
`tests/test_l2_never_sees_resolved.py`

**Implementation details**

- The model receives **one unresolved bank line + the bounded candidate set L1 produced** — never the
  full dataset
- Narration is passed as **clearly delimited data**, never as instruction text
- The model may only return a candidate ID **from the provided set**, or null. An ID outside the set is
  a validation failure → abstain.
- Schema failure → retry once → **abstain**. Never guess, never crash.
- Cache is checked before every call, so re-running the benchmark costs ₹0

**Tests**

- **`test_l2_never_sees_resolved.py`** — the core invariant; assert no L1-resolved ID ever enters an L2 prompt
- Malformed JSON, truncated response, empty response, out-of-set candidate ID, injected instruction in
  narration → **all produce ABSTAIN**, none crash, none post
- Budget guard aborts at the cap and does not silently continue
- Cache hit produces zero API calls

**Acceptance criteria**

- [ ] L2 processes only the residual set
- [ ] All six adversarial response tests pass
- [ ] Second run of the same batch makes zero API calls (cache proven)
- [ ] Spend printed at end of run and visible at `/healthz`

**Failure modes:** model returns confident nonsense → that is Phase 5’s job, not a reason to prompt-engineer forever.

**Definition of done:** LLM resolves part of the residual; malformed output provably harmless.

-----

## Phase 5 — L3 Calibration + Abstention Gate — NEVER CUT

**Goal:** Turn raw confidence into a trustworthy, cost-optimal decision.

**Tasks**

1. Feature extraction per decision: partial-rule-agreement count, absolute amount gap (paise), date
   skew (days), narration similarity score, candidate-set size, model self-rated confidence
1. `calibrator.py` — logistic or isotonic, **fit on validation labels only**
1. `cost_model.py` — expected ₹ cost as a function of threshold (see `CLAUDE.md`)
1. `gate.py` — threshold **selected by minimizing expected cost**, not by maximizing accuracy
1. `exception_queue.py` — reason codes, evidence, ranked by ₹ at risk
1. Emit ECE + reliability diagram on **holdout**

**Files:** `src/ledgerguard/l3_calibrate_gate/*`, `eval/calibration.py`, `eval/cost_model.py`,
`tests/test_calibration.py`, `tests/test_gate.py`

**Implementation details**

- **Do not calibrate on raw LLM token probabilities.** Fit on the feature vector above; the model’s
  self-rating is one feature among many, never the answer.
- Fit on validation. Report on holdout. Never fit on holdout.
- Reason codes are a closed enum — e.g. `AMBIGUOUS_NARRATION_MULTI_CANDIDATE`,
  `SUBSET_SUM_OVER_BUDGET`, `AMOUNT_GAP_EXCEEDS_TOLERANCE`, `NO_CANDIDATE_FOUND`,
  `SCHEMA_VALIDATION_FAILED`, `BUDGET_EXHAUSTED`

**Tests**

- Calibrator improves ECE versus raw confidence (assert numerically)
- Cost model returns a minimum at a threshold strictly inside (0,1)
- Gate never passes a decision below threshold
- Every escalated case carries a reason code from the enum

**Acceptance criteria**

- [ ] ECE reported on holdout with a reliability diagram saved to `eval/output/`
- [ ] Cost curve plotted with the chosen threshold marked
- [ ] Exception queue populated, ranked by ₹ at risk, every entry with evidence
- [ ] Threshold value is derived from the cost model, not hardcoded

**Failure modes:** too few residual samples to calibrate → increase generated dataset size rather than
faking a calibration curve.

**Definition of done:** calibrated, cost-optimal threshold in use; ECE reported on holdout.

-----

## Phase 6 — L4 Anomaly + L5 Bounded Executor + Audit

**Goal:** The gated money action, and the log that makes it defensible.

**Tasks**

1. `l4_anomaly/` — duplicate UTR, **genuine double-settlement (distinct reason code)**, missing
   settlement, fee/tax outside contract band. **L4 has veto power over L1 and L3.**
1. `l5_executor/authority.py` — the policy: `AUTO_POST` requires
   `calibrated_confidence >= threshold AND amount_paise <= AUTHORITY_LIMIT_PAISE AND no anomaly flag`
1. `l5_executor/idempotency.py` — idempotency key derived from stable source IDs; DB UNIQUE enforces it
1. `l5_executor/ledger.py` — write posted entries
1. Wire the full audit line (schema in `CLAUDE.md`) for **every** decision, including abstentions

**Files:** `src/ledgerguard/l4_anomaly/*`, `l5_executor/*`, `tests/test_authority_policy.py`,
`tests/test_idempotency.py`, `tests/test_anomaly_veto.py`

**Implementation details**

- The duplicate-vs-double-settlement distinction must produce **two different reason codes** and
  **neither is ever auto-posted** — this is the demo climax and the safety property
- Idempotency key must be stable across runs and independent of wall-clock time

**Tests**

- **`test_idempotency.py`** — run the full batch twice; output byte-identical; zero duplicate ledger rows
- Over-`AUTHORITY_LIMIT` amounts never auto-post even at confidence 0.99
- An anomaly flag overrides a high-confidence match
- Every decision, including abstentions, produces exactly one audit line

**Acceptance criteria**

- [ ] Rerun produces zero double-posts, proven by test
- [ ] Authority policy enforced and unit-tested
- [ ] `audit.jsonl` line count equals total decision count
- [ ] Both twin cases correctly refused with distinct reason codes

**Failure modes:** anomaly detection firing on everything → tune on validation, report FP rate honestly.

**Definition of done:** money action is bounded, gated, idempotent, and fully audited.

-----

## Phase 7 — D2 Red Team (cut 2nd if behind)

**Goal:** Build the thing that attacks your own matcher, and measure survival.

**Tasks**

1. `data/redteam.py` — adversarial case generator: near-collision pairs (same amount, same day,
   narration differing by one character); plausible-but-wrong subset sums; a prompt-injection narration;
   a refund timed to make a wrong match look perfect
1. `eval/redteam_eval.py` — **adversarial survival rate** = fraction of attack cases correctly refused
   or correctly resolved
1. Keep the red-team set **separate from holdout** so it never contaminates headline metrics

**Files:** `data/redteam.py`, `eval/redteam_eval.py`, `tests/test_redteam.py`

**Acceptance criteria**

- [ ] ≥50 adversarial cases across at least 4 attack categories
- [ ] Survival rate measured and reported separately from holdout metrics
- [ ] The injection case provably results in ABSTAIN
- [ ] Any attack that succeeds is written into `BROKE.md` **and the fix is described**

**Failure modes:** a red team so weak everything survives → include at least one attack you are fairly
confident will succeed. A survival rate of 100% on a trivial suite proves nothing.

**Definition of done:** survival rate measured; failures documented and fixed or honestly listed.

-----

## Phase 8 — D1 Rule Learning (cut 1st if behind)

**Goal:** The headline metric — the LLM’s workload shrinks over time.

**Tasks**

1. `d1_rule_learning/propose.py` — from a human-resolved exception, propose a candidate rule spec
   (narration transform + match key + tolerance)
1. `validate.py` — replay the candidate against train+validation history; count hits and false positives
1. `promote.py` — promote into the L1 registry **only if** `hits >= 3 AND false_positives == 0`
1. Run three sequential batches and record **LLM invocation rate per batch**

**Files:** `src/ledgerguard/d1_rule_learning/*`, `tests/test_rule_learning.py`

**Implementation details**

- Candidate rules are **data (JSON specs), never generated code.** No `eval`, no `exec`.
- The rule spec is a bounded, typed structure the L1 registry can interpret.
- Every promotion and rejection is logged with its validation numbers.

**Tests**

- A rule with a single false positive is **rejected**
- A promoted rule resolves in L1 on the next batch (invocation rate provably drops)
- The registry survives a restart

**Acceptance criteria**

- [ ] LLM invocation rate measured across ≥3 batches and **falls**
- [ ] Precision on auto-posted entries does **not** degrade across those batches
- [ ] Cost per 1,000 records falls in step
- [ ] Chart saved to `eval/output/invocation_decay.png`

**Failure modes:** no rule ever passes validation → loosen `hits` to 2, but **never** loosen the
zero-false-positive requirement. If still nothing passes, report that honestly — a negative result is
publishable and is better than a fake curve.

**Definition of done:** a real declining-invocation chart from measured runs.

-----

## Phase 9 — Ablation, Report, README — NEVER CUT

**Goal:** Every claim becomes a measured number.

**Tasks**

1. **FIRST, before running anything:** write `PREREGISTRATION.md` from `plan.md` §24 — the stratified
   table shape, the binding Δ decision rule, the EASY-stratum prediction, and the holdout discipline —
   and **commit it**. The commit must land before the first holdout ablation run. Do not proceed until
   this commit exists.
1. `benchmark/ablation.py` — three configs on the **same holdout**: rules-only, hybrid (full system),
   LLM-only. One command. **Results must be broken out by difficulty stratum
   (EASY / MEDIUM / HARD / ADVERSARIAL), not just overall.**
1. `eval/metrics.py` — per stratum and overall: auto-match rate, precision on auto-posted, recall, F1,
   **false auto-match rate**, exception-queue precision, throughput (records/sec), LLM call count,
   p50 latency, ₹ cost per 1,000 records
1. **Apply the decision rule.** Compute Δ on HARD+ADVERSARIAL. Look up the outcome band in
   `PREREGISTRATION.md` and **write the verdict into the README in the language that band permits** —
   no more. If Δ < 0.03, write the negative result plainly and reframe the project’s claim around the
   deterministic layer and the abstention gate.
1. `eval/report.py` — render `report.md` + `report.html` with every chart
1. `README.md` — problem → architecture diagram → one-command repro → **stratified results table** →
   the pre-registered verdict → honest limitations (`plan.md` §25 and `CLAUDE.md`)
1. Update `REAL_VS_SIMULATED.md` if anything changed since Phase 1
1. `docs/architecture.md` + diagram image

**Files:** `benchmark/ablation.py`, `eval/metrics.py`, `eval/report.py`, `README.md`,
`docs/architecture.md`

**Acceptance criteria**

- [ ] `PREREGISTRATION.md` committed **before** the first holdout ablation run (verify by git log)
- [ ] `make bench` runs all three configs and prints the **stratified** table
- [ ] Δ computed on HARD+ADVERSARIAL; the README verdict uses only the language its outcome band permits
- [ ] EASY-stratum Δ reported; if materially > 0, an L1 gap is filed in `BROKE.md`
- [ ] Every number in `README.md` traceable to a single committed `make bench` output
- [ ] Precision on auto-posted, false auto-match rate, ECE, throughput, ₹/1k all present per stratum
- [ ] Limitations section written and honest (synthetic data gap, bounded subset-sum, calibration
  distribution, red-team construction)
- [ ] `REAL_VS_SIMULATED.md` current and consistent with what the README claims
- [ ] A stranger with no API keys can run `make demo` on the sample data and reproduce the report

**Failure modes:** hybrid does not beat rules-only → **that is a valid, reportable outcome, not a
failure.** Apply the pre-registered rule, write the negative result, and reframe the claim. Do not tune
on holdout, do not re-run until a favourable seed appears, do not quietly widen the “hard” stratum.
This is the single most important integrity rule in the project — and the pre-registration commit
exists specifically so this decision was already made when it was still cheap to make honestly.

**Definition of done:** one command reproduces every claim in the README.

-----

## Phase 10 — Demo & Submission

**Goal:** Ship it with a day to spare.

**Tasks**

1. `make demo` — deterministic scripted run from seeded data with a **warm cache** (zero live calls)
1. Record the 5-minute video following `plan.md` §21. Cold open on the twin case.
1. Write the “what broke and how you got out” answer from `BROKE.md` — one specific bug, the
   diagnosis, the fix
1. Final repo pass: no secrets, `.env.example` complete, CI green, LICENSE, clean commit history
1. Submit the form: track 04, project name, what it solves, public repo URL, video URL, failure answer

**Acceptance criteria**

- [ ] `make demo` produces identical output on three consecutive runs
- [ ] Video is under 5:00 and the twin-case refusal appears within the first 90 seconds
- [ ] No secret anywhere in git history (scan, don’t assume)
- [ ] Repo is public and CI is green
- [ ] Submitted **by Sep 3**, leaving Sep 4–5 as buffer

**Failure modes:** discovering a broken repo on submission day → Phase 9’s stranger-reproduction check
exists precisely to prevent this. Do it on a clean clone.

**Definition of done:** submitted, with two days of buffer unused.
