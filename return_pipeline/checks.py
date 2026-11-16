"""Controls that run before a return is released.

A check is either a FAIL (the return is not produced) or a WARN (the return is
produced, and the warning travels with it so whoever files it sees it).

The rule for choosing: FAIL means the numbers are wrong or can't be trusted.
WARN means the numbers may well be right but a person should look before
signing, e.g. a line that moved a lot since last month.
"""

from dataclasses import dataclass, asdict

from .lines import KNOWN_STATUSES, RETURN_LINES, TYPE_LINES

FAIL = "fail"
WARN = "warn"


@dataclass
class CheckResult:
    name: str
    severity: str
    passed: bool
    detail: str

    def to_dict(self):
        return asdict(self)


def _scalar(con, sql, params=()):
    return con.execute(sql, params).fetchone()[0]


def check_line_set(lines):
    got, expected = set(lines), set(RETURN_LINES)
    missing, extra = sorted(expected - got), sorted(got - expected)
    # A type with no successful transactions legitimately produces no row.
    missing = [code for code in missing if code not in TYPE_LINES]
    ok = not missing and not extra
    detail = "all lines present" if ok else f"missing={missing} unexpected={extra}"
    return CheckResult("line_set", FAIL, ok, detail)


def check_every_day_present(con, period):
    """A missing day usually means a load didn't run, not that nobody paid."""
    days = _scalar(
        con,
        "SELECT COUNT(DISTINCT local_date) FROM stg_transactions "
        "WHERE local_date >= :period_start AND local_date < :period_end",
        period.sql_params(),
    )
    ok = days == period.days
    return CheckResult("every_day_present", FAIL, ok, f"{days} of {period.days} days have transactions")


def check_unique_ids(con, period):
    start, end = period.utc_bounds()
    total, distinct = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT txn_id) FROM transactions WHERE txn_ts >= ? AND txn_ts < ?",
        (start, end),
    ).fetchone()
    return CheckResult("unique_transaction_ids", FAIL, total == distinct, f"{total} rows, {distinct} distinct ids")


def check_status_domain(con, period):
    """An unknown status would silently drop out of every section."""
    placeholders = ",".join("?" for _ in KNOWN_STATUSES)
    params = period.sql_params()
    unknown = _scalar(
        con,
        "SELECT COUNT(*) FROM stg_transactions WHERE local_date >= ? AND local_date < ? "
        f"AND status NOT IN ({placeholders})",
        (params["period_start"], params["period_end"]) + KNOWN_STATUSES,
    )
    return CheckResult("status_domain", FAIL, unknown == 0, f"{unknown} rows with an unrecognised status")


def check_amounts_valid(con, period):
    bad = _scalar(
        con,
        "SELECT COUNT(*) FROM stg_transactions "
        "WHERE local_date >= :period_start AND local_date < :period_end "
        "AND (amount_minor IS NULL OR amount_minor <= 0 OR fee_minor IS NULL OR fee_minor < 0)",
        period.sql_params(),
    )
    return CheckResult("amounts_valid", FAIL, bad == 0, f"{bad} rows with a missing, zero or negative amount")


def check_control_total(con, period, lines):
    """Recompute the headline total by a second route and compare.

    The return goes: raw table -> staging view (local date) -> SQL.
    This goes: raw table, UTC bounds worked out in Python, no view.
    If the timezone handling or the test-account filter is wrong in one path,
    the two disagree.
    """
    start, end = period.utc_bounds()
    count, value = con.execute(
        "SELECT COUNT(*), COALESCE(SUM(amount_minor), 0) FROM transactions "
        "WHERE txn_ts >= ? AND txn_ts < ? AND status = 'success' "
        "AND customer_id NOT IN (SELECT customer_id FROM customers WHERE is_test_account = 1)",
        (start, end),
    ).fetchone()
    line_count, line_value = lines["B9"]
    ok = (count, value) == (line_count, line_value)
    detail = f"return: {line_count} txns / {line_value} minor; independent: {count} txns / {value} minor"
    return CheckResult("control_total", FAIL, ok, detail)


def check_types_sum_to_total(lines):
    count = sum(lines[code][0] for code in TYPE_LINES if code in lines)
    value = sum(lines[code][1] for code in TYPE_LINES if code in lines)
    ok = (count, value) == tuple(lines["B9"])
    return CheckResult("type_lines_sum_to_total", FAIL, ok, f"types: {count} / {value}; total line: {lines['B9']}")


def check_status_reconciliation(con, period, lines):
    """Successful + failed + reversed must account for every row in the period."""
    all_rows = _scalar(
        con,
        "SELECT COUNT(*) FROM stg_transactions WHERE local_date >= :period_start AND local_date < :period_end",
        period.sql_params(),
    )
    reported = lines["B9"][0] + lines["C1"][0] + lines["C2"][0]
    return CheckResult("status_reconciliation", FAIL, all_rows == reported, f"{reported} reported of {all_rows} rows")


def check_customer_counts(lines):
    registered, new, active = lines["A1"][0], lines["A2"][0], lines["A3"][0]
    ok = new <= registered and active <= registered
    return CheckResult("customer_counts_consistent", FAIL, ok, f"registered={registered} new={new} active={active}")


def check_no_test_accounts(con):
    leaked = _scalar(
        con,
        "SELECT COUNT(*) FROM stg_transactions s JOIN customers c ON c.customer_id = s.customer_id "
        "WHERE c.is_test_account = 1",
    )
    return CheckResult("test_accounts_excluded", FAIL, leaked == 0, f"{leaked} test-account rows in staging")


def variance_table(lines, prior_lines):
    """Each line against the prior period: (code, measure, current, prior, change)."""
    rows = []
    for code, (_, _, has_value) in RETURN_LINES.items():
        if code not in lines:
            continue
        measures = [("count", 0)] + ([("value", 1)] if has_value else [])
        for measure, idx in measures:
            current = lines[code][idx]
            prior = prior_lines.get(code, (None, None))[idx] if prior_lines else None
            change = None if not prior else (current - prior) / prior
            rows.append((code, measure, current, prior, change))
    return rows


def check_variance(variance_rows, threshold, has_prior):
    if not has_prior:
        return CheckResult("variance_vs_prior_period", WARN, True, "no prior period data to compare against")
    moved = [
        f"{code} {measure} {change:+.1%}"
        for code, measure, _, _, change in variance_rows
        if change is not None and abs(change) > threshold
    ]
    detail = "; ".join(moved) if moved else f"no line moved more than {threshold:.0%}"
    return CheckResult("variance_vs_prior_period", WARN, not moved, detail)


def run_all(con, period, lines, prior_lines, variance_rows, threshold):
    results = [check_line_set(lines)]
    if not results[0].passed:
        return results  # nothing below is meaningful without the full line set
    results += [
        check_every_day_present(con, period),
        check_unique_ids(con, period),
        check_status_domain(con, period),
        check_amounts_valid(con, period),
        check_control_total(con, period, lines),
        check_types_sum_to_total(lines),
        check_status_reconciliation(con, period, lines),
        check_customer_counts(lines),
        check_no_test_accounts(con),
        check_variance(variance_rows, threshold, bool(prior_lines)),
    ]
    return results
