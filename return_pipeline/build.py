"""Runs one reporting period end to end: SQL -> checks -> workbook -> manifest."""

import datetime as dt
import hashlib
import json
import sqlite3
from pathlib import Path

from . import __version__, checks
from .excel import write_workbook
from .period import Period

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"

RELEASED = "released"
RELEASED_WITH_WARNINGS = "released_with_warnings"
BLOCKED = "blocked"


def sha256_of(path):
    digest = hashlib.sha256()
    with open(str(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def connect_read_only(db_path):
    """The pipeline can't change the source data even by accident."""
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.executescript((SQL_DIR / "stg_transactions.sql").read_text(encoding="utf-8"))
    return con


def compute_lines(con, period):
    sql = (SQL_DIR / "return_lines.sql").read_text(encoding="utf-8")
    return {code: (count, value) for code, count, value in con.execute(sql, period.sql_params())}


def has_data(con, period):
    row = con.execute(
        "SELECT 1 FROM stg_transactions WHERE local_date >= :period_start AND local_date < :period_end LIMIT 1",
        period.sql_params(),
    ).fetchone()
    return row is not None


def run(db_path, period_text, out_dir, variance_threshold=0.25, now=None):
    """Build the return for one period. Returns the manifest as a dict.

    The manifest is always written, including for a blocked run: a record of
    what was stopped and why is as useful as a record of what went out.
    """
    period = Period.parse(period_text)
    now = now or dt.datetime.utcnow()
    generated_at = now.strftime("%Y-%m-%d %H:%M:%S")
    run_id = f"PS-M1-{period.label}-{now.strftime('%Y%m%dT%H%M%S')}"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    con = connect_read_only(db_path)
    try:
        lines = compute_lines(con, period)
        prior = period.previous()
        prior_lines = compute_lines(con, prior) if has_data(con, prior) else {}
        variance_rows = checks.variance_table(lines, prior_lines)
        results = checks.run_all(con, period, lines, prior_lines, variance_rows, variance_threshold)
    finally:
        con.close()

    failed = [r for r in results if not r.passed and r.severity == checks.FAIL]
    warned = [r for r in results if not r.passed and r.severity == checks.WARN]
    status = BLOCKED if failed else (RELEASED_WITH_WARNINGS if warned else RELEASED)

    output = None
    if status != BLOCKED:
        workbook_path = out_dir / f"PS-M1_{period.label}.xlsx"
        write_workbook(workbook_path, period, run_id, generated_at, lines, variance_rows, results, variance_threshold)
        output = {"file": workbook_path.name, "sha256": sha256_of(workbook_path)}

    manifest = {
        "run_id": run_id,
        "form": "PS-M1 (fictional)",
        "period": period.label,
        "status": status,
        "generated_at_utc": generated_at,
        "pipeline_version": __version__,
        "inputs": {
            "database_sha256": sha256_of(db_path),
            "sql_sha256": {p.name: sha256_of(p) for p in sorted(SQL_DIR.glob("*.sql"))},
            "variance_threshold": variance_threshold,
            "prior_period": prior.label if prior_lines else None,
        },
        "lines": {code: {"count": count, "value_minor": value} for code, (count, value) in sorted(lines.items())},
        "checks": [r.to_dict() for r in results],
        "output": output,
    }
    manifest_path = out_dir / f"PS-M1_{period.label}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
