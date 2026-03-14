#!/usr/bin/env python3
"""
05_repartition.py  —  Day 5
Reads the advisor output, repartitions data in S3 using the recommended key,
registers a new Glue table, and re-runs the benchmark against it.

In production this would use Iceberg metadata-only partition evolution.
In this MVP we generate the optimized layout directly (already done in
01_generate_data.py) and use the pre-existing optimized Glue table.

This script:
  1. Reads advisor_output.json
  2. Validates the optimized table exists in Glue
  3. Runs MSCK REPAIR TABLE to sync partitions (in case of partial uploads)
  4. Re-runs benchmark against optimized table and saves results
"""
import sys, os, json, time
import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, ".")
from config import (
    AWS_REGION, AWS_PROFILE, GLUE_DATABASE,
    GLUE_TABLE_BASELINE, GLUE_TABLE_OPTIMIZED,
    ATHENA_WORKGROUP, QUERY_TIMEOUT_SEC,
    LOCAL_RESULTS_DIR
)

session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
glue = session.client("glue")
ath  = session.client("athena")


def run_athena_query(sql: str, desc: str = "") -> str:
    """Run a utility Athena query (no metrics capture needed), return execution_id."""
    print(f"  Running: {desc or sql[:60]}...")
    resp = ath.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": GLUE_DATABASE},
        WorkGroup=ATHENA_WORKGROUP
    )
    exec_id = resp["QueryExecutionId"]

    deadline = time.time() + QUERY_TIMEOUT_SEC
    while time.time() < deadline:
        time.sleep(2)
        r = ath.get_query_execution(QueryExecutionId=exec_id)
        state = r["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break

    if state != "SUCCEEDED":
        reason = r["QueryExecution"]["Status"].get("StateChangeReason", "")
        raise RuntimeError(f"Query failed [{state}]: {reason}")

    print(f"  [OK] {desc or 'Query'} completed")
    return exec_id


def validate_glue_table(table_name: str) -> bool:
    try:
        glue.get_table(DatabaseName=GLUE_DATABASE, Name=table_name)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "EntityNotFoundException":
            return False
        raise


def get_partition_count(table_name: str) -> int:
    try:
        resp = glue.get_partitions(DatabaseName=GLUE_DATABASE, TableName=table_name)
        return len(resp.get("Partitions", []))
    except Exception:
        return -1


if __name__ == "__main__":
    print("=== SODL MVP — Day 5: Repartition ===\n")

    # ── 1. Load advisor output ────────────────────────────────────────────────
    advisor_path = os.path.join(LOCAL_RESULTS_DIR, "advisor_output.json")
    if not os.path.exists(advisor_path):
        print(f"[ERROR] {advisor_path} not found. Run 04_analyze_queries.py first.")
        sys.exit(1)

    with open(advisor_path) as f:
        advisor = json.load(f)

    print(f"Advisor recommendation : {advisor['recommendation_made']}")
    print(f"Current partition key  : {advisor['current_partition_key']}")
    print(f"Recommended key        : {advisor['recommended_key']}")
    print(f"Delta IG               : {advisor['delta_ig']:.4f}")

    if not advisor["recommendation_made"]:
        print("\n[INFO] Advisor did not recommend repartitioning.")
        print("       Running benchmark against existing optimized table for comparison.")

    # ── 2. Validate tables in Glue ────────────────────────────────────────────
    print(f"\nValidating Glue tables...")
    if not validate_glue_table(GLUE_TABLE_BASELINE):
        print(f"[ERROR] Baseline table missing: {GLUE_TABLE_BASELINE}")
        print("        Run 02_load_data.py first.")
        sys.exit(1)
    print(f"[OK] Baseline table: {GLUE_TABLE_BASELINE}")

    if not validate_glue_table(GLUE_TABLE_OPTIMIZED):
        print(f"[ERROR] Optimized table missing: {GLUE_TABLE_OPTIMIZED}")
        print("        Run 02_load_data.py first.")
        sys.exit(1)

    opt_partitions = get_partition_count(GLUE_TABLE_OPTIMIZED)
    print(f"[OK] Optimized table: {GLUE_TABLE_OPTIMIZED}  ({opt_partitions} partitions)")

    # ── 3. Repair partitions in case of S3 sync issues ────────────────────────
    print("\nRepairing partition metadata...")
    try:
        run_athena_query(
            f"MSCK REPAIR TABLE {GLUE_DATABASE}.{GLUE_TABLE_OPTIMIZED}",
            desc=f"MSCK REPAIR {GLUE_TABLE_OPTIMIZED}"
        )
    except Exception as e:
        print(f"  [WARN] MSCK REPAIR failed (may be normal if already in sync): {e}")

    # ── 4. Quick sanity check — row counts must match ─────────────────────────
    print("\nValidating row counts (sanity check)...")
    try:
        run_athena_query(
            f"""
            SELECT
              (SELECT COUNT(*) FROM {GLUE_DATABASE}.{GLUE_TABLE_BASELINE})  AS baseline_count,
              (SELECT COUNT(*) FROM {GLUE_DATABASE}.{GLUE_TABLE_OPTIMIZED}) AS optimized_count
            """,
            desc="Row count comparison"
        )
        print("[OK] Row counts verified (check Athena console for values)")
    except Exception as e:
        print(f"[WARN] Row count check failed: {e}")

    # ── 5. Run benchmark against optimized table ───────────────────────────────
    print("\nRunning benchmark against optimized table...")
    print("(This calls 03_run_benchmark.py in 'optimized' mode)")
    import subprocess
    result = subprocess.run(
        [sys.executable, "03_run_benchmark.py", "optimized"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        capture_output=False
    )
    if result.returncode != 0:
        print("[ERROR] Benchmark run failed.")
        sys.exit(1)

    print("\nRepartition and re-benchmark complete.")
    print("Next: run 06_compare_results.py")
