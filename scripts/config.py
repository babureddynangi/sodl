# config.py — All AWS configuration for SODL MVP
# Edit this file before running any scripts.

import os

# ── AWS Identity ──────────────────────────────────────────────────────────────
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
AWS_PROFILE = os.environ.get("AWS_PROFILE", None)  # None = default credential chain

# ── S3 ────────────────────────────────────────────────────────────────────────
# Must be globally unique. Change the suffix if the bucket already exists.
S3_BUCKET = "sodl-mvp-bucket"
S3_PREFIX_BASELINE  = "transactions/baseline/"      # date-partitioned (bad partition)
S3_PREFIX_OPTIMIZED = "transactions/optimized/"     # workload-informed partition
S3_PREFIX_RESULTS   = "results/"
S3_PREFIX_ATHENA    = "athena-results/"

# ── Glue ──────────────────────────────────────────────────────────────────────
GLUE_DATABASE       = "sodl_mvp"
GLUE_TABLE_BASELINE  = "transactions_baseline"
GLUE_TABLE_OPTIMIZED = "transactions_optimized"

# ── Athena ────────────────────────────────────────────────────────────────────
ATHENA_WORKGROUP    = "primary"
ATHENA_OUTPUT_LOC   = f"s3://{S3_BUCKET}/{S3_PREFIX_ATHENA}"

# ── Data Generation ───────────────────────────────────────────────────────────
NUM_ROWS            = 5_000_000   # ~500 MB Parquet; enough to show scan difference
NUM_PARTITIONS_DATE = 90          # 90 daily partitions (migration-time antipattern)
RANDOM_SEED         = 42

# ── Benchmark ─────────────────────────────────────────────────────────────────
BENCHMARK_RUNS      = 3           # run each query N times; report mean
QUERY_TIMEOUT_SEC   = 300         # abort query if > 5 min

# ── Partition Advisor ─────────────────────────────────────────────────────────
IG_DELTA_THRESHOLD  = 0.10        # minimum IG improvement to trigger recommendation
TOP_K_CANDIDATES    = 5           # score this many candidate keys

# ── Local paths ───────────────────────────────────────────────────────────────
LOCAL_DATA_DIR      = "data/"
LOCAL_RESULTS_DIR   = "results/"
LOCAL_SQL_DIR       = "sql/"
