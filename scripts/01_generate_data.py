#!/usr/bin/env python3
"""
01_generate_data.py  —  Day 1/2
Generates synthetic financial transaction data as Parquet files.

Intentional antipattern: baseline is partitioned by date (the lift-and-shift
default). The queries filter primarily on merchant_category and region —
columns that are NOT the partition key — so Athena must scan all partitions.
This reproduces the common migration-time antipattern the partition advisor
is designed to detect and correct.
"""
import os, sys, random
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, ".")
from config import NUM_ROWS, NUM_PARTITIONS_DATE, RANDOM_SEED, LOCAL_DATA_DIR

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

# ── Domain values ─────────────────────────────────────────────────────────────
MERCHANT_CATEGORIES = [
    "retail", "dining", "travel", "utilities", "healthcare",
    "entertainment", "groceries", "fuel", "online", "financial"
]
REGIONS = ["us-east", "us-west", "eu-central", "ap-southeast", "ap-northeast"]
CARD_TYPES = ["credit", "debit", "prepaid"]
CHANNELS = ["pos", "online", "atm", "mobile"]
CURRENCIES = ["USD", "EUR", "GBP", "SGD"]

# Skewed distributions (realistic): 80% of transactions are in top 3 categories
CATEGORY_WEIGHTS = [0.20, 0.18, 0.15, 0.10, 0.08, 0.08, 0.07, 0.06, 0.05, 0.03]
REGION_WEIGHTS   = [0.40, 0.25, 0.20, 0.10, 0.05]


def generate_batch(n: int, start_date: datetime) -> pd.DataFrame:
    dates = [start_date + timedelta(days=random.randint(0, NUM_PARTITIONS_DATE - 1))
             for _ in range(n)]
    return pd.DataFrame({
        "transaction_id":    [f"TXN{i:010d}" for i in range(n)],
        "transaction_date":  [d.strftime("%Y-%m-%d") for d in dates],
        "transaction_ts":    [d + timedelta(seconds=random.randint(0, 86399)) for d in dates],
        "merchant_id":       np.random.randint(1000, 9999, n).astype(str),
        "merchant_category": random.choices(MERCHANT_CATEGORIES, weights=CATEGORY_WEIGHTS, k=n),
        "region":            random.choices(REGIONS, weights=REGION_WEIGHTS, k=n),
        "card_type":         random.choices(CARD_TYPES, k=n),
        "channel":           random.choices(CHANNELS, k=n),
        "currency":          random.choices(CURRENCIES, k=n),
        "amount":            np.round(np.random.lognormal(mean=3.5, sigma=1.2, size=n), 2),
        "is_fraud":          np.random.binomial(1, 0.015, n).astype(bool),
        "customer_id":       np.random.randint(100000, 999999, n).astype(str),
        "account_age_days":  np.random.randint(1, 3650, n),
    })


def write_baseline_partitions(df: pd.DataFrame, out_dir: str):
    """
    Write partitioned by date — the migration-time antipattern.
    Queries on merchant_category or region will scan ALL date partitions.
    """
    part_dir = os.path.join(out_dir, "baseline")
    os.makedirs(part_dir, exist_ok=True)

    for date, grp in df.groupby("transaction_date"):
        partition_path = os.path.join(part_dir, f"date={date}")
        os.makedirs(partition_path, exist_ok=True)
        table = pa.Table.from_pandas(grp.drop(columns=["transaction_date"]))
        pq.write_table(table, os.path.join(partition_path, "data.parquet"),
                       compression="snappy")

    print(f"[OK] Baseline written: {len(df.transaction_date.unique())} date partitions")
    print(f"     Path: {part_dir}")


def write_optimized_partitions(df: pd.DataFrame, out_dir: str):
    """
    Write partitioned by merchant_category — the workload-informed layout.
    The benchmark queries all filter on merchant_category, so Athena prunes
    to 1–2 partitions instead of scanning all 90 date partitions.
    """
    part_dir = os.path.join(out_dir, "optimized")
    os.makedirs(part_dir, exist_ok=True)

    for cat, grp in df.groupby("merchant_category"):
        partition_path = os.path.join(part_dir, f"merchant_category={cat}")
        os.makedirs(partition_path, exist_ok=True)
        table = pa.Table.from_pandas(grp)
        pq.write_table(table, os.path.join(partition_path, "data.parquet"),
                       compression="snappy")

    print(f"[OK] Optimized written: {len(df.merchant_category.unique())} category partitions")
    print(f"     Path: {part_dir}")


if __name__ == "__main__":
    print("=== SODL MVP — Data Generation ===")
    print(f"Generating {NUM_ROWS:,} rows...")

    os.makedirs(LOCAL_DATA_DIR, exist_ok=True)
    start_date = datetime(2024, 1, 1)

    # Generate in one batch (fits in memory for 5M rows)
    df = generate_batch(NUM_ROWS, start_date)

    total_mb = df.memory_usage(deep=True).sum() / 1024 / 1024
    print(f"[OK] DataFrame: {len(df):,} rows, {total_mb:.0f} MB in memory")
    print(f"     Fraud rate: {df.is_fraud.mean():.2%}")
    print(f"     Categories: {df.merchant_category.value_counts().to_dict()}")
    print(f"     Regions:    {df.region.value_counts().to_dict()}")

    write_baseline_partitions(df, LOCAL_DATA_DIR)
    write_optimized_partitions(df, LOCAL_DATA_DIR)

    print()
    print("Data generation complete. Next: run 02_load_data.py")
