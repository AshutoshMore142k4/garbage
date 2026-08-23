# SUBMISSION.md — the form answers, ready to paste

Prepared per `phases.md` Phase 10 tasks 3 and 5. Everything below is drawn from measured output
in this repo (`report.md`, `BROKE.md`, `PROGRESS.md`) — no number here is estimated or rounded up.

**Two fields on the form cannot be filled in from inside this repo** and are left as explicit
blanks below for a human to complete: the video URL (the video has to be recorded) and the
confirmation that the repo is public. Both are called out in "Still needed from a human" at the
bottom rather than guessed at.

-----

## Track

**04 — AI Finance Controller**

## Project name

**LedgerGuard**

## What it solves (short)

Reconciliation is where merchant money actually goes missing. LedgerGuard matches Razorpay
orders/payments/refunds against a bank statement and an internal ledger — and its distinguishing
property is that it knows when *not* to act. A deterministic rules layer resolves what it can; a
single, narrowly-scoped LLM call site sees only the residual; a calibrated gate decides whether
the answer is confident enough to be worth the money at risk; and an anomaly detector can veto a
confident match outright. On the committed 300-record sample it auto-posts 198, refuses 102, and
its false auto-match rate is **0.0%** — nothing it posted was wrong.

## What it solves (longer, if the form allows it)

The hard case is not "match 3,000 rows." It is the pair of bank credits with the same amount, the
same value date, and narrations differing by one character — where one is a duplicate report and
the other is real money sent twice. Automate that wrong and you either lose the money or you
double-count it. LedgerGuard refuses both, with **distinct reason codes** (`DUPLICATE_UTR` vs.
`GENUINE_DOUBLE_SETTLEMENT`) so an operator knows which is which.

What makes that refusal interesting: the calibrated confidence on both twins is **0.985, above
the gate's 0.98 threshold**. L3 was ready to post them. L4's anomaly detector vetoed it. "An
anomaly flag always beats a confident match" is a design invariant asserted in tests, not a
docstring.

Three things the project measures rather than asserts:

- **The LLM's workload shrinks over time (D1).** Human-resolved exceptions get compiled into
  candidate deterministic rules, replayed against history, and promoted into the rules layer only
  at ≥3 hits and **zero** false positives. Measured across three sequential batches: invocation
  rate 17.1% → 15.0% → 11.2%, precision holds (88.6% → 97.8% → 97.8%), cost falls in step.
- **An adversarial red team attacks the matcher (D2).** 60 cases, 4 attack categories, measured
  survival rate **80.0% (48/60)**, kept entirely out of the holdout so it can't contaminate
  headline metrics. It found a real bug on its first run (below) and one attack still succeeds,
  reported rather than hidden.
- **A pre-registered ablation, committed before the run.** See the failure answer below.

## The "what broke and how you got out" answer

> **The demo pair could not have worked, and a green test suite was hiding it.**
>
> In Phase 6 I built the anomaly detectors whose entire purpose is to refuse the duplicate-vs-
> double-settlement pair — the project's own headline demo. Every unit test passed. Instead of
> stopping there, I ran `make close` for real and queried the database for those two specific
> rows. The double-settlement line had escalated on a generic `AMOUNT_GAP_EXCEEDS_TOLERANCE`:
> the right outcome for entirely the wrong reason.
>
> **Diagnosis.** The data generator forced the pair's `value_date` to a fixed constant so the two
> scenarios could share a date — that's the point of the demo — but left the underlying payment's
> `captured_at` on its normal random 0–120-day draw, completely decoupled. For this seed the draw
> landed nearly two months *after* the forced bank credit date. The matcher requires `captured_at`
> to precede `value_date` by 2–4 days, so a payment captured after the credit can never match.
> Neither twin could ever resolve to anything, by construction — there was never a proposed match
> for the anomaly detector to veto.
>
> **The fix, and the second bug hiding behind it.** I added a `forced_created` parameter and
> pinned `captured_at` to `value_date − 2 days`. It *still* failed. `_make_order_payment` adds its
> own independent 1–30 minute offset on top of whatever timestamp it's handed, to make capture
> times look real — and that offset alone pushed the gap under the tolerance floor by single-digit
> minutes. A boundary-condition bug sitting directly behind the first one. The final fix is a
> `DEMO_CAPTURED_AT` constant with an explicit ~45-minute safety margin, documented inline with
> the arithmetic so the next person doesn't reintroduce either.
>
> **Why it matters beyond "a test passed."** A version of this repo could have shipped passing
> every unit test while the actual demo scenario silently never reached the code path meant to
> protect it. That's why the acceptance checks for that phase were verified against real
> `make close` output and a real database query, not only against synthetic fixtures. The full
> account — and everything else that broke across ten phases — is in `BROKE.md`.

### If they ask for a second one, the honest-negative-result story

I pre-registered the ablation's decision rule in `PREREGISTRATION.md` and **committed it before
the ablation existed** (`git log -- PREREGISTRATION.md` shows the commit landing first). It bound
me in advance: if Δ = hybrid F1 − rules-only F1 on the HARD+ADVERSARIAL strata came in under
0.03, I had to report it as a negative result and reframe the claim around the deterministic
layer.

**Δ came out 0.000.** Rules-only and hybrid are numerically identical on every stratum. So the
README says exactly that, in the language the pre-registered band permits and no stronger. A
manufactured win is detectable at a panel and costs more than an honest negative result — and
"where did you choose *not* to use AI" is one of the four judging criteria, so this is the
strongest available answer to it, not a shortfall.

## Public repo URL

`https://github.com/AshutoshMore142k4/garbage`

*(Repo visibility needs a human to confirm — see below.)*

## Video URL

`________________________` — **not yet recorded.** See below.

-----

## Still needed from a human (cannot be done from inside this repo)

1. **Record the ~5-minute video.** `make demo` is built, deterministic (byte-identical across
   three consecutive runs, pinned by `tests/test_demo_determinism.py`), and its on-screen section
   headers follow `plan.md` §21's timing beats directly — the cold open on the twin case is the
   first thing it prints, so the refusal lands well inside the first 90 seconds. Recording it and
   uploading it is a human step.
2. **Confirm the repo is public**, per the acceptance criterion "repo is public and CI is green."
   CI is green (verifiable in Actions); visibility is a GitHub setting only the owner can check
   and change.
3. **Submit the form**, using the answers above. Submitting to an external service on the owner's
   behalf is theirs to do.

## Final repo pass — status

| Check | Status |
|---|---|
| `make demo` identical across three consecutive runs | **verified** — byte-identical, and pinned by a subprocess test in the suite |
| No secret anywhere in git history | **verified** — scanned every blob in `git rev-list --all` for live-key/private-key/token patterns: zero matches; no `.env` was ever committed |
| `.env.example` complete | **verified** — all 8 settings `config.py` reads are present, placeholders only |
| CI green | **verified locally** — full suite passes; GitHub Actions runs the same `pytest -q` on 3.11 |
| LICENSE | **added** — MIT |
| Clean commit history | one commit per phase, each with its acceptance criteria recorded in `PROGRESS.md` |
| Repo is public | **needs a human** (see above) |
| Video under 5:00, twin case in first 90s | **needs a human** (see above) |
| Submitted by the deadline | **needs a human** (see above) |
