#!/usr/bin/env python3
"""
app/run_pipeline.py
Full closed-loop pipeline orchestrator.
Runs all stages in order: features → train → recommend → gate → execute → report

Usage:
  python app/run_pipeline.py
"""
import sys, os, traceback
from datetime import datetime, timezone

sys.path.insert(0, ".")
from scripts.config import LOCAL_RESULTS_DIR

STAGES = [
    ("Feature Builder",    "app.features.train_features",  "build_features"),
    ("Trainer",            "app.model.train",               "train"),
    ("Recommender",        "app.recommender.recommend",     "recommend"),
    ("Confidence Gate",    "app.gate.gate",                 "run_gate"),
    ("Executor",           "app.executor.execute",          "execute"),
    ("Reporter",           "app.reporter.report",           "generate_report"),
]


def run_stage(name: str, module_path: str, fn_name: str, kwargs: dict):
    import importlib
    print(f"\n{'─'*50}")
    print(f"[{name}]")
    mod = importlib.import_module(module_path)
    fn  = getattr(mod, fn_name)
    result = fn(**kwargs)
    print(f"[OK] {name} complete")
    return result


def main():
    r = LOCAL_RESULTS_DIR
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"{'='*50}")
    print(f"SODL Closed-Loop Pipeline")
    print(f"Started: {ts}")
    print(f"{'='*50}")

    stage_args = [
        {
            "baseline_path":  os.path.join(r, "baseline.csv"),
            "optimized_path": os.path.join(r, "optimized.csv"),
            "out_path":       os.path.join(r, "features.csv"),
        },
        {
            "features_path": os.path.join(r, "features.csv"),
            "model_out":     os.path.join(r, "model.pkl"),
            "metrics_out":   os.path.join(r, "model_metrics.json"),
        },
        {
            "features_path": os.path.join(r, "features.csv"),
            "model_path":    os.path.join(r, "model.pkl"),
            "advisor_path":  os.path.join(r, "advisor_output.json"),
            "out_path":      os.path.join(r, "recommendation.json"),
        },
        {
            "rec_path":     os.path.join(r, "recommendation.json"),
            "decision_out": os.path.join(r, "gate_decision.json"),
            "audit_log":    os.path.join(r, "gate_audit_log.jsonl"),
        },
        {
            "decision_path": os.path.join(r, "gate_decision.json"),
            "post_exec_out": os.path.join(r, "post_exec_benchmark.csv"),
        },
        {
            "baseline_path":  os.path.join(r, "baseline.csv"),
            "post_exec_path": os.path.join(r, "post_exec_benchmark.csv"),
            "decision_path":  os.path.join(r, "gate_decision.json"),
            "out_path":       os.path.join(r, "experiment_report.md"),
            "audit_log_path": os.path.join(r, "gate_audit_log.jsonl"),
        },
    ]

    for (name, module, fn), kwargs in zip(STAGES, stage_args):
        try:
            run_stage(name, module, fn, kwargs)
        except Exception as e:
            print(f"\n[FAILED] Stage '{name}' raised an error:")
            traceback.print_exc()
            sys.exit(1)

    report_path = os.path.join(r, "experiment_report.md")
    print(f"\n{'='*50}")
    print(f"Pipeline complete.")
    print(f"Report: {report_path}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
