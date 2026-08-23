"""Orchestrates Razorpay test-mode ingest (plan.md #12, phases.md Phase 2).

Honest scope note: creating orders is a pure server-side API call and is fully automated here.
Getting an order to a *captured* payment in Razorpay test mode still requires completing checkout
with a test card (a client-facing action, per Razorpay's own documented test-mode flow -- see
docs/razorpay-verification.md) -- there is no documented server-only "create a captured payment"
endpoint. So `fetch_captured_payments` here reads back payments that were already captured through
that checkout step; it does not fabricate them. This module has not been run against a live
Razorpay account in this session -- no credentials were available and network egress to
razorpay.com was blocked (see PROGRESS.md / BROKE.md, Phase 0).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ledgerguard.config import get_settings
from ledgerguard.models import Order, Payment, Refund
from ledgerguard.razorpay.client import RazorpayClient


def _epoch_to_iso(epoch_seconds: int) -> str:
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_test_orders(client: RazorpayClient, amounts_paise: list[int], receipt_prefix: str) -> list[Order]:
    orders = []
    for i, amount in enumerate(amounts_paise):
        raw = client.create_order(amount, receipt=f"{receipt_prefix}-{i}")
        orders.append(
            Order(
                id=raw["id"],
                amount_paise=raw["amount"],
                currency=raw["currency"],
                created_at=_epoch_to_iso(raw["created_at"]),
                source="razorpay_test_mode",
            )
        )
    return orders


def fetch_captured_payments(client: RazorpayClient, order_ids: list[str]) -> list[Payment]:
    payments = []
    for order_id in order_ids:
        for raw in client.fetch_payments_for_order(order_id):
            if raw.get("status") != "captured":
                continue
            payments.append(
                Payment(
                    id=raw["id"],
                    order_id=order_id,
                    amount_paise=raw["amount"],
                    fee_paise=raw.get("fee") or 0,
                    tax_paise=raw.get("tax") or 0,
                    method=raw.get("method", "unknown"),
                    status=raw["status"],
                    captured_at=_epoch_to_iso(raw["created_at"]),
                )
            )
    return payments


def create_partial_refunds(client: RazorpayClient, refund_plan: dict[str, int]) -> list[Refund]:
    refunds = []
    for payment_id, amount_paise in refund_plan.items():
        raw = client.create_refund(payment_id, amount_paise)
        refunds.append(
            Refund(
                id=raw["id"],
                payment_id=payment_id,
                amount_paise=raw["amount"],
                created_at=_epoch_to_iso(raw["created_at"]),
            )
        )
    return refunds


def persist_raw(orders: list[Order], payments: list[Payment], refunds: list[Refund], out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "orders.json").write_text(
        json.dumps([o.model_dump() for o in orders], indent=2, sort_keys=True), encoding="utf-8"
    )
    (out_dir / "payments.json").write_text(
        json.dumps([p.model_dump() for p in payments], indent=2, sort_keys=True), encoding="utf-8"
    )
    (out_dir / "refunds.json").write_text(
        json.dumps([r.model_dump() for r in refunds], indent=2, sort_keys=True), encoding="utf-8"
    )


def main() -> None:
    settings = get_settings()
    client = RazorpayClient(settings.razorpay_key_id, settings.razorpay_key_secret)

    amounts = [10_000 * (i + 1) for i in range(20)]
    orders = create_test_orders(client, amounts, receipt_prefix="ledgerguard")
    payments = fetch_captured_payments(client, [o.id for o in orders])
    refund_plan = {p.id: p.amount_paise // 4 for p in payments[:5]}
    refunds = create_partial_refunds(client, refund_plan)

    persist_raw(orders, payments, refunds, Path("data/raw"))
    print(f"Ingested {len(orders)} orders, {len(payments)} captured payments, {len(refunds)} refunds.")
    if not payments:
        print(
            "No captured payments found. Test-mode payments must be captured via checkout with a "
            "test card first -- see this module's docstring."
        )


if __name__ == "__main__":
    main()
