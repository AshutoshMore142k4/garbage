import pytest
from razorpay.errors import BadRequestError, GatewayError, ServerError

from ledgerguard.razorpay.client import MAX_RETRIES, _with_backoff


def test_returns_result_on_success():
    assert _with_backoff(lambda: 42) == 42


def test_retries_server_error_then_succeeds(monkeypatch):
    monkeypatch.setattr("ledgerguard.razorpay.client.time.sleep", lambda _seconds: None)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ServerError("temporarily unavailable")
        return "ok"

    assert _with_backoff(flaky) == "ok"
    assert calls["n"] == 3


def test_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr("ledgerguard.razorpay.client.time.sleep", lambda _seconds: None)
    calls = {"n": 0}

    def always_fails():
        calls["n"] += 1
        raise GatewayError("still down")

    with pytest.raises(GatewayError):
        _with_backoff(always_fails)

    assert calls["n"] == MAX_RETRIES + 1


def test_does_not_retry_bad_request_error(monkeypatch):
    monkeypatch.setattr("ledgerguard.razorpay.client.time.sleep", lambda _seconds: None)
    calls = {"n": 0}

    def bad_request():
        calls["n"] += 1
        raise BadRequestError("invalid amount")

    with pytest.raises(BadRequestError):
        _with_backoff(bad_request)

    assert calls["n"] == 1
