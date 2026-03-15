#!/usr/bin/env python3
"""
app/recommender/recommend.py
Loads the trained model and advisor output, produces one top recommendation
with confidence score and reason codes.

Usage:
  python app/recommender/recommend.py
"""
import sys, os, json, pickle
import pandas as pd
import numpy as np

sys.path.insert(0, ".")
from scripts.config import LOCAL_RESULTS_DIR, GATE_MIN_CONFIDENCE

FEATURE_COLS = [
    "baseline_mean_runtime_ms",
    "baseline_mean_bytes",
    "optimized_mean_runtime_ms",
    "optimized_mean_bytes",
    "runtime_improvement_pct",
    "bytes_improvement_pct",
    "partition_scheme_baseline",
    "partition_scheme_optimized",
]


def load_model(model_path: str):
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model artifact not found: {model_path}")
    with open(model_path, "rb") as f:
        return pickle.load(f)


def build_reason_codes(features: pd.DataFrame, advisor: dict) -> list:
    reasons = []
    best_key = advisor.get("recommended_key", "unknown")
    freq = advisor.get("column_query_frequency", {}).get(best_key, 0)
    total = advisor.get("total_queries_analyzed", 1)
    ig = advisor.get("recommended_ig_score", 0)

    if freq / max(total, 1) >= 0.8:
        reasons.append(f"'{best_key}' is a filter predicate in {freq}/{total} queries")
    if ig > 0.5:
        reasons.append(f"high information gain score ({ig:.4f})")
    mean_imp = features["runtime_improvement_pct"].mean()
    if mean_imp >= 30:
        reasons.append(f"historical mean runtime improvement {mean_imp:.1f}%")
    mean_bytes = features["bytes_improvement_pct"].mean()
    if mean_bytes >= 50:
        reasons.append(f"historical mean bytes reduction {mean_bytes:.1f}%")
    if not reasons:
        reasons.append("partition advisor recommends repartitioning")
    return reasons


def recommend(features_path: str, model_path: str, advisor_path: str, out_path: str) -> dict:
    artifact = load_model(model_path)
    model = artifact["model"]

    if not os.path.exists(features_path):
        raise FileNotFoundError(f"Features file not found: {features_path}")
    features = pd.read_csv(features_path)

    if not os.path.exists(advisor_path):
        raise FileNotFoundError(f"Advisor output not found: {advisor_path}")
    with open(advisor_path) as f:
        advisor = json.load(f)

    # Use aggregate feature row (mean across all queries) for prediction
    X = features[FEATURE_COLS].fillna(0).mean().to_frame().T

    confidence = float(model.predict_proba(X)[0][1]) if hasattr(model, "predict_proba") else 0.5
    predicted_improvement_pct = float(features["runtime_improvement_pct"].mean())

    current_layout    = advisor.get("current_partition_key", "transaction_date")
    recommended_layout = advisor.get("recommended_key", "merchant_category")
    reason_codes      = build_reason_codes(features, advisor)
    model_name        = artifact.get("model_name", "unknown")

    if confidence < GATE_MIN_CONFIDENCE:
        result = {
            "recommendation": None,
            "reason": f"confidence {confidence:.4f} below threshold {GATE_MIN_CONFIDENCE}",
        }
    else:
        result = {
            "current_layout":            current_layout,
            "recommended_layout":        recommended_layout,
            "predicted_improvement_pct": round(predicted_improvement_pct, 2),
            "confidence":                round(confidence, 4),
            "reason_codes":              reason_codes,
            "model_used":                model_name,
            "n_queries_analyzed":        len(features),
        }

    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"[OK] Recommendation saved: {out_path}")
    return result


if __name__ == "__main__":
    features_path = os.path.join(LOCAL_RESULTS_DIR, "features.csv")
    model_path    = os.path.join(LOCAL_RESULTS_DIR, "model.pkl")
    advisor_path  = os.path.join(LOCAL_RESULTS_DIR, "advisor_output.json")
    out_path      = os.path.join(LOCAL_RESULTS_DIR, "recommendation.json")

    print("=== Recommender ===")
    result = recommend(features_path, model_path, advisor_path, out_path)

    if result.get("recommendation") is None and "reason" in result:
        print(f"No recommendation: {result['reason']}")
    else:
        print(f"  Current layout    : {result['current_layout']}")
        print(f"  Recommended layout: {result['recommended_layout']}")
        print(f"  Predicted gain    : {result['predicted_improvement_pct']:.1f}%")
        print(f"  Confidence        : {result['confidence']:.4f}")
        print(f"  Reasons           : {result['reason_codes']}")
