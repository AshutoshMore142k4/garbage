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
