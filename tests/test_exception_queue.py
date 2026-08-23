from ledgerguard.l3_calibrate_gate.exception_queue import ExceptionQueueEntry, build_exception_queue


def test_build_exception_queue_ranks_by_amount_at_risk_descending():
    entries = [
        ExceptionQueueEntry("bl_1", amount_paise=1_000, reason_code="NO_CANDIDATE_FOUND", calibrated_confidence=0.1, evidence=["a"]),
        ExceptionQueueEntry("bl_2", amount_paise=50_000, reason_code="AMBIGUOUS_NARRATION_MULTI_CANDIDATE", calibrated_confidence=0.6, evidence=["b"]),
        ExceptionQueueEntry("bl_3", amount_paise=10_000, reason_code="SUBSET_SUM_OVER_BUDGET", calibrated_confidence=0.0, evidence=["c"]),
    ]

    ranked = build_exception_queue(entries)

    assert [e.bank_line_id for e in ranked] == ["bl_2", "bl_3", "bl_1"]


def test_build_exception_queue_every_entry_has_evidence_and_reason_code():
    entries = [
        ExceptionQueueEntry("bl_1", amount_paise=1_000, reason_code="NO_CANDIDATE_FOUND", calibrated_confidence=0.1, evidence=["why"]),
    ]

    ranked = build_exception_queue(entries)

    assert ranked[0].reason_code
    assert ranked[0].evidence
