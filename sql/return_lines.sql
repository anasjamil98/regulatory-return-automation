-- Form PS-M1 (fictional): Monthly Payment Systems Return.
-- One row per return line: line_code, txn_count, value_minor.
-- Parameters: :period_start (inclusive) and :period_end (exclusive), local dates.

WITH period AS (
    SELECT *
    FROM stg_transactions
    WHERE local_date >= :period_start
      AND local_date <  :period_end
),
real_customers AS (
    SELECT customer_id, signup_date
    FROM customers
    WHERE is_test_account = 0
)

-- Section A: customer accounts (a count of customers, no value)
SELECT 'A1' AS line_code, COUNT(*) AS txn_count, NULL AS value_minor
FROM real_customers
WHERE signup_date < :period_end

UNION ALL
SELECT 'A2', COUNT(*), NULL
FROM real_customers
WHERE signup_date >= :period_start
  AND signup_date <  :period_end

UNION ALL
SELECT 'A3', COUNT(DISTINCT customer_id), NULL
FROM period
WHERE status = 'success'

-- Section B: successful transactions by type
UNION ALL
SELECT
    CASE txn_type
        WHEN 'p2p_transfer'     THEN 'B1'
        WHEN 'merchant_payment' THEN 'B2'
        WHEN 'card_payment'     THEN 'B3'
        WHEN 'bill_payment'     THEN 'B4'
        WHEN 'cash_in'          THEN 'B5'
        WHEN 'cash_out'         THEN 'B6'
    END,
    COUNT(*),
    SUM(amount_minor)
FROM period
WHERE status = 'success'
GROUP BY txn_type

UNION ALL
SELECT 'B9', COUNT(*), COALESCE(SUM(amount_minor), 0)
FROM period
WHERE status = 'success'

-- Section C: transactions that did not complete
UNION ALL
SELECT 'C1', COUNT(*), COALESCE(SUM(amount_minor), 0)
FROM period
WHERE status = 'failed'

UNION ALL
SELECT 'C2', COUNT(*), COALESCE(SUM(amount_minor), 0)
FROM period
WHERE status = 'reversed'

-- Section D: fees charged on successful transactions
UNION ALL
SELECT 'D1', COALESCE(SUM(fee_minor > 0), 0), COALESCE(SUM(fee_minor), 0)
FROM period
WHERE status = 'success';
