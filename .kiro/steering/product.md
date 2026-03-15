# SODL Closed-Loop Prototype — Product Steering

## Goal
Demonstrate one live end-to-end self-optimizing data lake loop suitable for inclusion in an academic white paper.

## Scope
telemetry (benchmark CSV) → feature engineering → ML predictor → recommender → confidence gate → executor → re-benchmark → before/after report

## Non-goals
- No full 500 TB scale
- No multi-tenant scheduler
- No autonomous write optimization beyond one accepted partition action
- No SageMaker (model trains locally in Python)

## Success criteria
1. Ingest telemetry from existing benchmark runs (baseline.csv / optimized.csv)
2. Train a predictor from observed telemetry
3. Generate one recommendation with confidence score
4. Gate the decision (accept/reject with audit log)
5. Execute one safe optimization (new table copy, never mutate baseline)
6. Re-run benchmark and collect post-change telemetry
7. Show measurable before/after improvement with correctness validation

## Budget constraint
Keep Athena scan cost minimal — use existing Parquet tables already registered in Glue.
