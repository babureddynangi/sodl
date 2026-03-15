# SODL Closed-Loop Prototype — Structure Steering

## Directory layout
```
app/
  features/     # feature engineering from telemetry CSV
  model/        # training pipeline, artifacts, metrics
  recommender/  # ranks candidate layouts, emits top recommendation
  gate/         # confidence gate with audit log
  executor/     # safe table materialisation + re-benchmark trigger
  reporter/     # before/after comparison, paper-ready markdown
results/
  baseline.csv          # existing
  optimized.csv         # existing
  advisor_output.json   # existing
  model_metrics.json    # new
  recommendation.json   # new
  gate_decision.json    # new
  experiment_report.md  # new
```

## Module conventions
- One module per pipeline stage
- Each stage reads from results/ and writes to results/
- Config-driven thresholds (gate thresholds in config.py)
- All stages runnable standalone: python app/model/train.py
- Full pipeline runnable: python app/run_pipeline.py
