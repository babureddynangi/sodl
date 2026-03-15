# SODL Closed-Loop Prototype — Tech Steering

## Stack
- Python 3.10+
- pandas / pyarrow for data handling
- scikit-learn for predictor (logistic regression + random forest)
- boto3 for AWS (S3, Athena, Glue) — already configured in scripts/config.py
- pytest for tests
- existing scripts/ structure — new modules go in app/

## AWS services in use
- S3: sodl-mvp-bucket (already exists)
- Glue: sodl_mvp database, transactions_baseline + transactions_optimized tables (already registered)
- Athena: primary workgroup, output to s3://sodl-mvp-bucket/athena-results/

## Conventions
- All config via scripts/config.py — do not hardcode bucket names or regions
- New pipeline modules live in app/ subdirectories
- All experiment results stored as JSON + CSV in results/
- Reproducible seeds: RANDOM_SEED = 42 from config
- Benchmark runner (scripts/03_run_benchmark.py) is the source of truth for telemetry
- Never mutate transactions_baseline — executor creates new table copies only
