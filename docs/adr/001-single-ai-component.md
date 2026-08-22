# ADR 001 — One LLM call site, not a multi-agent pipeline

## Context

LedgerGuard reconciles Razorpay orders/payments/refunds against a bank statement and an internal
ledger (`plan.md` §1–§2). The obvious "AI finance agent" shape for a hackathon entry is a
multi-agent pipeline: one agent to normalize records, one to propose matches, one to detect
anomalies, one to write the report, orchestrated by a framework. LedgerGuard does not do this.

The system has exactly **one** LLM call site: **L2 — Residual Triage** (`plan.md` §11). Every
other stage — normalization (L0), deterministic matching (L1), calibration and the abstention
gate (L3), anomaly detection (L4), the bounded action executor (L5), and rule learning (D1) — is
plain deterministic code with no model in the loop.

## Decision

Keep a single, narrowly-scoped LLM call site (L2) that:

- only ever sees the ~8–15% residual of records L1 could not resolve deterministically
  (`plan.md` §9's design invariant, enforced by `tests/test_l2_never_sees_resolved.py` in Phase 4),
- receives one unresolved bank line plus the bounded candidate set L1 already produced — never
  the full dataset,
- returns a schema-validated, bounded-choice answer (`{candidate_id | null, confidence,
  evidence[]}`) that can only ever name a candidate already in that bounded set,
- has no tools: no web access, no code execution, no database writes,
- is temperature 0, versioned and content-hashed, response-cached, and budget-capped.

Do not add a second agent (e.g. a separate "anomaly reasoning agent" or "report-writing agent")
without first meeting the bar below.

## Rationale

**The bar for adding another agent: every additional agent must justify itself with a measured
delta on a named case class; none currently can.**

This is not a stylistic preference for minimalism. It is a direct consequence of three things
this project treats as load-bearing:

1. **Money-handling software should have the smallest possible AI attack surface.** Every LLM
   call site is a place where non-determinism, prompt injection (bank narration is
   attacker-controllable, `plan.md` §17), and silent confident-wrongness can enter the system.
   Fewer call sites is fewer things to prove safe.
2. **The project's own headline claim is that the AI's footprint should shrink, not grow**
   (`plan.md` §1, D1 rule learning). A multi-agent architecture pulls in the opposite direction:
   more agents is more surface for the AI to "own," not less.
3. **The pre-registered ablation (`plan.md` §24) is the only mechanism this project trusts to
   justify an LLM call at all.** L2 exists because the residual set is hypothesized to need
   narration-semantics reasoning that rules cannot cheaply replicate — and that hypothesis is
   falsifiable and gets tested on holdout. A second agent proposed without an equivalent
   falsifiable justification would be added on vibes, which this project's own integrity rules
   (`plan.md` §24.3) exist to prevent.

Deterministic code (L0, L1, L3, L4, L5, D1) is preferred everywhere it is *sufficient*, not
because determinism is inherently superior, but because it is auditable, replayable byte-for-byte
(`tests/test_idempotency.py`), and free. An LLM is used only where a concrete, measured gap has
been shown to exist and deterministic code has not closed it.

## Consequences

- **Positive:** the entire non-L2 pipeline is unit-testable without any network access or API
  key, exactly as this repo's CI does today. The audit log (`audit.jsonl`) can attribute every
  decision to either a specific deterministic rule or the single named model, with no ambiguity
  about which of several agents was "responsible." The cost model (`plan.md` §20) has exactly one
  variable cost line item to reason about.
- **Negative:** if a future residual case class turns out to need a genuinely different kind of
  reasoning than L2's narration-matching prompt provides (e.g., something that needs multi-step
  tool use, not just classification), forcing it through the same single-prompt L2 call site
  would be the wrong fix — that pressure is exactly what the revisit condition below is for.
- **Explicitly not a consequence:** this ADR does not claim one agent is always correct for every
  problem. It claims one agent is currently justified for *this* problem, given what has actually
  been measured.

## Revisit condition

Revisit this decision (i.e., consider adding a second agent or splitting L2's responsibility)
**only if both** of the following hold:

1. The residual set that reaches L2 is shown (via the stratified ablation, `plan.md` §24.1) to
   contain **at least two distinct case classes that plausibly need different reasoning
   strategies** — e.g., narration-semantics matching vs. some other kind of judgment L2's single
   prompt structurally cannot express well (not just "L2 gets some of these wrong," which is a
   prompt/calibration problem, not an architecture problem).
2. A stratified ablation run shows a **measured, holdout, per-class gain** from splitting the
   responsibility (analogous to the Δ ≥ 0.03 bar in `plan.md` §24.2) — not a hypothesis that it
   would help.

Absent both conditions, additional agents are scope creep and should be rejected, per
`phases.md`'s own hard rule against unilaterally changing architecture decisions in `plan.md`.
