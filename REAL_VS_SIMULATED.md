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
| Red-team cases | SYNTHETIC | not yet generated | Adversarial by construction (`data/redteam.py`, Phase 7 — not started) | The measured "adversarial survival rate" will describe robustness to *this project's own* attack suite, not a real-world attack rate. |

## Current status (as of this commit)

End of Phase 2 (`PROGRESS.md`). `data/generator.py` is built, tested, and has produced a real
committed sample at `data/samples/` (300 bank lines, all 10 chaos categories present, the
duplicate-UTR/genuine-double-settlement demo pair forced into holdout). `ledgerguard.razorpay.ingest`
is built and unit-tested but has never been run live — so, plainly stated, **every row above is
currently SIMULATED or SYNTHETIC in what's actually in this repo**, including the Orders/Payments/
Refunds row whose *design* is REAL. Red-team cases don't exist yet (Phase 7). This file must be
re-checked for accuracy at the end of every phase that touches data provenance, per `phases.md`
Phase 9's requirement that it stay "current and consistent with what the README claims."
