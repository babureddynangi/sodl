#!/usr/bin/env python3
"""
02b_register_optimized.py — registers only the optimized Glue table.
Run this after 02_load_data.py if it failed partway through.
"""
import os, sys
import pyarrow.parquet as pq
import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, ".")
from config import (
    AWS_REGION, AWS_PROFILE, S3_BUCKET, S3_PREFIX_OPTIMIZED,
    GLUE_DATABASE, GLUE_TABLE_OPTIMIZED, LOCAL_DATA_DIR
)

session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
s3   = session.client("s3")
glue = session.client("glue")

def _pa_to_glue_type(pa_type: str) -> str:
    mapping = {
        "string": "string", "utf8": "string", "large_string": "string",
        "double": "double", "float": "float",
        "int32": "int", "int64": "bigint",
        "bool": "boolean", "timestamp[us]": "timestamp",
        "timestamp[us, tz=UTC]": "timestamp",
        "dictionary<values=string, indices=int32, ordered=0>": "string",
    }
    return mapping.get(pa_type, "string")

def get_columns(local_dir):
    for root, _, files in os.walk(local_dir):
        for f in files:
            if f.endswith(".parquet"):
                pf = pq.ParquetFile(os.path.join(root, f))
                return [(field.name, _pa_to_glue_type(str(field.type)))
                        for field in pf.schema_arrow]
    return []

def register_glue_table(table_name, s3_location, columns, partition_keys):
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

def add_glue_partitions(table_name, s3_prefix, partition_key):
    paginator = s3.get_paginator("list_objects_v2")
    seen, batch = set(), []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=s3_prefix, Delimiter="/"):
        for prefix_obj in page.get("CommonPrefixes", []):
            part_prefix = prefix_obj["Prefix"]
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
                    "SerdeInfo": {"SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"}
                }
            })
            if len(batch) == 100:
                glue.batch_create_partition(DatabaseName=GLUE_DATABASE, TableName=table_name, PartitionInputList=batch)
                batch = []
    if batch:
        glue.batch_create_partition(DatabaseName=GLUE_DATABASE, TableName=table_name, PartitionInputList=batch)
    print(f"[OK] {len(seen)} partitions registered for {table_name}")

if __name__ == "__main__":
    optimized_local = os.path.join(LOCAL_DATA_DIR, "optimized")
    cols = get_columns(optimized_local)
    print(f"Columns detected: {cols}")
    register_glue_table(
        table_name=GLUE_TABLE_OPTIMIZED,
        s3_location=f"s3://{S3_BUCKET}/{S3_PREFIX_OPTIMIZED}",
        columns=cols,
        partition_keys=[("merchant_category", "string")]
    )
    add_glue_partitions(GLUE_TABLE_OPTIMIZED, S3_PREFIX_OPTIMIZED, "merchant_category")
    print("\n[OK] Optimized table registered. Next: run 03_run_benchmark.py")
