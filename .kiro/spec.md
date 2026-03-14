# Kiro Spec: SODL MVP — Partition Advisor (H1)

## Project Purpose

Build a paper-aligned AWS MVP that provides mechanism-level evidence for
**H1 only** from the SODL white paper:

> H1: The information-gain-optimal partition advisor reduces mean query latency
> by ≥30% relative to the migration-time partition within 30 days of deployment.

## Scope Boundaries

### In scope
- S3 data storage (Parquet, two partition layouts)
- Glue Data Catalog (external tables, Hive partitioning)
- Athena (query execution, latency + bytes metrics)
- Python partition advisor (sqlglot AST parsing, IG scoring)
- CloudWatch via Athena workgroup metrics
- Results: before/after CSV, latency chart, bytes chart, summary.md

### Out of scope (do not build)
- SageMaker Pipelines DAG
- LSTM–Markov predictor
- Confidence-gated autonomy scheduler
- Step Functions approval workflow
- Redshift optimization
- Iceberg (use Hive-style Glue tables for MVP; note limitation in paper)
- End-to-end 15-minute control loop

## Tech Stack

- Python 3.11+
- AWS: S3, Glue, Athena
- Libraries: boto3, pyarrow, sqlglot, matplotlib

## Entry Points (run in order)

```
scripts/00_setup_aws.py      # Day 1 — infra
scripts/01_generate_data.py  # Day 1/2 — data
scripts/02_load_data.py      # Day 2 — S3 + Glue
scripts/03_run_benchmark.py  # Day 3 — baseline
scripts/04_analyze_queries.py # Day 4 — advisor
scripts/05_repartition.py    # Day 5 — optimized benchmark
scripts/06_compare_results.py # Day 6 — charts + report
```

## Success Criteria

| Metric | Target | Hard fail |
|--------|--------|-----------|
| Mean latency reduction | ≥10% | <5% (no signal) |
| Bytes scanned reduction | ≥10% | <5% |
| Row count equivalence | 100% | Any mismatch |
| Second run reproducibility | Within 15% | >20% variance |

Note: ≥30% is the H1 target. 10–29% is "directionally supportive" and
still publishable with appropriate hedging.

## Config

All AWS settings in `scripts/config.py`. Change `S3_BUCKET` to a unique value.

## Key Design Decision

The **baseline uses date partitioning** (the migration-time antipattern).
The benchmark queries filter on `merchant_category` — NOT on date.
This means Athena must scan all 90 date partitions for every baseline query.
The optimized layout partitions by `merchant_category`, allowing Athena to
prune to 1–2 partitions per query.

This is the controlled experiment setup that gives the partition advisor
the best chance of demonstrating its mechanism. The paper acknowledges
that real enterprise baselines may already have reasonable partition keys
(compressing the gain toward the lower end of the 30–60% range).

## AWS Cost Estimate

| Service | Usage | Estimated Cost |
|---------|-------|----------------|
| S3 | ~1 GB data × 2 layouts | ~$0.05/month |
| Glue | Crawler + catalog | ~$1 |
| Athena | 25 queries × 3 runs × 2 tables = 150 queries | ~$0.50 |
| **Total MVP experiment** | | **~$5–10** |

Clean up with: `aws s3 rb s3://sodl-mvp-bucket --force`
