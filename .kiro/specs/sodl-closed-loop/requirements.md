# Requirements Document

## Introduction

This spec covers the remaining pipeline stages needed to complete the SODL closed-loop prototype. The benchmark runner, partition advisor, and before/after measurement already exist. This spec adds: feature engineering, ML predictor, confidence gate, safe executor, and paper-ready reporting — completing one full end-to-end optimization loop on AWS Athena.

## Glossary

- **Telemetry**: Structured benchmark run records (query_id, runtime_ms, bytes_scanned, partition_scheme, etc.) stored in results/baseline.csv and results/optimized.csv
- **Predictor**: A scikit-learn binary classifier that predicts whether a candidate partition layout will improve performance by ≥10%
- **Recommendation**: A structured object containing current layout, proposed layout, predicted improvement %, confidence score, and reason codes
- **Confidence Gate**: A rule-based filter that accepts or rejects a recommendation based on configurable thresholds
- **Executor**: The component that materialises an accepted recommendation as a new Glue/Athena table copy and triggers re-benchmarking
- **Pipeline**: The full sequence: features → predictor → recommender → gate → executor → reporter
- **Baseline Table**: `transactions_baseline` — must never be mutated
- **Optimized Table**: `transactions_optimized` — the pre-existing optimized layout used as ground truth

---

## Requirements

### Requirement 1: Feature Engineering

**User Story:** As a researcher, I want telemetry records transformed into ML-ready features so the predictor can learn from benchmark history.

#### Acceptance Criteria

1. WHEN telemetry CSV files are provided, THE Feature_Builder SHALL extract per-query features including: query_id, mean_runtime_ms, mean_bytes_scanned_mb, partition_scheme, filter_column_count, and improvement_label
2. WHEN baseline and optimized telemetry are both available, THE Feature_Builder SHALL compute improvement_label as 1 if optimized mean_runtime_ms is ≥10% lower than baseline, else 0
3. THE Feature_Builder SHALL encode partition_scheme as a numeric feature
4. WHEN output is written, THE Feature_Builder SHALL save the feature matrix to results/features.csv
5. IF a telemetry file is missing or malformed, THEN THE Feature_Builder SHALL raise a descriptive error and exit

---

### Requirement 2: ML Predictor

**User Story:** As a researcher, I want a trained model that predicts whether a candidate partition layout will improve benchmark performance.

#### Acceptance Criteria

1. WHEN features.csv is available, THE Trainer SHALL train both a logistic regression and a random forest classifier using scikit-learn
2. THE Trainer SHALL use RANDOM_SEED=42 for reproducibility
3. THE Trainer SHALL evaluate both models on a held-out test split and save accuracy, precision, recall, F1, and ROC-AUC to results/model_metrics.json
4. THE Trainer SHALL save the best-performing model artifact to results/model.pkl
5. WHEN the training dataset has fewer than 10 samples, THE Trainer SHALL log a warning and proceed with available data

---

### Requirement 3: Recommendation

**User Story:** As a researcher, I want the system to recommend one partition optimization action with a confidence score and human-readable rationale.

#### Acceptance Criteria

1. WHEN a trained model artifact exists, THE Recommender SHALL evaluate candidate partition layouts and return the top-ranked recommendation
2. THE Recommender SHALL include in the recommendation: current_layout, recommended_layout, predicted_improvement_pct, confidence, and reason_codes
3. THE Recommender SHALL save the recommendation to results/recommendation.json
4. WHEN no candidate layout scores above the minimum confidence threshold, THE Recommender SHALL return a no-recommendation result with reason

---

### Requirement 4: Confidence Gate

**User Story:** As a researcher, I want a safety gate that explicitly accepts or rejects recommendations based on configurable thresholds, with a full audit log.

#### Acceptance Criteria

1. WHEN a recommendation is provided, THE Gate SHALL accept it only if confidence >= GATE_MIN_CONFIDENCE AND predicted_improvement_pct >= GATE_MIN_IMPROVEMENT_PCT
2. THE Gate SHALL reject any recommendation where the benchmark sample count is below GATE_MIN_SAMPLES
3. THE Gate SHALL write a gate_decision.json containing: decision (accept/reject), confidence, predicted_improvement_pct, and gate_reason
4. THE Gate SHALL append every decision to results/gate_audit_log.jsonl
5. WHEN a recommendation is rejected, THE Gate SHALL log the specific threshold that was not met

---

### Requirement 5: Safe Executor

**User Story:** As a researcher, I want an accepted recommendation applied safely without mutating the baseline table.

#### Acceptance Criteria

1. WHEN a gate decision of "accept" is present, THE Executor SHALL verify the baseline Glue table exists before proceeding
2. THE Executor SHALL create a new Glue table named `transactions_exec_{timestamp}` rather than modifying any existing table
3. WHEN the new table is registered, THE Executor SHALL trigger a re-benchmark run using scripts/03_run_benchmark.py against the new table
4. THE Executor SHALL save post-execution telemetry to results/post_exec_benchmark.csv
5. IF Glue table creation fails, THEN THE Executor SHALL log the error, skip execution, and write a failed status to gate_decision.json

---

### Requirement 6: Before/After Reporter

**User Story:** As a researcher, I want a paper-ready before/after comparison report with correctness validation.

#### Acceptance Criteria

1. WHEN baseline and post-execution benchmark CSVs are available, THE Reporter SHALL compute median latency, P95 latency, mean bytes scanned, and a cost proxy (bytes_scanned_mb * 0.000005) for both
2. THE Reporter SHALL validate correctness by checking that row counts match between baseline and optimized tables via Athena COUNT(*) queries
3. THE Reporter SHALL write results/experiment_report.md containing a markdown table with before/after deltas and a correctness check row
4. WHEN H1 threshold (≥30% latency reduction) is met, THE Reporter SHALL mark the result as "H1: MET" in the report
5. THE Reporter SHALL include the gate decision and confidence score in the report

---

### Requirement 7: Pipeline Orchestrator

**User Story:** As a researcher, I want to run the full closed loop with a single command.

#### Acceptance Criteria

1. THE Pipeline SHALL execute stages in order: features → train → recommend → gate → execute → report
2. WHEN any stage fails, THE Pipeline SHALL stop and print the failing stage name and error
3. THE Pipeline SHALL print a summary of each stage result to stdout
4. WHEN the pipeline completes successfully, THE Pipeline SHALL print the path to experiment_report.md
