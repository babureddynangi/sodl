#!/usr/bin/env python3
"""
app/features/train_features.py
Feature engineering: aggregates baseline + optimized telemetry into
an ML-ready feature matrix and saves to results/features.csv.

Usage:
  python app/features/train_features.py
"""
import sys, os
import pandas as pd

sys.path.insert(0, ".")
from scripts.config import LOCAL_RESULTS_DIR, RANDOM_SEED

# Partition scheme encoding
SCHEME_ENCODING = {
    "transactions_baseline":  0,   # date-partitioned (baseline)
    "transactions_optimized": 1,   # merchant_category-partitioned
}

IMPROVEMENT_THRESHOLD_PCT = 10.0  # label=1 if runtime improves by >= this %


def load_telemetry(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise ValueError(f"Telemetry file not found: {path}")
    df = pd.read_csv(path)
    required = {"query_id", "engine_ms", "bytes_scanned", "status", "table"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Telemetry file {path} missing columns: {missing}")
    return df


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """Mean runtime and bytes per query_id for SUCCEEDED rows only."""
    succeeded = df[df["status"] == "SUCCEEDED"].copy()
    succeeded["engine_ms"] = pd.to_numeric(succeeded["engine_ms"], errors="coerce")
    succeeded["bytes_scanned"] = pd.to_numeric(succeeded["bytes_scanned"], errors="coerce")
    agg = (
        succeeded.groupby("query_id")
        .agg(
            mean_runtime_ms=("engine_ms", "mean"),
            mean_bytes=("bytes_scanned", "mean"),
            table=("table", "first"),
            n_runs=("run", "count"),
        )
        .reset_index()
    )
    return agg


def build_features(baseline_path: str, optimized_path: str, out_path: str) -> pd.DataFrame:
    b = load_telemetry(baseline_path)
    o = load_telemetry(optimized_path)

    b_agg = aggregate(b)
    o_agg = aggregate(o)

    merged = b_agg.merge(o_agg, on="query_id", suffixes=("_base", "_opt"))
    if merged.empty:
        raise ValueError("No overlapping query_ids between baseline and optimized telemetry.")

    merged["runtime_improvement_pct"] = (
        (merged["mean_runtime_ms_base"] - merged["mean_runtime_ms_opt"])
        / merged["mean_runtime_ms_base"] * 100
    ).round(2)

    merged["bytes_improvement_pct"] = (
        (merged["mean_bytes_base"] - merged["mean_bytes_opt"])
        / merged["mean_bytes_base"] * 100
    ).round(2)

    merged["improvement_label"] = (
        merged["runtime_improvement_pct"] >= IMPROVEMENT_THRESHOLD_PCT
    ).astype(int)

    merged["partition_scheme_baseline"] = (
        merged["table_base"].map(SCHEME_ENCODING).fillna(0).astype(int)
    )
    merged["partition_scheme_optimized"] = (
        merged["table_opt"].map(SCHEME_ENCODING).fillna(1).astype(int)
    )

    features = merged[[
        "query_id",
        "mean_runtime_ms_base", "mean_bytes_base",
        "mean_runtime_ms_opt",  "mean_bytes_opt",
        "runtime_improvement_pct", "bytes_improvement_pct",
        "improvement_label",
        "partition_scheme_baseline", "partition_scheme_optimized",
        "n_runs_base",
    ]].rename(columns={
        "mean_runtime_ms_base": "baseline_mean_runtime_ms",
        "mean_bytes_base":      "baseline_mean_bytes",
        "mean_runtime_ms_opt":  "optimized_mean_runtime_ms",
        "mean_bytes_opt":       "optimized_mean_bytes",
        "n_runs_base":          "n_runs",
    })

    os.makedirs(os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True)
    features.to_csv(out_path, index=False)
    print(f"[OK] Features saved: {out_path}  ({len(features)} rows, "
          f"{features['improvement_label'].sum()} positive labels)")
    return features


if __name__ == "__main__":
    baseline_path  = os.path.join(LOCAL_RESULTS_DIR, "baseline.csv")
    optimized_path = os.path.join(LOCAL_RESULTS_DIR, "optimized.csv")
    out_path       = os.path.join(LOCAL_RESULTS_DIR, "features.csv")

    print("=== Feature Builder ===")
    features = build_features(baseline_path, optimized_path, out_path)
    print(f"\nFeature matrix shape : {features.shape}")
    print(f"Improvement label dist: {features['improvement_label'].value_counts().to_dict()}")
    print(f"Mean runtime improvement: {features['runtime_improvement_pct'].mean():.1f}%")
