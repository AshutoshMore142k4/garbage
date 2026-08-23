import sqlite3

import pytest

from ledgerguard.db import TABLE_NAMES, init_db


def test_all_tables_created(tmp_path):
    conn = init_db(tmp_path / "ledgerguard.db")
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        names = {row[0] for row in rows}
        for table in TABLE_NAMES:
            assert table in names
    finally:
        conn.close()


def test_idempotency_key_unique_constraint_enforced(tmp_path):
    conn = init_db(tmp_path / "ledgerguard.db")
    try:
        row = (
            "d1", "batch-1", "bl-1", "L1_RULE", None, None, None,
            None, None, None, "AUTO_POST", None, "[]", "idem-1", "2026-08-22T00:00:00Z",
        )
        conn.execute(
            "INSERT INTO match_decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row
        )
        conn.commit()

        duplicate = ("d2",) + row[1:]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO match_decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                duplicate,
            )
    finally:
        conn.close()
