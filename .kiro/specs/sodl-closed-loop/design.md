# Design Document: SODL Closed-Loop Prototype

## Overview

This design extends the existing SODL MVP (benchmark runner + partition advisor + results reporter) with the remaining pipeline stages to form a complete closed optimization loop. The loop runs entirely on AWS Athena/Glue using already-registered tables, with a local Python ML layer. No new AWS services are introduced.

The full pipeline:
```
results/baseline.csv
results/optimized.csv
       │
       ▼
[Feature Builder]  →  results/features.csv
       │
       ▼
[Trainer]          →  results/model.pkl + model_metrics.json
       │
       ▼
[Recommender]      →  results/recommendation.json
       │
       ▼
[Confidence Gate]  →  results/gate_decision.json + gate_audit_log.jsonl
       │
       ▼ (if accept)
[Executor]         →  Glue table: transactions_exec_{ts} + post_exec_benchmark.csv
       │
       ▼
[Reporter]         →  results/experiment_report.md
```

---

## Architecture

```
app/
  features/train_features.py   # Req 1
  model/train.py               # Req 2
  recommender/recommend.py     # Req 3
  gate/gate.py                 # Req 4
  executor/execute.py          # Req 5
  reporter/report.py           # Req 6
  run_pipeline.py              # Req 7
```

Each module is independently runnable and reads/writes from `results/`. The pipeline orchestrator calls them in sequence.

---

## Components and Interfaces

### Feature Builder (`app/features/train_features.py`)

Input: `results/baseline.csv`, `results/optimized.csv`
Output: `results/features.csv`

Per-query feature row:
```python
{
  "query_id": str,
  "baseline_mean_runtime_ms": float,
  "baseline_mean_bytes_mb": float,
  "optimized_mean_runtime_ms": float,
  "optimized_mean_bytes_mb": float,
  "runtime_improvement_pct": float,   # (baseline - optimized) / baseline * 100
  "bytes_improvement_pct": float,
  "improvement_label": int,           # 1 if runtime_improvement_pct >= 10 else 0
  "partition_scheme_baseline": int,   # 0 = date, 1 = category, 2 = none
  "partition_scheme_optimized": int,
}
```

### Trainer (`app/model/train.py`)

Input: `results/features.csv`
Output: `results/model.pkl`, `results/model_metrics.json`

- Train/test split: 80/20, stratified, seed=42
- Models: LogisticRegression, RandomForestClassifier
- Select best by F1 score
- Save metrics for both models

### Recommender (`app/recommender/recommend.py`)

Input: `results/model.pkl`, `results/advisor_output.json`
Output: `results/recommendation.json`

Uses the advisor's top candidate key + model confidence to produce:
```python
{
  "current_layout": "date",
  "recommended_layout": "merchant_category",
  "predicted_improvement_pct": float,
  "confidence": float,          # model predict_proba for class=1
  "reason_codes": [str],
  "model_used": str
}
```

### Confidence Gate (`app/gate/gate.py`)

Input: `results/recommendation.json`
Output: `results/gate_decision.json`, appends to `results/gate_audit_log.jsonl`

Thresholds (added to `scripts/config.py`):
```python
GATE_MIN_CONFIDENCE     = 0.80
GATE_MIN_IMPROVEMENT_PCT = 10.0
GATE_MIN_SAMPLES        = 5
```

Decision object:
```python
{
  "decision": "accept" | "reject",
  "confidence": float,
  "predicted_improvement_pct": float,
  "gate_reason": str,
  "timestamp": str
}
```

### Executor (`app/executor/execute.py`)

Input: `results/gate_decision.json`
Output: Glue table `transactions_exec_{timestamp}`, `results/post_exec_benchmark.csv`

Steps:
1. Read gate decision — abort if not "accept"
2. Verify `transactions_baseline` exists in Glue
3. Register new Glue table pointing to `s3://sodl-mvp-bucket/transactions/optimized/` (reuse existing S3 data, new table name only — zero S3 write cost)
4. Run `scripts/03_run_benchmark.py optimized` against new table, save to `post_exec_benchmark.csv`

Note: reusing existing optimized S3 data means zero additional S3 storage cost and no Athena DDL scan cost.

### Reporter (`app/reporter/report.py`)

Input: `results/baseline.csv`, `results/post_exec_benchmark.csv`, `results/gate_decision.json`
Output: `results/experiment_report.md`

Computes:
- Median latency before/after
- P95 latency before/after
- Mean bytes scanned before/after
- Cost proxy: bytes_scanned_mb × $0.000005 (Athena $5/TB)
- Correctness: Athena COUNT(*) on both tables must match
- H1 check: latency reduction ≥ 30%

### Pipeline Orchestrator (`app/run_pipeline.py`)

Calls each stage in sequence, catches exceptions, prints stage-by-stage status.

---

## Data Models

### TelemetryRecord
```python
@dataclass
class TelemetryRecord:
    query_id: str
    tag: str                  # "baseline" | "optimized"
    run: int
    engine_ms: Optional[float]
    bytes_scanned: Optional[float]
    status: str               # "SUCCEEDED" | "ERROR"
```

### FeatureRow
```python
@dataclass
class FeatureRow:
    query_id: str
    baseline_mean_runtime_ms: float
    baseline_mean_bytes_mb: float
    optimized_mean_runtime_ms: float
    optimized_mean_bytes_mb: float
    runtime_improvement_pct: float
    bytes_improvement_pct: float
    improvement_label: int
```

### Recommendation
```python
@dataclass
class Recommendation:
    current_layout: str
    recommended_layout: str
    predicted_improvement_pct: float
    confidence: float
    reason_codes: list[str]
    model_used: str
```

### GateDecision
```python
@dataclass
class GateDecision:
    decision: str             # "accept" | "reject"
    confidence: float
    predicted_improvement_pct: float
    gate_reason: str
    timestamp: str
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Improvement label consistency
*For any* pair of baseline and optimized telemetry records for the same query, if `runtime_improvement_pct >= 10` then `improvement_label == 1`, otherwise `improvement_label == 0`.
**Validates: Requirements 1.2**

### Property 2: Feature round-trip
*For any* valid telemetry CSV pair, writing features.csv and reading it back should produce a DataFrame with the same query_ids and improvement_labels.
**Validates: Requirements 1.4**

### Property 3: Gate threshold invariant
*For any* recommendation, if `confidence < GATE_MIN_CONFIDENCE` OR `predicted_improvement_pct < GATE_MIN_IMPROVEMENT_PCT`, then `gate_decision.decision == "reject"`.
**Validates: Requirements 4.1, 4.2**

### Property 4: Gate audit log append-only
*For any* sequence of N gate evaluations, the audit log must contain exactly N entries after all evaluations complete.
**Validates: Requirements 4.4**

### Property 5: Executor never touches baseline
*For any* executor run, the Glue table `transactions_baseline` must exist with the same schema before and after execution.
**Validates: Requirements 5.2**

### Property 6: Cost proxy monotonicity
*For any* two queries where query A scans more bytes than query B, the cost proxy for A must be strictly greater than the cost proxy for B.
**Validates: Requirements 6.1**

---

## Error Handling

| Stage | Error condition | Behaviour |
|-------|----------------|-----------|
| Feature Builder | Missing CSV | Raise ValueError with filename |
| Feature Builder | No overlapping query_ids | Raise ValueError |
| Trainer | < 10 samples | Log warning, proceed |
| Trainer | All labels same class | Log warning, skip ROC-AUC |
| Recommender | No model.pkl | Raise FileNotFoundError |
| Gate | Missing recommendation.json | Raise FileNotFoundError |
| Executor | Gate decision = reject | Print reason, exit 0 (not an error) |
| Executor | Glue table creation fails | Log error, write failed status, exit 1 |
| Reporter | Missing post_exec CSV | Raise FileNotFoundError |

---

## Testing Strategy

### Unit tests (pytest)
- Feature builder: label computation, encoding, missing file handling
- Gate: threshold boundary conditions (exactly at threshold, just below, just above)
- Reporter: cost proxy calculation, H1 check logic
- Pipeline: stage ordering, failure propagation

### Property-based tests (Hypothesis)
- Property 1: improvement label consistency across generated telemetry pairs
- Property 3: gate threshold invariant across generated recommendation objects
- Property 6: cost proxy monotonicity across generated byte scan values

Each property test runs minimum 100 iterations via Hypothesis `@given` decorator.
Tag format: `# Feature: sodl-closed-loop, Property N: <property_text>`

### Integration smoke test
- Run `python app/run_pipeline.py` against existing results/ artifacts
- Assert experiment_report.md is created and contains "H1:"
