#!/usr/bin/env python3
"""
02_load_data.py  —  Day 2
Uploads Parquet files to S3 and registers Glue external tables.
"""
import os, sys, boto3
from botocore.exceptions import ClientError
sys.path.insert(0, ".")
from config import (
    AWS_REGION, AWS_PROFILE, S3_BUCKET, S3_PREFIX_BASELINE, S3_PREFIX_OPTIMIZED,
    GLUE_DATABASE, GLUE_TABLE_BASELINE, GLUE_TABLE_OPTIMIZED, LOCAL_DATA_DIR
)

session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
s3   = session.client("s3")
glue = session.client("glue")


# ── Helpers ───────────────────────────────────────────────────────────────────
def upload_directory(local_dir: str, s3_prefix: str) -> int:
    """Upload all files under local_dir to s3://BUCKET/s3_prefix, preserving structure."""
    count = 0
    for root, _, files in os.walk(local_dir):
        for fname in files:
            local_path = os.path.join(root, fname)
            # Compute relative path from local_dir
            rel = os.path.relpath(local_path, local_dir)
            s3_key = s3_prefix + rel.replace(os.sep, "/")
            s3.upload_file(local_path, S3_BUCKET, s3_key)
            count += 1
    return count


def get_parquet_columns(local_dir: str):
    """Peek at one Parquet file to get column names + types."""
    import pyarrow.parquet as pq
    for root, _, files in os.walk(local_dir):
        for f in files:
            if f.endswith(".parquet"):
                tbl = pq.read_table(os.path.join(root, f)).schema
                return [(field.name, _pa_to_glue_type(str(field.type)))
                        for field in tbl]
    return []


def _pa_to_glue_type(pa_type: str) -> str:
    mapping = {
        "string": "string", "utf8": "string",
        "double": "double", "float": "float",
        "int32": "int", "int64": "bigint",
        "bool": "boolean", "timestamp[us]": "timestamp",
        "timestamp[us, tz=UTC]": "timestamp",
    }
    return mapping.get(pa_type, "string")


def register_glue_table(table_name: str, s3_location: str,
                         columns: list, partition_keys: list):
    """Create (or replace) a Glue external table over Parquet on S3."""
    # Columns = non-partition columns
    non_part = [{"Name": n, "Type": t} for n, t in columns
                if n not in [k for k, _ in partition_keys]]
    part_cols = [{"Name": k, "Type": t} for k, t in partition_keys]

    table_input = {
        "Name": table_name,
        "StorageDescriptor": {
            "Columns": non_part,
            "Location": s3_location,
            "InputFormat":  "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
            "SerdeInfo": {
                "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
                "Parameters": {"serialization.format": "1"}
            },
            "Parameters": {"classification": "parquet"}
        },
        "PartitionKeys": part_cols,
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {"EXTERNAL": "TRUE", "classification": "parquet"}
    }

    try:
        glue.create_table(DatabaseName=GLUE_DATABASE, TableInput=table_input)
        print(f"[OK] Glue table created: {GLUE_DATABASE}.{table_name}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "AlreadyExistsException":
            glue.update_table(DatabaseName=GLUE_DATABASE, TableInput=table_input)
            print(f"[OK] Glue table updated: {GLUE_DATABASE}.{table_name}")
        else:
            raise


def add_glue_partitions(table_name: str, s3_prefix: str, partition_key: str):
    """
    Batch-add partition metadata to Glue so Athena can resolve them.
    Discovers partitions by listing the S3 prefix.
    """
    paginator = s3.get_paginator("list_objects_v2")
    seen = set()
    batch = []

    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=s3_prefix, Delimiter="/"):
        for prefix_obj in page.get("CommonPrefixes", []):
            part_prefix = prefix_obj["Prefix"]           # e.g. "transactions/baseline/date=2024-01-01/"
            part_val = part_prefix.rstrip("/").split(f"{partition_key}=")[-1]
            if part_val in seen:
                continue
            seen.add(part_val)

            batch.append({
                "Values": [part_val],
                "StorageDescriptor": {
                    "Location": f"s3://{S3_BUCKET}/{part_prefix}",
                    "InputFormat":  "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
                    "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
                    "SerdeInfo": {
                        "SerializationLibrary":
                            "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
                    }
                }
            })

            if len(batch) == 100:   # Glue batch limit
                glue.batch_create_partition(
                    DatabaseName=GLUE_DATABASE,
                    TableName=table_name,
                    PartitionInputList=batch
                )
                batch = []

    if batch:
        glue.batch_create_partition(
            DatabaseName=GLUE_DATABASE,
            TableName=table_name,
            PartitionInputList=batch
        )

    print(f"[OK] {len(seen)} partitions registered for {table_name}")


if __name__ == "__main__":
    print("=== SODL MVP — Day 2: Load Data ===")

    # ── Upload baseline (date-partitioned) ─────────────────────────────────
    print("\n[1/4] Uploading baseline (date partitions)...")
    baseline_local = os.path.join(LOCAL_DATA_DIR, "baseline")
    n = upload_directory(baseline_local, S3_PREFIX_BASELINE)
    print(f"      Uploaded {n} files → s3://{S3_BUCKET}/{S3_PREFIX_BASELINE}")

    # ── Upload optimized (category-partitioned) ────────────────────────────
    print("\n[2/4] Uploading optimized (merchant_category partitions)...")
    optimized_local = os.path.join(LOCAL_DATA_DIR, "optimized")
    n = upload_directory(optimized_local, S3_PREFIX_OPTIMIZED)
    print(f"      Uploaded {n} files → s3://{S3_BUCKET}/{S3_PREFIX_OPTIMIZED}")

    # ── Baseline Glue table ────────────────────────────────────────────────
    print("\n[3/4] Registering Glue tables...")
    # Get column schema from a sample file (exclude the date partition col)
    cols = get_parquet_columns(baseline_local)
    register_glue_table(
        table_name=GLUE_TABLE_BASELINE,
        s3_location=f"s3://{S3_BUCKET}/{S3_PREFIX_BASELINE}",
        columns=cols,
        partition_keys=[("date", "string")]
    )
    add_glue_partitions(GLUE_TABLE_BASELINE, S3_PREFIX_BASELINE, "date")

    # ── Optimized Glue table ───────────────────────────────────────────────
    cols2 = get_parquet_columns(optimized_local)
    register_glue_table(
        table_name=GLUE_TABLE_OPTIMIZED,
        s3_location=f"s3://{S3_BUCKET}/{S3_PREFIX_OPTIMIZED}",
        columns=cols2,
        partition_keys=[("merchant_category", "string")]
    )
    add_glue_partitions(GLUE_TABLE_OPTIMIZED, S3_PREFIX_OPTIMIZED, "merchant_category")

    print("\nLoad complete. Next: run 03_run_benchmark.py")
