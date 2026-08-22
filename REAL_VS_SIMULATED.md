# REAL_VS_SIMULATED.md — Honesty Ledger

Every data source LedgerGuard uses, labelled plainly, so no metric in `README.md` or the demo can
be mistaken for something it isn't. See `plan.md` §14/§25 and `phases.md` Phase 1/9.

| Source | Status | How produced | What this means for the metrics |
|---|---|---|---|
| Orders / Payments / Refunds | REAL | Razorpay **test-mode** API (`plan.md` §4/§12) | Real IDs, amounts, fee/tax fields as Razorpay's test sandbox reports them. No real money moves (test mode), but the shapes and values come from the actual API, not invented. |
| Settlements | **SIMULATED** | Per the Phase 0 finding for R1 (`docs/razorpay-verification.md`): Razorpay test mode is not expected to produce real settlement batches/UTRs, so the settlement leg is synthesized from real captured-payment amounts using the documented fee/tax contract (Phase 2). **This finding itself was reached without a live experiment** — no Razorpay credentials were available to the Phase 0 session, so it rests on documentation/community-consensus research, not an observed API response. A session with real test-mode keys should run the live-confirmation check in `docs/razorpay-verification.md` and correct this row if reality differs. | Settlement amounts/UTRs/timing in this project are **not observed Razorpay behavior** — they are a plausible simulation built on real payment data. Any claim about "settlement" in the README must say so. |
| Bank statement | SYNTHETIC | Seeded generator (`data/generator.py`, Phase 2) | Narration mangling, T+2 skew, split-settlement grouping etc. are modelled by the generator's assumptions, not observed real bank narrations. |
| Internal ledger | SYNTHETIC | Derived deterministically from real Razorpay orders (Phase 2) | Order-side facts trace back to real orders; the ledger file format itself is invented for this project. |
| Ground truth labels | SYNTHETIC | The generator knows the answer it constructed (Phase 2) | Precision/recall/F1 computed against these labels are exact *relative to the generator's own construction*, not validated against an independent real-world reconciliation. The generated difficulty distribution is LedgerGuard's own choice, not a measured real-world distribution. |
| Red-team cases | SYNTHETIC | Adversarial by construction (`data/redteam.py`, Phase 7) | The measured "adversarial survival rate" describes robustness to *this project's own* attack suite, not a real-world attack rate. |

## Current status (as of this commit)

Only the **Orders / Payments / Refunds** row's REAL claim and the **Settlements** row's mechanism
are meaningfully populated so far — this repo is at the end of Phase 1 (`PROGRESS.md`). No data has
been generated yet (Phase 2), so the Bank statement / Internal ledger / Ground truth / Red-team
rows describe the *planned* mechanism, not yet-executed output. This file must be re-checked for
accuracy at the end of every phase that touches data provenance, per `phases.md` Phase 9's
requirement that it stay "current and consistent with what the README claims."
