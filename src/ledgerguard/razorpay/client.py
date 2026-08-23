"""Thin wrapper around the official `razorpay` SDK client (plan.md #12/#13).

Verified request/response shapes are in docs/razorpay-verification.md. Method names and
signatures below (`order.create`, `order.payments`, `payment.capture(id, amount)`,
`payment.refund(id, data={"amount": ...})`) were checked directly against the installed
`razorpay` SDK source in this environment, not just secondary research.

Retry behaviour, honestly scoped: the installed SDK (`Client(..., max_retries=..., ...)` plus
`enable_retry(True)`) already retries `ConnectionError`/`Timeout` internally with exponential
backoff and jitter -- that is enabled below and covers plan.md #12's "bounded concurrency +
exponential backoff on ingest" for transient network failures. The SDK does not preserve HTTP
status codes on the exceptions it raises for non-2xx responses (`BadRequestError`, `GatewayError`,
`ServerError` all carry only a message string), so this module cannot cleanly special-case HTTP
429 the way a status-code-aware client could -- docs/razorpay-verification.md already flags that
Razorpay's exact rate-limit thresholds aren't published anyway. `_with_backoff` below retries the
SDK's `ServerError`/`GatewayError` (its 5xx-shaped, plausibly-transient exceptions) and does not
retry `BadRequestError`, since retrying an identical malformed request just fails identically.
"""
from __future__ import annotations

import time
from typing import Any, Callable, TypeVar

import razorpay
from razorpay.errors import GatewayError, ServerError

T = TypeVar("T")

MAX_RETRIES = 4
BASE_BACKOFF_SECONDS = 1.0


def _with_backoff(fn: Callable[[], T]) -> T:
    attempt = 0
    while True:
        try:
            return fn()
        except (ServerError, GatewayError):
            if attempt >= MAX_RETRIES:
                raise
            time.sleep(BASE_BACKOFF_SECONDS * (2**attempt))
            attempt += 1


class RazorpayClient:
    """Wraps the subset of the Razorpay API this project's ingest needs."""

    def __init__(self, key_id: str, key_secret: str) -> None:
        self._client = razorpay.Client(
            auth=(key_id, key_secret), max_retries=4, initial_delay=1, max_delay=30, jitter=0.25
        )
        self._client.enable_retry(True)

    def create_order(self, amount_paise: int, receipt: str, notes: dict[str, Any] | None = None) -> dict:
        return _with_backoff(
            lambda: self._client.order.create(
                data={"amount": amount_paise, "currency": "INR", "receipt": receipt, "notes": notes or {}}
            )
        )

    def fetch_payments_for_order(self, order_id: str) -> list[dict]:
        response = _with_backoff(lambda: self._client.order.payments(order_id))
        return response["items"]

    def capture_payment(self, payment_id: str, amount_paise: int) -> dict:
        return _with_backoff(lambda: self._client.payment.capture(payment_id, amount_paise))

    def create_refund(self, payment_id: str, amount_paise: int) -> dict:
        return _with_backoff(lambda: self._client.payment.refund(payment_id, data={"amount": amount_paise}))
