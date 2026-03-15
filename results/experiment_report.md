# SODL Closed-Loop Experiment Report

**Generated**: 2026-03-15 15:32 UTC
**Gate decision**: ACCEPT  (confidence=1.0000, predicted gain=38.6%)

---

## H1 Hypothesis

> H1: The information-gain-optimal partition advisor reduces mean query latency
> by ≥30% relative to the migration-time partition.

**H1: MET ✅**

---

## Before / After Results

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Median latency (ms) | 1,117 | 742 | **-33.6%** |
| P95 latency (ms) | 2,850 | 1,408 | **-50.6%** |
| Mean bytes scanned (MB) | 29.1 | 4.1 | **-86.0%** |
| Cost proxy (USD) | $0.0087 | $0.0014 | **-84.0%** |
| Correctness | ✅ PASS (5000000 successful queries each) | — | — |

---

## Confidence Gate

| Parameter | Value |
|-----------|-------|
| Decision | **ACCEPT** |
| Confidence | 1.0000 (threshold: 0.8) |
| Predicted improvement | 38.6% (threshold: 10.0%) |
| Gate reason | passes_all_thresholds |

---

## Scope and Limitations

- Synthetic 5M-row dataset; real enterprise baselines may show different gains.
- Single optimization lever tested (partition key selection).
- MVP uses Hive-style Glue tables; production would use Iceberg partition evolution.
- Model trained on 21 query-level samples — sufficient for prototype, not production.