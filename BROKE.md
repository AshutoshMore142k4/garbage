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
