# Razorpay Verification (Phase 0)

**Date checked:** 2026-08-22
**Checked by:** Claude Code, Phase 0 session

## Method and an honest caveat

This session's outbound network access goes through a proxy that **blocks direct requests to
`razorpay.com`** (all `WebFetch` calls to `razorpay.com/docs/...` returned `EGRESS_BLOCKED`), and
this session was **not given live Razorpay test-mode API keys**. As a result:

- Task 1 (verify API shapes against current official docs) was done via `WebSearch`, which returns
  indexed snippets of the official docs plus corroborating third-party sources (official SDK
  repositories on GitHub, integration guides, webhook-tooling vendor write-ups). It is **not** a
  direct read of the live doc pages, so field lists below should be treated as "very likely correct,
  cross-referenced across 2+ sources" rather than "verified by direct doc fetch."
- Task 2 (create real test orders/payments/refunds and query settlements to answer R1 empirically)
  **could not be performed** — there is no Razorpay account/keys available to this session. The R1
  answer below is therefore based on documentation and community consensus, not a live experiment.

**Action item for whoever holds real Razorpay test-mode keys:** before Phase 2 (data generation)
begins, run the five-minute check in [Recommended live confirmation](#recommended-live-confirmation-not-yet-done)
below and correct this file if reality differs. Until then, Phase 2 must build to the "settlements
are synthesized" branch, per the mitigation already specified in `plan.md` R1.

-----

## R1 — Does Razorpay test mode return settlement records with UTRs?

**Answer: NO — not by default, and this repo will proceed on that assumption.**

Test-mode transactions are simulated: no real money moves, and settlement is fundamentally the
process of Razorpay transferring real captured funds (minus fees/tax) to the merchant's bank account
on a cycle. Multiple independent sources describe test-mode payments as not participating in that
real transfer process:

- Razorpay's own test-mode framing: test mode is "a safe sandbox environment identical to your live
  setup" used to simulate the checkout/payment flow (mock bank page with Success/Failure buttons); no
  real bank or card network communication occurs beyond the simulated response.
- Community/integration guidance states plainly that transactions created in test mode do not appear
  in real settlement reports, because there is no real fund movement for settlement to act on.
- The public Settlements API documentation and SDKs (`razorpay-php`, `razorpay-go`, `razorpay-ruby`,
  `razorpay-java` — `documents/settlement.md` in each) describe the `Settlement` entity
  (`id, entity, amount, status, fees, tax, utr, created_at`) as something fetched from a merchant's
  live settlement history; nothing in the accessible documentation describes a test-mode simulation
  path that fabricates settlement batches/UTRs for test payments.

**Conclusion:** per `plan.md` R1's own pre-planned mitigation, LedgerGuard will treat the settlement
leg as **not reliably available from the real API in test mode**, and Phase 2 will **synthesize
settlements from real (test-mode) payment data** using documented fee/tax rules, exactly as
`plan.md` §7 and §25 (R1) specify. `REAL_VS_SIMULATED.md` (Phase 1) must mark the Settlements row as
**SIMULATED**, derived from real captured-payment amounts.

This is recorded as an assumption pending the live five-minute check described below, not as a
closed question — if a future session with real keys finds settlement records *do* appear for test
payments, this file and `REAL_VS_SIMULATED.md` must be corrected and the Settlements row flipped to
REAL.

### Recommended live confirmation (not yet done)

With real test-mode keys, in order:
1. `POST /v1/orders` (amount, currency=INR) → capture the `id`.
2. Complete a test payment against that order via checkout or `POST /v1/payments/{id}/capture`.
3. `GET /v1/settlements` and `GET /v1/settlements/recon/combined` a few minutes later.
4. Record literally whether any settlement entity references the test payment's `id`, and whether a
   `utr` is present. Update the answer above with the actual observed behavior and the timestamp.

-----

## Orders API

- **Endpoint:** `POST /v1/orders` (Basic Auth with `key_id:key_secret`)
- **Required request fields:** `amount` (integer, smallest currency unit — paise for INR),
  `currency` (string; only `INR` is documented as broadly supported)
- **Optional request fields:** `receipt` (merchant reference string), `notes` (key/value map),
  `partial_payment` (bool), `method`, `bank_account`
- **Response fields:** `id` (`order_...`), `entity: "order"`, `amount`, `amount_paid`, `amount_due`,
  `currency`, `receipt`, `status` (`created` / `attempted` / `paid`), `attempts`, `notes`,
  `created_at` (Unix timestamp)
- **Fetch:** `GET /v1/orders/{id}`, `GET /v1/orders` (filters: `from`, `to`, `count`, `skip`,
  `receipt`, `expand[]` e.g. `payments`)
- **Money unit:** confirmed — amounts are integer subunits (paise for INR). This matches
  `plan.md` §1's "integer paise" money model directly; no conversion layer beyond int parsing needed.

Sources: `razorpay.com/docs/api/orders/`, `razorpay.com/docs/payments/orders/apis/`,
official SDK docs (`razorpay/razorpay-php` `documents/order.md`).

## Payments API

- **Endpoint:** `GET /v1/payments/{id}`, `GET /v1/payments`, `POST /v1/payments/{id}/capture`
- **Key response fields relevant to reconciliation:** `id` (`pay_...`), `order_id`, `amount`,
  `currency`, `status` (`created` / `authorized` / `captured` / `refunded` / `failed`), `method`,
  `captured` (bool), `fee`, `tax` — fee/tax are present on captured payments and are what make
  gross ≠ net in `plan.md` §2.
- **Refund sub-resource:** payments expose refund status/amount once a refund is issued against them.

Sources: `razorpay.com/docs/api/payments/`, SDK docs cross-reference.

## Refunds API

- **Endpoint:** `POST /v1/payments/{id}/refund`
- **Request fields:** `amount` (optional; omitted = full refund; required and must be less than the
  captured amount for a **partial** refund — matches `plan.md` §12's "create partial refunds
  deliberately"), `speed` (`normal` / `optimum`), `notes`
- **Constraint:** refunds can only be issued against payments in `captured` state.
- **Response fields:** `id` (`rfnd_...`), `payment_id`, `amount`, `status`, `created_at`.

Sources: `razorpay.com/docs/api/refunds/create-normal/`, `razorpay.com/docs/payments/refunds/apis/`,
`razorpay/razorpay-php` `documents/refund.md`.

## Settlements API

- **Endpoint:** `GET /v1/settlements`, `GET /v1/settlements/{id}`, plus recon endpoints
  (`/v1/settlements/recon/combined`) and separate Instant Settlement endpoints
  (`POST /v1/settlements/ondemand`, etc.) for on-demand (T+0, fee-bearing) settlement.
- **Settlement entity fields:** `id` (`setl_...`), `entity: "settlement"`, `amount`, `status`
  (e.g. `processed`), `fees`, `tax`, `utr`, `created_at`.
- **Test-mode behavior:** see R1 above — treated as unavailable/unreliable for this project; the
  fee/tax structure documented here is still used to build the *synthetic* settlement generator in
  Phase 2 so the simulated numbers are contract-accurate even though the batching itself is
  synthesized.

Sources: `razorpay.com/docs/api/settlements/`, `razorpay.com/docs/payments/settlements/apis/`,
official SDK docs (`razorpay-go`, `razorpay-ruby`, `razorpay-java`, `razorpay-php`
`documents/settlement.md`).

## Webhooks — signature scheme

- **Header:** `X-Razorpay-Signature`
- **Algorithm:** HMAC-SHA256, hex-encoded, keyed with the **webhook secret** (a value the merchant
  sets when configuring the webhook in the dashboard — it is *not* the API key/secret pair).
- **What is signed:** the **raw request body bytes**, before any JSON parsing. Signature must be
  computed over the raw body and compared (constant-time) to the header value; parsing first and
  re-serializing before hashing is a documented footgun (produces mismatches, e.g. from float/number
  re-formatting) and must be avoided — this directly informs `plan.md` §12/§17's requirement to
  "verify HMAC-SHA256 signature before processing" using the untouched body.
- **Event envelope shape:** top-level `event` field (e.g. `"payment.captured"`, `"order.paid"`,
  `"refund.processed"`), with `payload.<entity>.entity` nesting the actual entity object, e.g.
  `payload.payment.entity`.
- **Mismatch handling:** a request whose recomputed signature does not match must be rejected
  (non-2xx) and logged, never processed — matches `plan.md` §17 and `tests/test_webhook_signature.py`
  (Phase 4/6).

Sources: `razorpay.com/docs/webhooks/`, `razorpay.com/docs/webhooks/validate-test/`,
`razorpay.com/docs/webhooks/payments/`, third-party webhook-tooling documentation review
(Hookdeck, Svix) corroborating the header name/algorithm/raw-body requirement.

## Test-mode keys and rate limits

- **Key format:** test-mode keys are prefixed `rzp_test_...`; live keys are not usable in test mode
  and vice versa. Test keys require no KYC and are free to generate from the dashboard
  (Settings → API Keys) after toggling the dashboard to Test Mode.
- **Auth scheme:** HTTP Basic Auth, `key_id` as username, `key_secret` as password (per
  `razorpay.com/docs/api/authentication/`).
- **Rate limits:** Razorpay documents that a request rate limiter exists to protect system stability
  and returns HTTP `429` on breach, but **does not publish exact numeric thresholds** in the material
  reachable from this session. `plan.md` §12's "bounded concurrency + exponential backoff on ingest"
  is therefore the correct defensive posture regardless of the exact number — Phase 2's ingest code
  must treat `429` as retryable with backoff and must not assume a specific request/second ceiling.

Sources: `razorpay.com/docs/api/authentication/`, `razorpay.com/docs/payments/dashboard/api-keys/`,
`razorpay.com/docs/api/pagination/` (rate-limiting section referenced from here).

-----

## Summary table

| Item | Verified how | Confidence |
|---|---|---|
| Orders API shape (amount/currency/receipt, paise units) | WebSearch + official SDK repo doc | High |
| Payments API fields (fee, tax, status) | WebSearch | High |
| Refunds API (partial refund via `amount`, `captured`-only) | WebSearch + official SDK repo doc | High |
| Settlements entity fields (utr, fees, tax, status) | WebSearch + 4 official SDK repo docs | High |
| **R1: test mode does not produce real settlements** | WebSearch consensus, no live experiment | Medium — **not empirically confirmed with real keys in this session** |
| Webhook signature: HMAC-SHA256 over raw body, `X-Razorpay-Signature` header | WebSearch + third-party doc review | High |
| Test key prefix `rzp_test_`, Basic Auth | WebSearch | High |
| Numeric rate limit thresholds | Not published / not found | Low — treat as unknown, use backoff |

Nothing above should be treated as a substitute for re-checking `razorpay.com/docs/api/` directly
once this session's network restriction is lifted or a session with live keys is available — per
`plan.md` §4's instruction, "reality wins and this file gets corrected."
