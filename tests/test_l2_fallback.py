from ledgerguard.l2_llm_triage.fallback import fallback_triage


def test_fallback_resolves_single_plausible_candidate():
    candidates = [{"payment_id": "pay_1", "order_id": "order_1", "net_paise": 50000, "captured_at": "x"}]
    response = fallback_triage("RZPX*ACMEENTERP7F3A2C", candidates)
    assert response.candidate_id == "pay_1"
    assert 0 < response.confidence <= 0.6


def test_fallback_abstains_with_no_candidates():
    response = fallback_triage("RZPX*ACMEENTERP7F3A2C", [])
    assert response.candidate_id is None


def test_fallback_abstains_when_narration_implausible():
    candidates = [{"payment_id": "pay_1", "order_id": "order_1", "net_paise": 50000, "captured_at": "x"}]
    response = fallback_triage("ZZZQQQXXX999", candidates)
    assert response.candidate_id is None


def test_fallback_abstains_with_multiple_candidates():
    candidates = [
        {"payment_id": "pay_1", "order_id": "order_1", "net_paise": 50000, "captured_at": "x"},
        {"payment_id": "pay_2", "order_id": "order_2", "net_paise": 50000, "captured_at": "y"},
    ]
    response = fallback_triage("RZPX*ACMEENTERP7F3A2C", candidates)
    assert response.candidate_id is None
