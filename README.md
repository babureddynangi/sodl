# SODL MVP — Partition Advisor (H1 Only)

> **Scope**: This is a mechanism-level MVP focused exclusively on H1 from the SODL white paper.
> It is **not** an end-to-end instantiation of the full SODL control plane.

## What This Proves

From the paper's pre-registered hypothesis table (Section 12.1):

> **H1**: The information-gain-optimal partition advisor reduces mean query latency by ≥30%
> relative to the migration-time partition within 30 days of deployment.

## What This MVP Does NOT Include

- Full SageMaker Pipelines DAG
- LSTM–Markov predictor
- Confidence-gated autonomy scheduler
- Step Functions approval workflow
- Redshift optimization
- End-to-end 15-minute closed loop

These remain "Specified" or "Simulated" per Section 5.5 of the paper.

---

## Architecture

```
S3 (synthetic data)
  └── Glue Data Catalog (metadata)
        └── Athena (query execution + metrics)
              └── Python Partition Advisor (query log analysis)
                    └── Repartitioned S3 layout → new Glue table
                          └── CloudWatch / CSV metrics export
                                └── Comparison report + charts
```

## Repo Structure

```
sodl-mvp/
  data/                   # synthetic Parquet data (generated locally)
  sql/                    # 25 benchmark queries
  scripts/
    00_setup_aws.py       # S3 bucket, Glue DB, Athena workgroup
    01_generate_data.py   # synthetic financial transaction data
    02_load_data.py       # upload to S3 + register Glue tables
    03_run_benchmark.py   # execute 25 queries, capture latency + bytes
    04_analyze_queries.py # partition advisor: parse SQL, score partition keys
    05_repartition.py     # repartition data, register new Glue table
    06_compare_results.py # delta table + charts + markdown report
    config.py             # all AWS config in one place
  results/
    baseline.csv
    optimized.csv
    summary.md
  docs/
    paper_subsection.md   # ready-to-paste paper text
```

## 7-Day Build Plan

| Day | Task |
|-----|------|
| 1 | Run `00_setup_aws.py` — S3, Glue DB, Athena workgroup |
| 2 | Run `01_generate_data.py` + `02_load_data.py` — data + tables |
| 3 | Run `03_run_benchmark.py` × 3 — baseline CSV |
| 4 | Run `04_analyze_queries.py` — partition advisor output |
| 5 | Run `05_repartition.py` — new layout + re-run benchmark |
| 6 | Run `06_compare_results.py` — charts + summary |
| 7 | Review `docs/paper_subsection.md` — paste into paper |

## Prerequisites

```bash
pip install boto3 pandas pyarrow sqlglot matplotlib tabulate
```

Set environment variables or AWS profile:
```bash
export AWS_PROFILE=your-profile
export AWS_DEFAULT_REGION=us-east-1
```

## Success Criteria

| Metric | Target | Falsified If |
|--------|--------|--------------|
| Mean query latency reduction | ≥ 10–30% | < 5% |
| Bytes scanned reduction | ≥ 10–30% | < 5% |
| Query correctness | 100% row-count match | Any mismatch |
| Reproducibility | Second run within 10% | > 10% variance |

> Note: We target the **lower end** of the paper's conservative range (10–30%)
> because our synthetic baseline may already be partially reasonable.
> The paper's 30–60% claim requires a production workload with a substantially
> misaligned migration-time partition key.

---

## Paper Sentence (Ready to Use)

> To complement the simulation-backed architectural analysis, we implemented
> a limited AWS MVP focused on the partition-advisor mechanism (H1). The MVP
> used Amazon S3, AWS Glue Data Catalog, and Amazon Athena to compare a
> migration-time partitioning baseline against a workload-informed repartitioned
> layout under controlled synthetic workloads. This MVP provides
> mechanism-level feasibility evidence only; it is not an end-to-end
> instantiation of the full SODL control plane.
