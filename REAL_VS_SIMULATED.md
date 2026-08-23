# REAL_VS_SIMULATED.md — Honesty Ledger

Every data source LedgerGuard uses, labelled plainly, so no metric in `README.md` or the demo can
be mistaken for something it isn't. See `plan.md` §14/§25 and `phases.md` Phase 1/9.

| Source | Status (as designed) | Status (in the data actually committed right now) | How produced | What this means for the metrics |
|---|---|---|---|---|
| Orders / Payments / Refunds | REAL | **SIMULATED** | Designed to come from the Razorpay **test-mode** API via `ledgerguard.razorpay.ingest` (`plan.md` §4/§12), which is written and unit-tested but has never been run against a live account (no credentials, no egress to razorpay.com in any session so far — Phase 0/2, `BROKE.md`). `data/generator.py` falls back to its own seeded `synthetic_fixture` orders/payments whenever no real `data/raw/*.json` exists, which is the only path exercised so far, including for the committed `data/samples/`. | Every order/payment ID, amount, fee, and timestamp currently in this repo is generator-invented, not Razorpay-observed. This row flips to REAL only once `make ingest` has actually been run with live keys and its output feeds the generator. |
| Settlements | SIMULATED | **SIMULATED** | Per the Phase 0 finding for R1 (`docs/razorpay-verification.md`): Razorpay test mode is not expected to produce real settlement batches/UTRs, so the settlement leg is synthesized using a documented fee/tax contract (Phase 2). **This finding itself was reached without a live experiment** — no Razorpay credentials were available, so it rests on documentation/community-consensus research, not an observed API response. | Settlement amounts/UTRs/timing are **not observed Razorpay behavior** even in the best case — they are a plausible simulation. Any claim about "settlement" in the README must say so. |
| Bank statement | SYNTHETIC | SYNTHETIC | Seeded generator (`data/generator.py`, Phase 2) | Narration mangling, T+2 skew, split-settlement grouping, and the 10-category chaos taxonomy (see `data/generator.py`'s docstring — not from `CLAUDE.md`, which doesn't exist) are modelled by the generator's own assumptions, not observed real bank narrations. |
| Internal ledger | SYNTHETIC | SYNTHETIC | Derived from the orders/payments row above (Phase 2) | Currently derived from synthetic orders, not real ones (see row 1); the ledger file format itself is invented for this project either way. |
| Ground truth labels | SYNTHETIC | SYNTHETIC | The generator knows the answer it constructed (Phase 2) | Precision/recall/F1 computed against these labels are exact *relative to the generator's own construction*, not validated against an independent real-world reconciliation. The difficulty distribution (counts per category in `chaos_manifest.json`) is LedgerGuard's own choice, not a measured real-world distribution. |
| Red-team cases | SYNTHETIC | **SYNTHETIC** | Adversarial by construction (`data/redteam.py`, Phase 7 — done); generated fresh into a temp directory on each `eval/redteam_eval.py` run, never written into `data/samples/` or `data/raw/`. | The measured 80% (48/60) adversarial survival rate describes robustness to *this project's own* attack suite, not a real-world attack rate or an independently sourced corpus. |
| Learned rules (D1) | Derived, not simulated | **Derived from simulated exceptions** | `d1_rule_learning/propose.py` generalizes a "human-resolved exception" that, in every session so far, is actually ground truth's own known-correct answer standing in for a live operator (no live operator has ever been available either — same root cause as every other SIMULATED row). | The measured invocation-decay curve (17.1%→15.0%→11.2%, Phase 8) describes this system's rule-learning *mechanism* working correctly on synthetic exceptions; it is not a claim about how quickly a real human-in-the-loop team would resolve real exceptions. |
| L2 responses (Anthropic model output) | REAL model, live call | **SIMULATED via free rapidfuzz fallback** | Designed to call the real `anthropic` SDK (`l2_llm_triage/client.py`, schema-validated, prompt-hash cached, Phase 4) whenever `LLM_API_KEY` is configured; falls back to `l2_llm_triage/fallback.py` (rapidfuzz-only, $0, no network) whenever it isn't. No session in this project, across Phases 0-9, has ever had live Anthropic credentials or network egress to `api.anthropic.com`, so the fallback path is the *only* path ever exercised, including for every ablation/benchmark number in `README.md`. | Every "LLM invocation," "hybrid F1," and "₹ cost" figure in `README.md`/`report.md` describes this system's currently-shipped fallback-served L2 path, not a live Claude model's performance on the same holdout. The architecture (bounded candidates, schema validation, caching) is built so a real credential would need no other code change to plug in. |

## Current status (as of this commit)

End of Phase 9 (`PROGRESS.md`). All ten rows above have now actually been exercised at least
once, including red-team generation (Phase 7) and rule learning (Phase 8) — but the fundamental
picture from Phase 2 is unchanged: **every row above is currently SIMULATED or SYNTHETIC in what's
actually in this repo**, including the Orders/Payments/Refunds row whose *design* is REAL, and
including the L2 row, whose *design* is a live model call. `ledgerguard.razorpay.ingest` is built
and unit-tested but has never been run live; no session has ever had Anthropic credentials either.
The pre-registered ablation (`PREREGISTRATION.md`, `benchmark/ablation.py`) and every number
`README.md` quotes from it inherit this: they are honest, reproducible measurements of *this
system as actually shipped*, not of a live Razorpay account or a live Claude model. This file must
be re-checked for accuracy at the end of every future phase that touches data provenance, per
`phases.md` Phase 9's requirement that it stay "current and consistent with what the README
claims."
