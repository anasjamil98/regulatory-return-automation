-- Staging view. Every line of the return reads from here, never from the raw table.
--
-- Three decisions live in this one place so no report can make them differently:
--   1. Reporting date is LOCAL time (UTC+3). The raw timestamp is UTC.
--   2. Internal test accounts are excluded.
--   3. Amounts stay in minor units (integers) until the very last step, so
--      totals reconcile exactly instead of to within a rounding error.
--
-- It's a TEMP view because the pipeline opens the source database read-only.

CREATE TEMP VIEW stg_transactions AS
SELECT
    t.txn_id,
    t.txn_ts                       AS txn_ts_utc,
    date(t.txn_ts, '+3 hours')     AS local_date,
    t.customer_id,
    t.txn_type,
    t.amount_minor,
    t.fee_minor,
    t.status
FROM transactions AS t
JOIN customers    AS c ON c.customer_id = t.customer_id
WHERE c.is_test_account = 0;
