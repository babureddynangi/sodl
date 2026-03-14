# SODL MVP — Partition Advisor Results

**Generated**: 2026-03-14 19:54 UTC
**Benchmark runs per query**: 3
**Queries in benchmark**: 21

---

## H1 Hypothesis Check

> H1: The information-gain-optimal partition advisor reduces mean query latency
> by ≥30% relative to the migration-time partition within 30 days.

| Metric | Result |
|--------|--------|
| Mean latency reduction | **42.9%** — ✅ MET |
| Bytes scanned reduction | **85.0%** |
| H1 threshold (≥30%) | ✅ MET |

---

## Aggregate Results

| Metric | Baseline | Optimized | Δ |
|--------|----------|-----------|---|
| Mean latency (ms) | 1,421 | 812 | **−42.9%** |
| P95 latency (ms)  | 1,775 | 1,083 | — |
| Mean bytes scanned (MB) | 29.1 | 4.4 | **−85.0%** |

---

## Partition Advisor Output

| Parameter | Value |
|-----------|-------|
| Current partition key | `transaction_date` |
| Recommended key | `merchant_category` |
| Information gain delta | 1.2162 (threshold: 0.1) |
| Queries with filter on recommended key | 23/25 |

**Rationale**: Column 'merchant_category' appears in 23 of 25 queries as a filter predicate (IG score: 1.2162 vs current key 'transaction_date': 0.0000). Cardinality 10 creates 10 partitions, allowing Athena to prune partitions for ~23 queries.

---

## Per-Query Results

| Query | Label | Baseline (ms) | Optimized (ms) | Δ Latency | Baseline (MB) | Optimized (MB) | Δ Bytes |
|-------|-------|--------------|----------------|-----------|---------------|----------------|---------|
| Q01 | Total spend by merchant category (full s | 1,066 | 651 | **+38.9%** | 18.0 | 4.0 | **+77.6%** |
| Q02 | Fraud rate by region and category | 894 | 644 | **+27.9%** | 4.5 | 0.1 | **+97.7%** |
| Q03 | High-value transactions in travel catego | 1,252 | 845 | **+32.5%** | 77.5 | 7.3 | **+90.6%** |
| Q05 | Average transaction size by card type an | 1,123 | 694 | **+38.2%** | 20.5 | 2.4 | **+88.5%** |
| Q06 | Fraud detection â€” suspicious high-amou | 1,369 | 1,001 | **+26.9%** | 57.5 | 2.4 | **+95.9%** |
| Q07 | Region comparison for utilities spend | 1,178 | 887 | **+24.7%** | 19.9 | 1.3 | **+93.5%** |
| Q08 | Customer segmentation by account age (he | 1,016 | 707 | **+30.4%** | 26.5 | 1.5 | **+94.4%** |
| Q09 | Currency distribution for entertainment | 1,080 | 567 | **+47.5%** | 19.3 | 1.0 | **+94.8%** |
| Q10 | Top merchants by transaction volume (gro | 1,339 | 638 | **+52.3%** | 29.8 | 1.4 | **+95.2%** |
| Q11 | Multi-category fraud pattern | 1,405 | 784 | **+44.2%** | 4.5 | 0.2 | **+95.9%** |
| Q12 | ATM transaction analysis | 1,186 | 822 | **+30.7%** | 21.1 | 4.6 | **+78.1%** |
| Q13 | High-value customer analysis (travel + h | 1,731 | 1,107 | **+36.1%** | 55.7 | 9.6 | **+82.8%** |
| Q15 | Prepaid card usage patterns | 1,271 | 819 | **+35.6%** | 19.3 | 5.1 | **+73.3%** |
| Q16 | Cross-region spend comparison (entertain | 1,354 | 727 | **+46.3%** | 57.5 | 3.6 | **+93.8%** |
| Q17 | Fraud risk score by channel (financial c | 953 | 716 | **+24.8%** | 3.9 | 0.0 | **+98.9%** |
| Q18 | EUR transactions analysis | 1,636 | 717 | **+56.2%** | 19.3 | 6.3 | **+67.3%** |
| Q19 | New customer transaction patterns | 1,775 | 879 | **+50.5%** | 29.0 | 4.9 | **+83.2%** |
| Q20 | Large transaction fraud check (multi-cat | 1,451 | 969 | **+33.2%** | 25.5 | 3.5 | **+86.1%** |
| Q22 | AP region high-value retail | 4,651 | 912 | **+80.4%** | 64.6 | 8.7 | **+86.5%** |
| Q24 | Debit card category spend distribution | 935 | 874 | **+6.5%** | 19.3 | 12.3 | **+36.3%** |
| Q25 | Combined fraud and spend summary (all ca | 1,180 | 1,083 | **+8.2%** | 18.2 | 11.3 | **+38.3%** |

---

## Assumptions and Limitations

1. **Synthetic data**: 5M rows of generated financial transaction data.
   Real enterprise baselines may already have partially reasonable partition keys,
   compressing the latency benefit toward the lower end of the conservative range.

2. **Single mechanism tested**: Only H1 (partition advisor) is measured.
   H2–H5 (DAG parallelisation, storage tiering, LSTM pre-scaling, autonomy scheduler)
   are not implemented in this MVP.

3. **No Iceberg**: This MVP uses Hive-style Glue external tables, not Iceberg.
   The paper's metadata-only partition evolution claim requires Iceberg.
   In this MVP, the optimized layout is pre-generated rather than evolved.

4. **No production integration**: This MVP does not implement the full SODL
   control loop (Kinesis → Feature Store → Predictor → Scheduler → Action).

5. **Athena latency variability**: Serverless Athena has startup and queueing
   overhead that adds noise. The 3-run average mitigates but does not eliminate this.

---

## Files

- `baseline.csv` — raw benchmark results (baseline table)
- `optimized.csv` — raw benchmark results (optimized table)
- `advisor_output.json` — partition advisor scoring details
- `latency_comparison.png` — per-query latency chart
- `bytes_scanned_comparison.png` — per-query bytes scanned chart
- `summary.md` — this file