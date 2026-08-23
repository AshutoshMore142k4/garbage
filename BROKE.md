# BROKE.md

Daily log: what broke, how it was diagnosed, how it was fixed. This feeds the submission's
"what broke and how you got out" answer (`plan.md` §21, `phases.md` Phase 10).

-----

## 2026-08-22 — Phase 0

**What broke:** Direct `WebFetch` access to `razorpay.com` (and to several third-party doc-review
sites, e.g. `www.svix.com`) was blocked by this session's outbound network egress proxy
(`EGRESS_BLOCKED`). This session also had no live Razorpay test-mode API keys, so Phase 0 Task 2
("create a handful of test orders, capture payments, and query settlements" to answer R1
empirically) could not be executed as a real API call.

**Diagnosis:** The sandboxed execution environment for this session restricts egress to an
allowlist that does not include `razorpay.com`. This is an environment constraint, not a bug in
the plan.

**Fix / workaround:** Used `WebSearch` (which indexes/snippets the same official docs plus
official SDK repositories on GitHub, which *were* fetchable) to cross-reference API shapes across
2+ independent sources instead of a single direct doc fetch. Documented every finding's confidence
level and source in `docs/razorpay-verification.md`, and explicitly flagged R1's answer as
"based on documentation consensus, not a live experiment" rather than presenting it as verified
fact. Left a concrete recommended live-confirmation procedure in that file for whoever has real
keys to run before Phase 2 locks in the "settlements are synthesized" decision permanently.

**Why this is the right call, not a shortcut:** `plan.md` §6 and §24.3 are explicit that a
manufactured/assumed result reported as measured is worse than an honest gap. Fabricating a
"we created test orders and confirmed X" narrative without actually having done so would violate
that principle directly. The honest path was to do the best available secondary research, mark its
confidence level, and hand off the one remaining empirical step explicitly.

## 2026-08-23 — Phase 2

**What broke:** Same root constraint as Phase 0 (no Razorpay credentials, no egress to
razorpay.com in this session) surfaced again while writing `razorpay/ingest.py`: it cannot be
exercised against a live account here. Additionally, while designing `ingest.py`, a real product
constraint became clear during implementation (not just a session limitation): Razorpay test mode
has no documented server-only "create a captured payment" endpoint — getting from an order to a
*captured* payment requires completing checkout with a test card, a client-facing step. A script
that only calls server APIs cannot fabricate that step.

**Diagnosis:** This is a genuine property of Razorpay's test-mode design (consistent with Phase
0's research: "mock bank page with Success/Failure buttons"), not something to work around by
inventing a fake capture endpoint.

**Fix:** `ingest.py`'s `fetch_captured_payments` reads back payments that were captured through
checkout (done separately, out of this module's scope) rather than pretending to create them
server-side. Order creation and refund creation, which *are* pure server APIs, are fully
implemented and unit-tested against a fake client (no real network in tests). This is documented
in the module's own docstring and in `PROGRESS.md` Phase 2, rather than silently shipping a
capture path that would fail against a real account.

**Also fixed during this phase (a real bug, not an environment constraint):** the first draft of
the duplicate-UTR/genuine-double-settlement demo pair in `data/generator.py` accidentally
produced *identical* narrations for both scenarios (a `_flip_last_char` collision), which would
have failed the "near-identical, not identical" requirement from `plan.md` J4. Caught by
`tests/test_generator.py::test_holdout_contains_the_duplicate_vs_double_settlement_pair` before
commit; fixed by giving the two scenarios distinct forced base narrations.

## 2026-08-23 — Phase 3

**What broke:** The first version of the L1 matcher added a fourth rule,
`rule_exact_utr_duplicate`, meant to resolve the DUPLICATE_UTR chaos category's "reporting
artifact" bank line by treating whichever of the two same-UTR bank lines was seen first (after
sorting the batch by bank-line id) as "the real one." Running the matcher against
`data/samples/` and diagnosing *why* precision was only 96.8% (rather than assuming a passing
test suite meant the code was right) turned up 9 mismatches. 5 of them were the wrong half of
the pair: the rule was flagging the *real* settlement line as the duplicate and letting the fake
one resolve normally, because `bl_dup_00306` sorts alphabetically before `bl_setl_synth_...`
("d" < "s") — an artifact of this project's own id-naming scheme, not a real-world signal for
which credit is genuine.

**Diagnosis:** Two separate problems, not one. (1) There is no real-world signal available here
to say which of two identical-UTR bank lines is the genuine one — sorting by id is arbitrary and,
worse, systematically backwards for this dataset's naming convention. (2) Re-reading `phases.md`
Phase 6 while investigating: duplicate-UTR detection is explicitly named as an **L4 anomaly
detection** responsibility ("L4 has veto power over L1 and L3"), not an L1 rule. The rule was
both incorrect and in the wrong phase.

**Fix:** Removed `rule_exact_utr_duplicate` entirely rather than patching its tie-break logic.
L1 now resolves both halves of a DUPLICATE_UTR pair via ordinary amount/date matching, which
means the fake line currently gets incorrectly matched to the same order as the real one --
that gap is real, expected, and documented in `PROGRESS.md` Phase 3 as a known limitation to be
closed by L4 in Phase 6, not something to solve prematurely at L1 with an unprincipled heuristic.
Precision on `data/samples/` improved from 96.8% to 98.6% once the *backwards* half of the bug
was removed; the remaining ~1.3% gap is exactly the four DUPLICATE_UTR duplicate lines, confirmed
by re-diagnosing the mismatch list after the fix.

**Why this is the right call, not a shortcut:** it would have been easy to "fix" the ordering
(e.g., sort by captured-payment reference instead of bank-line id) and ship a rule that happened
to pass the unit tests I would have written for it. That would have re-created the same
architectural misplacement with better luck instead of removing it. Cutting the rule and writing
down exactly why is consistent with `plan.md` §6's own principle: a structural fix beats a
patched-over guess, even when the guess would score better on a shallow test.

## 2026-08-23 — Phase 4

**What broke (caught before it caused damage):** `.gitignore` (written in Phase 0) listed
`data/cache/` as ignored, under a generic "generated data" comment. Re-reading `plan.md` §20
while building L2's response cache found this was wrong: the cache is explicitly supposed to be
**committed** ("A rerun of the benchmark serves from cache and costs ₹0... anyone can rerun the
benchmark without keys"). Had this gone uncorrected, every future benchmark run in a fresh clone
would have silently required live API credentials, quietly breaking the exact reproducibility
guarantee Phase 9's ablation depends on. Fixed by removing `data/cache/` from `.gitignore` and
leaving a comment explaining why, before any cache files existed to be accidentally lost.

**A real API-behavior gap, not a bug in this repo:** `plan.md` §11's L2 spec calls for
`temperature 0`. Checked against the actually-installed `anthropic` SDK and current Claude API
documentation (via the bundled `claude-api` skill) rather than assumed from training data:
current Claude models run adaptive thinking by default and reject sampling parameters
(temperature/top_p/top_k) while thinking is active — a 400, not a soft warning. The workaround
of explicitly disabling thinking to regain temperature control has its own documented failure
mode (stray `<thinking>`-tag or tool-call-shaped text leaking into otherwise-structured output),
which would have undermined the very schema-validation abstain-path this module exists to
guarantee. Resolved by dropping temperature control entirely, using a low `output_config.effort`
instead, and leaning on the prompt-hash cache for reproducibility — which `plan.md` §20 already
treats as the real reproducibility mechanism, so this isn't a new workaround bolted on, just
using the mechanism the plan already specified for the job "temperature 0" used to do.

## 2026-08-23 — Phase 6

**What broke:** Building L4's anomaly detectors and then actually running `make close` against
the committed sample dataset (rather than trusting the unit tests alone) revealed that the
Phase 2 demo pair — the duplicate-UTR and genuine-double-settlement bank lines meant to be *the*
demo climax (`plan.md` §8 J4, §21) — were **both silently unmatchable by L1**, not just
correctly-flagged-as-anomalous. Querying the DB after the first `make close` run showed the
genuine-double-settlement line landing on a generic `AMOUNT_GAP_EXCEEDS_TOLERANCE` escalation
instead of the intended `GENUINE_DOUBLE_SETTLEMENT` anomaly flag — the right *outcome* (never
auto-posted) for the wrong *reason* (nothing had ever proposed a match for it to veto).

**Diagnosis, in two layers, both caught by re-checking real query output rather than assuming a
passing test suite meant the demo pair worked:**

1. `data/generator.py`'s demo-pair construction forces `value_date` to a fixed `DEMO_VALUE_DATE`
   (so the two scenarios can share an identical date, which is the point of the demo), but the
   underlying order/payment's `captured_at` was left on the normal random 0-120-day draw from
   `BASE_DATE` — completely decoupled from the forced date. For this seed, the draw landed on
   May 1st, nearly two months *after* the March 6th forced `value_date`. L1's date-tolerance rule
   requires `captured_at` to precede `value_date` by 2-4 days; a payment captured *after* the
   bank credit's value date can never pass that check, so neither demo-pair bank line could ever
   resolve to anything, by construction.
2. After forcing `captured_at` to `DEMO_VALUE_DATE - 2 days` to fix (1), the pair *still* failed.
   `_make_order_payment` adds a second, independent random offset (1-30 minutes) on top of
   whatever `created` timestamp it's given, to make the stored `captured_at` look like a real
   capture time rather than a round number. That extra offset alone was enough to push the gap
   below the T+2 tolerance floor by single-digit minutes — a boundary-condition bug hiding
   immediately behind the first one.

**Fix:** Added a `forced_created` parameter to `_make_order_payment` (previously it could only
ever draw a random date) and a `DEMO_CAPTURED_AT` constant with an explicit ~45-minute safety
margin below the exact 2-day mark, documented inline with the arithmetic so the next person
touching this doesn't reintroduce either bug. Regenerated `data/samples/` and re-verified via a
real `make close` run (not just unit tests) that both demo-pair lines now resolve to their
intended, distinct reason codes and neither auto-posts.

**Why this matters beyond "a test passed":** this is `plan.md`'s own stated demo climax and the
project's core safety-property proof. A version of this repo that could pass every unit test
while the actual demo scenario silently failed to even reach the code path meant to protect it
would have been a much worse outcome than catching it here, at the point where it's cheap to fix
— which is exactly why `PROGRESS.md`'s acceptance-criteria checks for this phase were verified
against real `make close` output and a real DB query, not only against synthetic test fixtures.

## 2026-08-23 — Phase 7

**What broke (a real bug the red team was built to find, and did):** `PLAUSIBLE_WRONG_SUBSET_SUM`
constructs a bank credit with two disjoint groups of ledger payments that both sum exactly to it
-- a true 3-payment group, and a decoy 2-payment group deliberately captured earlier so it sorts
first in `PaymentIndex.candidates_before`'s ascending-by-captured_at order. Running this attack
against the (pre-fix) pipeline showed L1's `rule_subset_sum_split_settlement` confidently
resolving to the *decoy* group in every one of 15 cases (`Decision.correct == False` in every
case, confirmed by direct inspection, not just by the aggregate survival number). The reason:
`subset_sum.find_subset` is a "first sum found" search over its candidate list in list order --
it had no notion that a different, equally-valid group might exist elsewhere in the same pool,
so it never even considered whether its answer was unique.

**Diagnosis:** This is not a hypothetical edge case dreamed up for the red team -- it is the same
class of arbitrary-tie-break bug already found and removed once before in Phase 3
(`rule_exact_utr_duplicate`'s alphabetical tie-break). The lesson from Phase 3 evidently didn't
fully propagate to `subset_sum.find_subset`'s own design: a search that returns "the first way I
found," with no check for a second way, is silently making an arbitrary choice and reporting it
as a confident (0.93) match.

**Fix:** `rule_subset_sum_split_settlement` now re-runs `find_subset` on the remaining candidate
pool (after removing the first group's payments) whenever the first search finds a group of size
> 1. If that second search also finds an exact-sum group, the two groups are genuinely
indistinguishable from where this rule sits -- there is no signal available to pick a winner --
so it now escalates (`AMBIGUOUS_NARRATION_MULTI_CANDIDATE`) instead of guessing. Re-running the
full test suite (116 pre-existing tests) and `make` `L1`-only precision on `data/samples/`
afterward confirmed this didn't regress ordinary split-settlement matching (precision held at
97.6% overall / 98.3% on validation) -- the fix only changes behavior when a *second*, disjoint
exact-sum group genuinely exists, which essentially never happens by chance with the production
generator's continuous random amounts. Re-running the red team afterward: `PLAUSIBLE_WRONG_SUBSET_SUM`'s
survival rate went from confidently-wrong-every-time to 15/15 correctly escalated.

**What broke and was *not* fixed, honestly listed instead:** `NEAR_COLLISION_PAIR` constructs a
stray bank credit with no real backing settlement at all, whose amount and date happen to exactly
collide with an unrelated, genuinely-captured payment elsewhere in the ledger (narration one
flipped character off that payment's own merchant token). `rule_single_payment_net_match` cannot
tell this apart from a real single-candidate match -- it produces exactly the same feature
signature (`amount_gap=0`, date within tolerance, high narration plausibility, `raw_confidence=0.97`)
that ordinary, genuinely-correct `EASY_EXACT_MATCH` production examples produce. Measured result:
12 of 15 cases (80%) clear L3's calibrated gate and auto-post the wrong order; L4 has no detector
for this pattern either (it isn't a duplicate UTR, and it isn't the same order matched twice --
it's two *different*, otherwise-unrelated orders that happen to share an amount).

**Why this one is listed, not patched:** amount + date + narration matching, with no independent
per-order reference field in the ledger (already flagged as a known gap in `PROGRESS.md`/this
file, Phase 3), cannot distinguish a genuine settlement from a same-amount coincidence *even in
principle* -- there is no additional signal at L1, L3, or L4 to check, because none exists in this
data model. A "fix" that tried to paper over this with a heuristic (e.g. penalizing candidates
whose narration wasn't a *perfect* string match) would just move the false-negative/false-positive
trade-off around without closing the actual gap, and would likely hurt `TRUNCATED_NARRATION`'s
legitimate matches in the process. The honest fix requires a new independent signal this project's
data doesn't have (e.g. an order reference embedded in the real bank narration, which
`docs/razorpay-verification.md` already flags as unconfirmed for real Razorpay settlement
narrations) -- recorded here per `plan.md` §6/§24.3's instruction to report a real gap rather than
manufacture a fix that only looks like one. The partial mitigation already in place is real,
though: 3 of 15 cases (20%) *do* get caught by L3's calibrated gate, because their particular
timing pushes the feature vector's `date_skew_days` far enough from the tolerance-window center
that calibrated confidence falls under threshold -- this is incidental, not a designed defense
against this specific attack, and should not be relied on.

**Why this matters beyond "a test passed":** this is exactly the failure mode `phases.md` Phase 7
warns against in the other direction -- a red team that's too weak proves nothing, but so does a
red-team writeup that quietly omits the attack that actually worked. `PLAUSIBLE_WRONG_SUBSET_SUM`
was found, understood, and fixed with a real code change and a re-verified precision number, not
just a passing test; `NEAR_COLLISION_PAIR` is reported with its exact measured survival rate
(3/15) and a concrete explanation of why closing it needs data this project doesn't have, rather
than being hidden inside a headline "80% survival rate" number with no per-category breakdown.
