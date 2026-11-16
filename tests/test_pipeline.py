import datetime as dt
import json
import sqlite3

from openpyxl import load_workbook

from return_pipeline.build import BLOCKED, RELEASED, RELEASED_WITH_WARNINGS, run
from return_pipeline.period import Period

NOW = dt.datetime(2025, 7, 2, 9, 0, 0)
REAL_CUSTOMER = "customer_id NOT IN (SELECT customer_id FROM customers WHERE is_test_account = 1)"


def failed_checks(manifest):
    return {c["name"] for c in manifest["checks"] if not c["passed"]}


# ---- periods ---------------------------------------------------------------

def test_period_bounds():
    june = Period.parse("2025-06")
    assert (june.start.isoformat(), june.end.isoformat(), june.days) == ("2025-06-01", "2025-07-01", 30)
    assert Period.parse("2025-12").end.isoformat() == "2026-01-01"
    assert Period.parse("2025-01").previous().label == "2024-12"


def test_utc_bounds_shift_by_the_offset():
    # Local midnight on 1 June is 21:00 UTC on 31 May.
    assert Period.parse("2025-06").utc_bounds() == ("2025-05-31 21:00:00", "2025-06-30 21:00:00")


# ---- a clean run -----------------------------------------------------------

def test_clean_period_is_released(clean_db, tmp_path):
    manifest = run(clean_db, "2025-06", tmp_path, variance_threshold=10.0, now=NOW)
    assert manifest["status"] == RELEASED
    assert failed_checks(manifest) == set()
    assert (tmp_path / manifest["output"]["file"]).exists()


def test_workbook_matches_manifest(clean_db, tmp_path):
    manifest = run(clean_db, "2025-06", tmp_path, variance_threshold=10.0, now=NOW)
    ws = load_workbook(str(tmp_path / manifest["output"]["file"]))["PS-M1"]
    on_form = {row[0]: row for row in ws.iter_rows(values_only=True) if row[0] in manifest["lines"]}
    for code, line in manifest["lines"].items():
        assert on_form[code][2] == line["count"]
        if line["value_minor"] is not None:
            assert round(on_form[code][3] * 100) == line["value_minor"]


def test_return_agrees_with_a_row_by_row_recount(clean_db, tmp_path):
    """Recount June in plain Python, reading the raw table, and compare."""
    manifest = run(clean_db, "2025-06", tmp_path, variance_threshold=10.0, now=NOW)
    con = sqlite3.connect(str(clean_db))
    test_accounts = {r[0] for r in con.execute("SELECT customer_id FROM customers WHERE is_test_account = 1")}
    count = value = 0
    for ts, customer_id, amount, status in con.execute(
        "SELECT txn_ts, customer_id, amount_minor, status FROM transactions"
    ):
        local = dt.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S") + dt.timedelta(hours=3)
        if local.year == 2025 and local.month == 6 and status == "success" and customer_id not in test_accounts:
            count += 1
            value += amount
    con.close()
    assert manifest["lines"]["B9"] == {"count": count, "value_minor": value}


def test_same_inputs_give_same_numbers(clean_db, tmp_path):
    first = run(clean_db, "2025-06", tmp_path / "a", now=NOW)
    second = run(clean_db, "2025-06", tmp_path / "b", now=NOW)
    assert first["lines"] == second["lines"]
    assert first["inputs"] == second["inputs"]


def test_first_period_has_nothing_to_compare_against(clean_db, tmp_path):
    manifest = run(clean_db, "2025-01", tmp_path, now=NOW)
    assert manifest["inputs"]["prior_period"] is None
    assert manifest["status"] == RELEASED


# ---- warnings travel with the return --------------------------------------

def test_large_movement_is_released_with_a_warning(clean_db, tmp_path):
    manifest = run(clean_db, "2025-06", tmp_path, variance_threshold=0.0001, now=NOW)
    assert manifest["status"] == RELEASED_WITH_WARNINGS
    assert failed_checks(manifest) == {"variance_vs_prior_period"}
    assert manifest["output"] is not None


# ---- broken inputs are blocked --------------------------------------------

def test_missing_day_blocks_the_return(broken_db, tmp_path):
    db = broken_db("DELETE FROM transactions WHERE date(txn_ts, '+3 hours') = '2025-06-14'")
    manifest = run(db, "2025-06", tmp_path, now=NOW)
    assert manifest["status"] == BLOCKED
    assert "every_day_present" in failed_checks(manifest)
    assert manifest["output"] is None
    assert not list(tmp_path.glob("*.xlsx"))


def test_unknown_status_blocks_the_return(broken_db, tmp_path):
    db = broken_db(
        "UPDATE transactions SET status = 'pending' WHERE txn_id IN "
        f"(SELECT txn_id FROM transactions WHERE date(txn_ts, '+3 hours') = '2025-06-10' AND {REAL_CUSTOMER} LIMIT 3)"
    )
    manifest = run(db, "2025-06", tmp_path, now=NOW)
    assert manifest["status"] == BLOCKED
    assert {"status_domain", "status_reconciliation"} <= failed_checks(manifest)


def test_duplicate_rows_block_the_return(broken_db, tmp_path):
    # Rebuild the table without its primary key, the way a warehouse table usually is.
    db = broken_db(
        "CREATE TABLE t2 AS SELECT * FROM transactions",
        "DROP TABLE transactions",
        "ALTER TABLE t2 RENAME TO transactions",
        "INSERT INTO transactions SELECT * FROM transactions "
        "WHERE date(txn_ts, '+3 hours') = '2025-06-20' LIMIT 5",
    )
    manifest = run(db, "2025-06", tmp_path, now=NOW)
    assert manifest["status"] == BLOCKED
    assert "unique_transaction_ids" in failed_checks(manifest)


def test_negative_amount_blocks_the_return(broken_db, tmp_path):
    db = broken_db(
        "UPDATE transactions SET amount_minor = -500 WHERE txn_id = "
        f"(SELECT MIN(txn_id) FROM transactions WHERE date(txn_ts, '+3 hours') = '2025-06-05' AND {REAL_CUSTOMER})"
    )
    manifest = run(db, "2025-06", tmp_path, now=NOW)
    assert manifest["status"] == BLOCKED
    assert "amounts_valid" in failed_checks(manifest)


def test_blocked_run_still_leaves_a_manifest(broken_db, tmp_path):
    db = broken_db("DELETE FROM transactions WHERE date(txn_ts, '+3 hours') = '2025-06-14'")
    run(db, "2025-06", tmp_path, now=NOW)
    manifest = json.loads((tmp_path / "PS-M1_2025-06_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == BLOCKED


# ---- the source is never modified -----------------------------------------

def test_source_database_is_untouched(clean_db, tmp_path):
    before = clean_db.read_bytes()
    run(clean_db, "2025-06", tmp_path, now=NOW)
    assert clean_db.read_bytes() == before
