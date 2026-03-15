#!/usr/bin/env python3
"""
app/model/train.py
Trains the partition-improvement classifier via SageMaker SKLearn estimator.

Execution modes (automatic fallback):
  1. SageMaker cloud  — used when SAGEMAKER_INSTANCE is an ml.* type and quota allows
  2. SageMaker local  — used when SAGEMAKER_INSTANCE="local" and Docker is available
  3. Local fallback   — runs sm_train.py directly when SageMaker is unavailable

The model artifact format (model.pkl + model_metrics.json) is identical in all modes
so the rest of the pipeline is unaffected.

Usage:
  python app/model/train.py
"""
import sys, os, json, pickle, tarfile, tempfile, time
sys.path.insert(0, ".")

from scripts.config import (
    AWS_REGION, S3_BUCKET, S3_PREFIX_SAGEMAKER,
    LOCAL_RESULTS_DIR, RANDOM_SEED,
    SAGEMAKER_ROLE, SAGEMAKER_INSTANCE, SAGEMAKER_FRAMEWORK,
)

FEATURE_COLS = [
    "baseline_mean_runtime_ms", "baseline_mean_bytes",
    "optimized_mean_runtime_ms", "optimized_mean_bytes",
    "runtime_improvement_pct", "bytes_improvement_pct",
    "partition_scheme_baseline", "partition_scheme_optimized",
]


def _train_via_sagemaker(features_path: str, model_out: str, metrics_out: str):
    """Launch a SageMaker SKLearn training job (cloud or local mode)."""
    import boto3
    from sagemaker.sklearn.estimator import SKLearn
    import sagemaker

    session    = boto3.Session(region_name=AWS_REGION)
    s3         = session.client("s3")
    sm_session = sagemaker.Session(boto_session=session)

    # Upload features.csv to S3
    s3_key = f"{S3_PREFIX_SAGEMAKER}input/features.csv"
    s3.upload_file(features_path, S3_BUCKET, s3_key)
    train_uri = f"s3://{S3_BUCKET}/{S3_PREFIX_SAGEMAKER}input/"
    print(f"[SM] Uploaded features → {train_uri}")

    estimator = SKLearn(
        entry_point       = "sm_train.py",
        source_dir        = "app/model",
        role              = SAGEMAKER_ROLE,
        instance_type     = SAGEMAKER_INSTANCE,
        framework_version = SAGEMAKER_FRAMEWORK,
        py_version        = "py3",
        sagemaker_session = sm_session,
        output_path       = f"s3://{S3_BUCKET}/{S3_PREFIX_SAGEMAKER}output/",
        hyperparameters   = {"random-seed": RANDOM_SEED},
        base_job_name     = "sodl-partition-classifier",
    )

    print(f"[SM] Launching training job (instance={SAGEMAKER_INSTANCE})...")
    estimator.fit({"train": train_uri}, wait=False)
    job_name = estimator.latest_training_job.name
    print(f"[SM] Job: {job_name}")

    # Poll until done
    sm_client = session.client("sagemaker")
    while True:
        resp  = sm_client.describe_training_job(TrainingJobName=job_name)
        state = resp["TrainingJobStatus"]
        print(f"[SM]   status: {state}")
        if state in ("Completed", "Failed", "Stopped"):
            if state != "Completed":
                raise RuntimeError(f"SageMaker job {state}: {resp.get('FailureReason','')}")
            break
        time.sleep(15)

    # Download + extract model artifact
    s3_uri = resp["ModelArtifacts"]["S3ModelArtifacts"]
    bucket = s3_uri.split("/")[2]
    key    = "/".join(s3_uri.split("/")[3:])
    with tempfile.TemporaryDirectory() as tmp:
        tar_path = os.path.join(tmp, "model.tar.gz")
        s3.download_file(bucket, key, tar_path)
        print(f"[SM] Downloaded artifact: {s3_uri}")
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(tmp)
        _save_artifacts(
            os.path.join(tmp, "model.pkl"),
            os.path.join(tmp, "metrics.json"),
            model_out, metrics_out,
        )


def _train_local(features_path: str, model_out: str, metrics_out: str):
    """Run sm_train.py directly in-process (no Docker/quota needed)."""
    print("[SM] SageMaker unavailable — running sm_train.py locally")
    with tempfile.TemporaryDirectory() as tmp:
        # Simulate SM environment variables
        os.environ["SM_MODEL_DIR"]      = tmp
        os.environ["SM_CHANNEL_TRAIN"]  = os.path.dirname(features_path)

        # Copy features.csv into the expected channel path if needed
        import shutil
        dst = os.path.join(os.path.dirname(features_path), "features.csv")
        if os.path.abspath(features_path) != os.path.abspath(dst):
            shutil.copy(features_path, dst)

        # Run the entry-point script in-process
        import importlib.util
        spec = importlib.util.spec_from_file_location("sm_train", "app/model/sm_train.py")
        mod  = importlib.util.module_from_spec(spec)
        # Patch sys.argv so argparse picks up the right model-dir
        old_argv = sys.argv
        sys.argv = ["sm_train.py", "--model-dir", tmp,
                    "--train", os.path.dirname(features_path),
                    "--random-seed", str(RANDOM_SEED)]
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.argv = old_argv

        _save_artifacts(
            os.path.join(tmp, "model.pkl"),
            os.path.join(tmp, "metrics.json"),
            model_out, metrics_out,
        )


def _save_artifacts(src_model: str, src_metrics: str, model_out: str, metrics_out: str):
    os.makedirs(os.path.dirname(model_out) or ".", exist_ok=True)
    with open(src_model, "rb") as f:   artifact = pickle.load(f)
    with open(model_out, "wb") as f:   pickle.dump(artifact, f)
    with open(src_metrics) as f:       metrics  = json.load(f)
    with open(metrics_out, "w") as f:  json.dump(metrics, f, indent=2)
    print(f"[OK] Model saved   : {model_out}")
    print(f"[OK] Metrics saved : {metrics_out}")
    best = metrics.get("best_model", "?")
    bm   = next((m for m in metrics.get("models", []) if m["model"] == best), {})
    print(f"[OK] Best model    : {best}  F1={bm.get('f1','?')}  AUC={bm.get('roc_auc','?')}")
    return artifact["model"], metrics.get("models", [])


def train(features_path: str, model_out: str, metrics_out: str):
    try:
        _train_via_sagemaker(features_path, model_out, metrics_out)
    except Exception as e:
        print(f"[WARN] SageMaker training failed ({type(e).__name__}: {e})")
        print("[WARN] Falling back to local execution of sm_train.py")
        _train_local(features_path, model_out, metrics_out)

    with open(model_out, "rb") as f:
        artifact = pickle.load(f)
    with open(metrics_out) as f:
        metrics = json.load(f)
    return artifact["model"], metrics.get("models", [])


if __name__ == "__main__":
    features_path = os.path.join(LOCAL_RESULTS_DIR, "features.csv")
    model_out     = os.path.join(LOCAL_RESULTS_DIR, "model.pkl")
    metrics_out   = os.path.join(LOCAL_RESULTS_DIR, "model_metrics.json")
    print("=== Trainer (SageMaker + local fallback) ===")
    train(features_path, model_out, metrics_out)
