# Implementation Plan: SODL Closed-Loop Prototype

## Overview

Extends the existing MVP with feature engineering, ML predictor, confidence gate, safe executor, and paper-ready reporter — completing one full end-to-end optimization loop. All new code goes in `app/`. Existing `scripts/` are unchanged except for adding gate thresholds to `config.py`.

## Tasks

- [x] 1. Add gate thresholds to config and create app/ skeleton
  - Add `GATE_MIN_CONFIDENCE = 0.80`, `GATE_MIN_IMPROVEMENT_PCT = 10.0`, `GATE_MIN_SAMPLES = 5` to `scripts/config.py`
  - Create `app/__init__.py` and subdirectory `__init__.py` files for features/, model/, recommender/, gate/, executor/, reporter/
  - _Requirements: 4.1, 4.2_

- [x] 2. Implement Feature Builder
  - [x] 2.1 Implement `app/features/train_features.py`
    - Load baseline.csv and optimized.csv, aggregate mean runtime and bytes per query_id
    - Compute runtime_improvement_pct and bytes_improvement_pct
    - Compute improvement_label (1 if runtime_improvement_pct >= 10 else 0)
    - Encode partition_scheme as integer
    - Save to results/features.csv
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ]* 2.2 Write property test for improvement label consistency
    - **Property 1: Improvement label consistency**
    - **Validates: Requirements 1.2**
    - Use Hypothesis to generate random (baseline_ms, optimized_ms) pairs and verify label matches formula

  - [ ]* 2.3 Write property test for feature round-trip
    - **Property 2: Feature round-trip**
    - **Validates: Requirements 1.4**
    - Generate random telemetry pairs, write features.csv, read back, assert query_ids and labels match

- [x] 3. Implement Trainer
  - [x] 3.1 Implement `app/model/train.py`
    - Load features.csv, split 80/20 stratified with seed=42
    - Train LogisticRegression and RandomForestClassifier
    - Evaluate both: accuracy, precision, recall, F1, ROC-AUC
    - Save best model to results/model.pkl, all metrics to results/model_metrics.json
    - Handle < 10 samples with warning
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ]* 3.2 Write property test for training reproducibility
    - **Property: Training idempotence — running train.py twice on same data produces identical predictions**
    - **Validates: Requirements 2.2**

- [x] 4. Checkpoint — run features + trainer end-to-end
  - Run `python app/features/train_features.py` and `python app/model/train.py`
  - Verify results/features.csv and results/model.pkl exist
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement Recommender
  - [x] 5.1 Implement `app/recommender/recommend.py`
    - Load model.pkl and advisor_output.json
    - Use advisor's recommended_key and model predict_proba to set confidence
    - Build Recommendation object with current_layout, recommended_layout, predicted_improvement_pct, confidence, reason_codes
    - Save to results/recommendation.json
    - Return no-recommendation result if confidence < threshold
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ]* 5.2 Write property test for recommendation structure
    - **Property 3: Recommendation round-trip — write then read produces object with all required fields**
    - **Validates: Requirements 3.2, 3.3**

- [x] 6. Implement Confidence Gate
  - [x] 6.1 Implement `app/gate/gate.py`
    - Load recommendation.json and config thresholds
    - Accept if confidence >= GATE_MIN_CONFIDENCE AND predicted_improvement_pct >= GATE_MIN_IMPROVEMENT_PCT
    - Reject with specific gate_reason if any threshold fails
    - Write gate_decision.json
    - Append to gate_audit_log.jsonl
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 6.2 Write property test for gate threshold invariant
    - **Property 4: Gate threshold invariant — for any recommendation, decision is consistent with thresholds**
    - **Validates: Requirements 4.1, 4.2**

  - [ ]* 6.3 Write property test for audit log append-only
    - **Property 5: Audit log append-only — N gate evaluations produce exactly N log entries**
    - **Validates: Requirements 4.4**

- [x] 7. Checkpoint — run recommender + gate end-to-end
  - Run `python app/recommender/recommend.py` and `python app/gate/gate.py`
  - Verify results/recommendation.json and results/gate_decision.json exist
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement Executor
  - [x] 8.1 Implement `app/executor/execute.py`
    - Load gate_decision.json — exit cleanly if decision != "accept"
    - Verify transactions_baseline exists in Glue
    - Register new Glue table `transactions_exec_{timestamp}` pointing to existing optimized S3 path (reuse data, no new S3 writes)
    - Call `scripts/03_run_benchmark.py optimized` with new table name, save output to results/post_exec_benchmark.csv
    - On Glue failure: log error, write failed status to gate_decision.json, exit 1
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 8.2 Write property test for executor safety invariant
    - **Property 6: Executor never touches baseline — transactions_baseline schema unchanged after any executor run**
    - **Validates: Requirements 5.2**

- [x] 9. Implement Reporter
  - [x] 9.1 Implement `app/reporter/report.py`
    - Load baseline.csv and post_exec_benchmark.csv
    - Compute median latency, P95 latency, mean bytes scanned, cost proxy for both
    - Run Athena COUNT(*) on both tables for correctness check
    - Write results/experiment_report.md with markdown table, correctness row, gate decision, H1 check
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 9.2 Write property test for cost proxy monotonicity
    - **Property 7: Cost proxy monotonicity — higher bytes scanned always produces higher cost proxy**
    - **Validates: Requirements 6.1**

  - [ ]* 9.3 Write property test for H1 labeling
    - **Property 8: H1 labeling — for any latency reduction >= 30%, report contains "H1: MET"**
    - **Validates: Requirements 6.4**

- [x] 10. Implement Pipeline Orchestrator
  - [x] 10.1 Implement `app/run_pipeline.py`
    - Import and call each stage module in order: features → train → recommend → gate → execute → report
    - Catch exceptions per stage, print stage name + error, exit 1 on failure
    - Print stage-by-stage status and final path to experiment_report.md
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 11. Final checkpoint — full pipeline run
  - Run `python app/run_pipeline.py`
  - Verify experiment_report.md is created and contains H1 result and gate decision
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Executor reuses existing S3 data — zero additional storage cost
- All new Glue tables created by executor are safe to delete after the experiment
- Property tests use Hypothesis library (`pip install hypothesis`)
