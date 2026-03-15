#!/usr/bin/env python3
"""
app/model/train.py
Trains logistic regression and random forest classifiers on features.csv.
Saves best model to results/model.pkl and metrics to results/model_metrics.json.

Usage:
  python app/model/train.py
"""
import sys, os, json, pickle, warnings
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from sklearn.exceptions import UndefinedMetricWarning

sys.path.insert(0, ".")
from scripts.config import LOCAL_RESULTS_DIR, RANDOM_SEED

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
LABEL_COL = "improvement_label"
MIN_SAMPLES_WARN = 10


def evaluate(model, X_test, y_test, name: str) -> dict:
    warnings.filterwarnings("ignore", category=UndefinedMetricWarning)
    y_pred = model.predict(X_test)
    metrics = {
        "model": name,
        "accuracy":  round(accuracy_score(y_test, y_pred), 4),
        "precision": round(precision_score(y_test, y_pred, zero_division=0), 4),
        "recall":    round(recall_score(y_test, y_pred, zero_division=0), 4),
        "f1":        round(f1_score(y_test, y_pred, zero_division=0), 4),
    }
    # ROC-AUC requires both classes present
    if len(set(y_test)) > 1 and hasattr(model, "predict_proba"):
        y_prob = model.predict_proba(X_test)[:, 1]
        metrics["roc_auc"] = round(roc_auc_score(y_test, y_prob), 4)
    else:
        metrics["roc_auc"] = None
    return metrics


def train(features_path: str, model_out: str, metrics_out: str):
    df = pd.read_csv(features_path)

    if len(df) < MIN_SAMPLES_WARN:
        print(f"[WARN] Only {len(df)} samples — model may not generalise well.")

    X = df[FEATURE_COLS].fillna(0)
    y = df[LABEL_COL]

    # With very small datasets, skip stratified split if a class has < 2 members
    stratify = y if y.value_counts().min() >= 2 else None
    test_size = 0.2 if len(df) >= 10 else 0.0

    if test_size > 0:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=RANDOM_SEED, stratify=stratify
        )
    else:
        X_train, X_test, y_train, y_test = X, X, y, y

    models = {
        "logistic_regression": LogisticRegression(random_state=RANDOM_SEED, max_iter=1000),
        "random_forest":       RandomForestClassifier(n_estimators=50, random_state=RANDOM_SEED),
    }

    all_metrics = []
    trained = {}
    for name, clf in models.items():
        clf.fit(X_train, y_train)
        m = evaluate(clf, X_test, y_test, name)
        all_metrics.append(m)
        trained[name] = clf
        print(f"  {name:25s}  F1={m['f1']:.4f}  AUC={m.get('roc_auc', 'N/A')}")

    # Pick best by F1
    best_name = max(all_metrics, key=lambda m: m["f1"])["model"]
    best_model = trained[best_name]
    print(f"\n[OK] Best model: {best_name}")

    os.makedirs(os.path.dirname(model_out) if os.path.dirname(model_out) else ".", exist_ok=True)
    with open(model_out, "wb") as f:
        pickle.dump({"model": best_model, "feature_cols": FEATURE_COLS, "model_name": best_name}, f)
    print(f"[OK] Model saved: {model_out}")

    output = {"best_model": best_name, "models": all_metrics, "feature_cols": FEATURE_COLS}
    with open(metrics_out, "w") as f:
        json.dump(output, f, indent=2)
    print(f"[OK] Metrics saved: {metrics_out}")

    return best_model, all_metrics


if __name__ == "__main__":
    features_path = os.path.join(LOCAL_RESULTS_DIR, "features.csv")
    model_out     = os.path.join(LOCAL_RESULTS_DIR, "model.pkl")
    metrics_out   = os.path.join(LOCAL_RESULTS_DIR, "model_metrics.json")

    print("=== Trainer ===")
    train(features_path, model_out, metrics_out)
