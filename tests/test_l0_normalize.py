from datetime import timezone

from ledgerguard.l0_normalize.normalize import (
    normalize_amount_paise,
    normalize_bank_line,
    normalize_narration,
    normalize_timestamp,
)


def test_normalize_amount_paise_accepts_int_and_str():
    assert normalize_amount_paise(1000) == 1000
    assert normalize_amount_paise("1000") == 1000


def test_normalize_timestamp_parses_utc_z_suffix():
    dt = normalize_timestamp("2026-01-05T00:00:00Z")
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2026 and dt.month == 1 and dt.day == 5


def test_normalize_narration_uppercases_strips_prefix_and_collapses_whitespace():
    assert normalize_narration("rzpx*acmeenterp7f3a2c") == "ACMEENTERP7F3A2C"
    assert normalize_narration("  NEFT-  some   merchant  ") == "SOME MERCHANT"


def test_normalize_narration_leaves_unprefixed_text_alone_but_cleans_it():
    assert normalize_narration("Random   Text") == "RANDOM TEXT"


def test_normalize_bank_line_from_csv_style_row():
    row = {
        "id": "bl_1",
        "utr": "",
        "credit_paise": "50000",
        "narration": "RZPX*ACMEENTERP123",
        "value_date": "2026-01-07T00:00:00Z",
    }
    bl = normalize_bank_line(row)
    assert bl.id == "bl_1"
    assert bl.utr is None
    assert bl.credit_paise == 50000
    assert bl.narration == "ACMEENTERP123"
