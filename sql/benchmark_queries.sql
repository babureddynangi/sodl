-- Benchmark query set for SODL MVP partition advisor experiment.
-- All 25 queries filter primarily on merchant_category and/or region.
-- On the BASELINE (date-partitioned) table, Athena must scan ALL partitions.
-- On the OPTIMIZED (merchant_category-partitioned) table, partition pruning applies.
--
-- Usage: run_benchmark.py substitutes {TABLE} with the actual table name.

-- Q01: Total spend by merchant category (full scan test)
SELECT merchant_category, SUM(amount) AS total_spend, COUNT(*) AS txn_count
FROM {TABLE}
WHERE merchant_category IN ('retail', 'dining')
GROUP BY merchant_category
ORDER BY total_spend DESC;

-- Q02: Fraud rate by region and category
SELECT region, merchant_category,
       COUNT(*) AS total,
       SUM(CAST(is_fraud AS INTEGER)) AS fraud_count,
       AVG(CAST(is_fraud AS DOUBLE)) AS fraud_rate
FROM {TABLE}
WHERE merchant_category = 'online'
GROUP BY region, merchant_category;

-- Q03: High-value transactions in travel category
SELECT transaction_id, merchant_id, amount, region, channel
FROM {TABLE}
WHERE merchant_category = 'travel'
  AND amount > 500
ORDER BY amount DESC
LIMIT 100;

-- Q04: Monthly transaction volume (retail only)
SELECT SUBSTR(transaction_date, 1, 7) AS month,
       COUNT(*) AS txn_count,
       SUM(amount) AS total_spend
FROM {TABLE}
WHERE merchant_category = 'retail'
GROUP BY SUBSTR(transaction_date, 1, 7)
ORDER BY month;

-- Q05: Average transaction size by card type and channel (dining)
SELECT card_type, channel, AVG(amount) AS avg_amount, COUNT(*) AS count
FROM {TABLE}
WHERE merchant_category = 'dining'
GROUP BY card_type, channel
ORDER BY avg_amount DESC;

-- Q06: Fraud detection — suspicious high-amount online transactions
SELECT customer_id, COUNT(*) AS fraud_txns, SUM(amount) AS total_fraud_amount
FROM {TABLE}
WHERE merchant_category = 'online'
  AND is_fraud = TRUE
  AND amount > 200
GROUP BY customer_id
HAVING COUNT(*) > 1
ORDER BY total_fraud_amount DESC
LIMIT 50;

-- Q07: Region comparison for utilities spend
SELECT region, SUM(amount) AS total, AVG(amount) AS avg_amount
FROM {TABLE}
WHERE merchant_category = 'utilities'
GROUP BY region
ORDER BY total DESC;

-- Q08: Customer segmentation by account age (healthcare)
SELECT
  CASE WHEN account_age_days < 365 THEN 'new'
       WHEN account_age_days < 1095 THEN 'mid'
       ELSE 'established' END AS segment,
  COUNT(*) AS txn_count,
  AVG(amount) AS avg_spend
FROM {TABLE}
WHERE merchant_category = 'healthcare'
GROUP BY 1;

-- Q09: Currency distribution for entertainment
SELECT currency, COUNT(*) AS txn_count, SUM(amount) AS total_amount
FROM {TABLE}
WHERE merchant_category = 'entertainment'
GROUP BY currency
ORDER BY txn_count DESC;

-- Q10: Top merchants by transaction volume (groceries)
SELECT merchant_id, COUNT(*) AS txn_count, SUM(amount) AS total
FROM {TABLE}
WHERE merchant_category = 'groceries'
GROUP BY merchant_id
ORDER BY txn_count DESC
LIMIT 20;

-- Q11: Multi-category fraud pattern
SELECT merchant_category, region,
       SUM(CAST(is_fraud AS INTEGER)) AS fraud_count,
       COUNT(*) AS total
FROM {TABLE}
WHERE merchant_category IN ('fuel', 'financial')
GROUP BY merchant_category, region;

-- Q12: ATM transaction analysis
SELECT region, merchant_category, SUM(amount) AS total
FROM {TABLE}
WHERE channel = 'atm'
  AND merchant_category IN ('retail', 'groceries', 'fuel')
GROUP BY region, merchant_category
ORDER BY total DESC;

-- Q13: High-value customer analysis (travel + healthcare)
SELECT customer_id, SUM(amount) AS lifetime_value
FROM {TABLE}
WHERE merchant_category IN ('travel', 'healthcare')
GROUP BY customer_id
HAVING SUM(amount) > 1000
ORDER BY lifetime_value DESC
LIMIT 100;

-- Q14: Daily transaction trend for online category
SELECT transaction_date, COUNT(*) AS txn_count, SUM(amount) AS daily_spend
FROM {TABLE}
WHERE merchant_category = 'online'
GROUP BY transaction_date
ORDER BY transaction_date;

-- Q15: Prepaid card usage patterns
SELECT merchant_category, COUNT(*) AS txn_count, SUM(amount) AS total
FROM {TABLE}
WHERE card_type = 'prepaid'
  AND merchant_category IN ('retail', 'dining', 'online')
GROUP BY merchant_category
ORDER BY total DESC;

-- Q16: Cross-region spend comparison (entertainment)
SELECT region, SUM(amount) AS total_spend,
       COUNT(DISTINCT customer_id) AS unique_customers
FROM {TABLE}
WHERE merchant_category = 'entertainment'
GROUP BY region;

-- Q17: Fraud risk score by channel (financial category)
SELECT channel,
       COUNT(*) AS total_txns,
       SUM(CAST(is_fraud AS INTEGER)) AS fraud_count,
       ROUND(100.0 * SUM(CAST(is_fraud AS INTEGER)) / COUNT(*), 2) AS fraud_pct
FROM {TABLE}
WHERE merchant_category = 'financial'
GROUP BY channel;

-- Q18: EUR transactions analysis
SELECT merchant_category, COUNT(*) AS count, SUM(amount) AS total
FROM {TABLE}
WHERE currency = 'EUR'
  AND merchant_category IN ('travel', 'dining', 'retail')
GROUP BY merchant_category;

-- Q19: New customer transaction patterns
SELECT merchant_category, channel, COUNT(*) AS txns, AVG(amount) AS avg_amount
FROM {TABLE}
WHERE account_age_days < 90
  AND merchant_category IN ('online', 'retail')
GROUP BY merchant_category, channel;

-- Q20: Large transaction fraud check (multi-category)
SELECT merchant_category, region, COUNT(*) AS high_value_fraud
FROM {TABLE}
WHERE amount > 1000
  AND is_fraud = TRUE
  AND merchant_category IN ('travel', 'financial', 'online')
GROUP BY merchant_category, region
ORDER BY high_value_fraud DESC;

-- Q21: Monthly fraud trend (dining)
SELECT SUBSTR(transaction_date, 1, 7) AS month,
       COUNT(*) AS fraud_count,
       SUM(amount) AS fraud_amount
FROM {TABLE}
WHERE is_fraud = TRUE
  AND merchant_category = 'dining'
GROUP BY 1
ORDER BY 1;

-- Q22: AP region high-value retail
SELECT customer_id, SUM(amount) AS total_spend
FROM {TABLE}
WHERE region IN ('ap-southeast', 'ap-northeast')
  AND merchant_category = 'retail'
  AND amount > 100
GROUP BY customer_id
ORDER BY total_spend DESC
LIMIT 50;

-- Q23: Channel efficiency for groceries
SELECT channel, COUNT(*) AS txns,
       AVG(amount) AS avg_amount,
       PERCENTILE_APPROX(amount, 0.95) AS p95_amount
FROM {TABLE}
WHERE merchant_category = 'groceries'
GROUP BY channel;

-- Q24: Debit card category spend distribution
SELECT merchant_category, SUM(amount) AS total, COUNT(*) AS txns
FROM {TABLE}
WHERE card_type = 'debit'
GROUP BY merchant_category
ORDER BY total DESC;

-- Q25: Combined fraud and spend summary (all categories, for baseline comparison)
SELECT merchant_category,
       COUNT(*) AS total_txns,
       SUM(amount) AS total_spend,
       SUM(CAST(is_fraud AS INTEGER)) AS fraud_count,
       AVG(amount) AS avg_txn,
       MAX(amount) AS max_txn
FROM {TABLE}
GROUP BY merchant_category
ORDER BY total_spend DESC;
