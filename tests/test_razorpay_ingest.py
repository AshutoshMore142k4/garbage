import json

from ledgerguard.razorpay.ingest import (
    create_partial_refunds,
    create_test_orders,
    fetch_captured_payments,
    persist_raw,
)


class FakeRazorpayClient:
    """Duck-typed stand-in for RazorpayClient -- no real network access."""

    def __init__(self):
        self.created_orders = []
        self.created_refunds = []

    def create_order(self, amount_paise, receipt, notes=None):
        order_id = f"order_fake_{len(self.created_orders)}"
        self.created_orders.append((amount_paise, receipt))
        return {"id": order_id, "amount": amount_paise, "currency": "INR", "created_at": 1735689600}

    def fetch_payments_for_order(self, order_id):
        return [
            {
                "id": f"pay_fake_{order_id}",
                "amount": 50000,
                "fee": 1000,
                "tax": 180,
                "method": "upi",
                "status": "captured",
                "created_at": 1735689660,
            },
            {
                "id": f"pay_failed_{order_id}",
                "amount": 50000,
                "status": "failed",
                "created_at": 1735689660,
            },
        ]

    def create_refund(self, payment_id, amount_paise):
        self.created_refunds.append((payment_id, amount_paise))
        return {"id": f"rfnd_fake_{payment_id}", "amount": amount_paise, "created_at": 1735776000}


def test_create_test_orders_maps_sdk_response_to_order_model():
    client = FakeRazorpayClient()

    orders = create_test_orders(client, [10_000, 20_000], receipt_prefix="test")

    assert len(orders) == 2
    assert orders[0].amount_paise == 10_000
    assert orders[0].currency == "INR"
    assert orders[0].source == "razorpay_test_mode"
    assert orders[0].created_at == "2025-01-01T00:00:00Z"
    assert client.created_orders == [(10_000, "test-0"), (20_000, "test-1")]


def test_fetch_captured_payments_filters_out_non_captured():
    client = FakeRazorpayClient()

    payments = fetch_captured_payments(client, ["order_1"])

    assert len(payments) == 1
    assert payments[0].status == "captured"
    assert payments[0].fee_paise == 1000
    assert payments[0].tax_paise == 180


def test_create_partial_refunds_maps_sdk_response_to_refund_model():
    client = FakeRazorpayClient()

    refunds = create_partial_refunds(client, {"pay_1": 5000})

    assert len(refunds) == 1
    assert refunds[0].payment_id == "pay_1"
    assert refunds[0].amount_paise == 5000
    assert client.created_refunds == [("pay_1", 5000)]


def test_persist_raw_writes_sorted_json(tmp_path):
    client = FakeRazorpayClient()
    orders = create_test_orders(client, [10_000], receipt_prefix="test")
    payments = fetch_captured_payments(client, [orders[0].id])
    refunds = create_partial_refunds(client, {payments[0].id: 1000})

    persist_raw(orders, payments, refunds, tmp_path)

    saved_orders = json.loads((tmp_path / "orders.json").read_text())
    saved_payments = json.loads((tmp_path / "payments.json").read_text())
    saved_refunds = json.loads((tmp_path / "refunds.json").read_text())
    assert saved_orders[0]["id"] == orders[0].id
    assert saved_payments[0]["id"] == payments[0].id
    assert saved_refunds[0]["id"] == refunds[0].id
