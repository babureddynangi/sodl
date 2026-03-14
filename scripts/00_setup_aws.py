#!/usr/bin/env python3
"""
00_setup_aws.py  —  Day 1
Creates: S3 bucket, Glue database, Athena workgroup.
Safe to re-run (idempotent).
"""
import sys, json, boto3
from botocore.exceptions import ClientError
sys.path.insert(0, ".")
from config import (
    AWS_REGION, AWS_PROFILE, S3_BUCKET, S3_PREFIX_ATHENA,
    GLUE_DATABASE, ATHENA_WORKGROUP, ATHENA_OUTPUT_LOC
)

session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
s3  = session.client("s3")
glue = session.client("glue")
ath  = session.client("athena")


# ── 1. S3 bucket ──────────────────────────────────────────────────────────────
def create_bucket():
    try:
        if AWS_REGION == "us-east-1":
            s3.create_bucket(Bucket=S3_BUCKET)
        else:
            s3.create_bucket(
                Bucket=S3_BUCKET,
                CreateBucketConfiguration={"LocationConstraint": AWS_REGION}
            )
        print(f"[OK] S3 bucket created: s3://{S3_BUCKET}")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            print(f"[OK] S3 bucket already exists: s3://{S3_BUCKET}")
        else:
            raise

    # Block public access
    s3.put_public_access_block(
        Bucket=S3_BUCKET,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True, "IgnorePublicAcls": True,
            "BlockPublicPolicy": True, "RestrictPublicBuckets": True
        }
    )
    print("[OK] S3 public access blocked")


# ── 2. Glue database ─────────────────────────────────────────────────────────
def create_glue_db():
    try:
        glue.create_database(
            DatabaseInput={
                "Name": GLUE_DATABASE,
                "Description": "SODL MVP — partition advisor experiment"
            }
        )
        print(f"[OK] Glue database created: {GLUE_DATABASE}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "AlreadyExistsException":
            print(f"[OK] Glue database already exists: {GLUE_DATABASE}")
        else:
            raise


# ── 3. Athena workgroup ───────────────────────────────────────────────────────
def create_athena_workgroup():
    # Using the built-in 'primary' workgroup — no creation needed
    print(f"[OK] Athena workgroup: using '{ATHENA_WORKGROUP}' (built-in, no creation required)")


# ── 4. Verify IAM permissions (soft check) ───────────────────────────────────
def verify_permissions():
    """Check we can at least describe the bucket — catches missing IAM early."""
    try:
        s3.head_bucket(Bucket=S3_BUCKET)
        print("[OK] IAM: s3:HeadBucket confirmed")
    except ClientError as e:
        print(f"[WARN] IAM check failed: {e}")


if __name__ == "__main__":
    print("=== SODL MVP — Day 1: AWS Setup ===")
    create_bucket()
    create_glue_db()
    create_athena_workgroup()
    verify_permissions()
    print()
    print("Setup complete. Next: run 01_generate_data.py")
    print(f"  Bucket : s3://{S3_BUCKET}")
    print(f"  Glue DB: {GLUE_DATABASE}")
    print(f"  Athena : workgroup={ATHENA_WORKGROUP}")
