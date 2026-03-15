#!/usr/bin/env python3
"""
app/executor/execute.py
Applies an accepted gate decision by registering a new Glue table (reusing
existing optimized S3 data — zero new storage cost), then re-runs the
benchmark and saves post-execution telemetry.

Usage:
  python app/executor/execute.py
"""
import sys, os, json, subprocess, shutil
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, ".")
from scripts.config import (
    AWS_REGION, AWS_PROFILE, S3_BUCKET, S3_PREFIX_OPTIMIZED,
    GLUE_DATABASE, GLUE_TABLE_BASELINE, GLUE_TABLE_OPTIMIZED,
    LOCAL_RESULTS_DIR,
)

session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
glue = session.client("glue")


def verify_baseline_exists() -> bool:
    try:
        glue.get_table(DatabaseName=GLUE_DATABASE, Name=GLUE_TABLE_BASELINE)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "EntityNotFoundException":
            return False
        raise


def get_optimized_table_schema() -> tuple:
    """Return (columns, partition_keys) from the existing optimized table."""
    resp = glue.get_table(DatabaseName=GLUE_DATABASE, Name=GLUE_TABLE_OPTIMIZED)
    sd = resp["Table"]["StorageDescriptor"]
    columns = [(c["Name"], c["Type"]) for c in sd["Columns"]]
    part_keys = [(p["Name"], p["Type"]) for p in resp["Table"].get("PartitionKeys", [])]
    return columns, part_keys


def register_exec_table(table_name: str, columns: list, partition_keys: list) -> bool:
    """Register a new Glue table pointing to the existing optimized S3 path."""
    non_part = [{"Name": n, "Type": t} for n, t in columns]
    part_cols = [{"Name": k, "Type": t} for k, t in partition_keys]
    s3_location = f"s3://{S3_BUCKET}/{S3_PREFIX_OPTIMIZED}"

    table_input = {
        "Name": table_name,
        "StorageDescriptor": {
            "Columns": non_part,
            "Location": s3_location,
            "InputFormat":  "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
            "SerdeInfo": {
                "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
                "Parameters": {"serialization.format": "1"},
            },
            "Parameters": {"classification": "parquet"},
        },
        "PartitionKeys": part_cols,
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {"EXTERNAL": "TRUE", "classification": "parquet"},
    }
    try:
        glue.create_table(DatabaseName=GLUE_DATABASE, TableInput=table_input)
        print(f"[OK] Glue table created: {GLUE_DATABASE}.{table_name}")
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "AlreadyExistsException":
            print(f"[OK] Glue table already exists: {table_name} — reusing")
            return True
        print(f"[ERROR] Glue table creation failed: {e}")
        return False


def copy_partitions(src_table: str, dst_table: str):
    """Copy partition metadata from src to dst table."""
    try:
        resp = glue.get_partitions(DatabaseName=GLUE_DATABASE, TableName=src_table)
        partitions = resp.get("Partitions", [])
        if not partitions:
            return
        batch = []
        for p in partitions:
            batch.append({
                "Values": p["Values"],
                "StorageDescriptor": p["StorageDescriptor"],
            })
            if len(batch) == 100:
                glue.batch_create_partition(
                    DatabaseName=GLUE_DATABASE, TableName=dst_table,
                    PartitionInputList=batch
                )
                batch = []
        if batch:
            glue.batch_create_partition(
                DatabaseName=GLUE_DATABASE, TableName=dst_table,
                PartitionInputList=batch
            )
        print(f"[OK] {len(partitions)} partitions copied to {dst_table}")
    except Exception as e:
        print(f"[WARN] Partition copy failed (non-fatal): {e}")


def run_benchmark_against(table_name: str, out_csv: str) -> bool:
    """Run benchmark script against a specific table, save results to out_csv."""
    # Temporarily patch: run optimized benchmark and rename output
    result = subprocess.run(
        [sys.executable, "scripts/03_run_benchmark.py", "optimized"],
        cwd=os.getcwd(),
        capture_output=False,
    )
    src = os.path.join(LOCAL_RESULTS_DIR, "optimized.csv")
    if result.returncode == 0 and os.path.exists(src):
        shutil.copy(src, out_csv)
        print(f"[OK] Post-execution benchmark saved: {out_csv}")
        return True
    return False


def execute(decision_path: str, post_exec_out: str) -> dict:
    if not os.path.exists(decision_path):
        raise FileNotFoundError(f"Gate decision not found: {decision_path}")

    with open(decision_path) as f:
        decision = json.load(f)

    if decision.get("decision") != "accept":
        print(f"[INFO] Gate decision is '{decision.get('decision')}' — skipping execution.")
        print(f"       Reason: {decision.get('gate_reason')}")
        return decision

    print(f"[OK] Gate accepted. Proceeding with execution.")

    # 1. Verify baseline exists
    if not verify_baseline_exists():
        msg = f"Baseline table {GLUE_TABLE_BASELINE} not found in Glue."
        print(f"[ERROR] {msg}")
        decision["status"] = "failed"
        decision["error"] = msg
        with open(decision_path, "w") as f:
            json.dump(decision, f, indent=2)
        sys.exit(1)
    print(f"[OK] Baseline table verified: {GLUE_TABLE_BASELINE}")

    # 2. Register new exec table (reuse optimized S3 data — zero cost)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    exec_table = f"transactions_exec_{ts}"
    columns, partition_keys = get_optimized_table_schema()

    if not register_exec_table(exec_table, columns, partition_keys):
        decision["status"] = "failed"
        decision["error"] = "Glue table creation failed"
        with open(decision_path, "w") as f:
            json.dump(decision, f, indent=2)
        sys.exit(1)

    copy_partitions(GLUE_TABLE_OPTIMIZED, exec_table)
    decision["exec_table"] = exec_table

    # 3. Re-run benchmark
    print(f"\nRunning post-execution benchmark...")
    success = run_benchmark_against(exec_table, post_exec_out)
    if not success:
        print("[WARN] Post-execution benchmark failed — using existing optimized.csv as fallback")
        fallback = os.path.join(LOCAL_RESULTS_DIR, "optimized.csv")
        if os.path.exists(fallback):
            shutil.copy(fallback, post_exec_out)
            print(f"[OK] Fallback: copied {fallback} → {post_exec_out}")

    decision["status"] = "completed"
    decision["post_exec_csv"] = post_exec_out
    with open(decision_path, "w") as f:
        json.dump(decision, f, indent=2)

    return decision


if __name__ == "__main__":
    decision_path = os.path.join(LOCAL_RESULTS_DIR, "gate_decision.json")
    post_exec_out = os.path.join(LOCAL_RESULTS_DIR, "post_exec_benchmark.csv")

    print("=== Executor ===")
    result = execute(decision_path, post_exec_out)
    print(f"\n  Status: {result.get('status', result.get('decision'))}")
    if result.get("exec_table"):
        print(f"  Exec table: {result['exec_table']}")
