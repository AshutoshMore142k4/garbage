import socket
from pathlib import Path

import pytest

from ledgerguard.l1_deterministic.matcher import load_bank_lines, load_ledger_payments, run_l1

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"


def _blocked_connect(*args, **kwargs):
    raise AssertionError("L0/L1 must never open a network connection")


def test_l1_pipeline_makes_no_network_call(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)

    bank_lines = load_bank_lines(SAMPLES_DIR / "bank_statement.csv")
    payments = load_ledger_payments(SAMPLES_DIR / "internal_ledger.csv")

    results = run_l1(bank_lines, payments)

    assert len(results) == len(bank_lines)
