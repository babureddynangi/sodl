#!/usr/bin/env python3
"""
app/model/sm_train.py
SageMaker entry-point script — runs inside the managed container.
Reads features.csv from /opt/ml/input/data/train/, trains LR + RF,
saves best model to /opt/ml/model/model.pkl + metrics.json.
"""
import os, json, pickle, warnings, argparse
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from sklearn.exceptions import UndefinedMetricWarning

FEATURE_COLS = [
    "baseline_mean_runtime_ms", "baseline_mean_bytes",
    "optimized_mean_runtime_ms", "optimized_mean_bytes",
    "runtime_improvement_pct", "bytes_improvement_pct",
    "partition_scheme_baseline", "partition_scheme_optimized",
]
LABEL_COL = "improvement_label"


def evaluate(model, X_test, y_test, name):
    warnings.filterwarnings("ignore", category=UndefinedMetricWarning)
    y_pred = model.predict(X_test)
    m = {
        "model":     name,
        "accuracy":  round(accuracy_score(y_test, y_pred), 4),
        "precision": round(precision_score(y_test, y_pred, zero_division=0), 4),
        "recall":    round(recall_score(y_test, y_pred, zero_division=0), 4),
        "f1":        round(f1_score(y_test, y_pred, zero_division=0), 4),
    }
    if len(set(y_test)) > 1 and hasattr(model, "predict_proba"):
        m["roc_auc"] = round(roc_auc_score(y_test, model.predict_proba(X_test)[:, 1]), 4)
    else:
        m["roc_auc"] = None
    return m


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--model-dir", type=str, default=os.environ.get("SM_MODEL_DIR", "/opt/ml/model"))
    parser.add_argument("--train",      type=str, default=os.environ.get("SM_CHANNEL_TRAIN", "/opt/ml/input/data/train"))
    args = parser.parse_args()

    features_path = os.path.join(args.train, "features.csv")
    df = pd.read_csv(features_path)
    print(f"[SM] Loaded {len(df)} rows from {features_path}")

    X = df[FEATURE_COLS].fillna(0)
    y = df[LABEL_COL]

    stratify  = y if y.value_counts().min() >= 2 else None
    test_size = 0.2 if len(df) >= 10 else 0.0

    if test_size > 0:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=args.random_seed, stratify=stratify
        )
    else:
        X_train, X_test, y_train, y_test = X, X, y, y

    candidates = {
        "logistic_regression": LogisticRegression(random_state=args.random_seed, max_iter=1000),
        "random_forest":       RandomForestClassifier(n_estimators=50, random_state=args.random_seed),
    }

    all_metrics, trained = [], {}
    for name, clf in candidates.items():
        clf.fit(X_train, y_train)
        m = evaluate(clf, X_test, y_test, name)
        all_metrics.append(m)
        trained[name] = clf
        print(f"[SM]   {name:25s}  F1={m['f1']:.4f}  AUC={m.get('roc_auc','N/A')}")

    best_name  = max(all_metrics, key=lambda m: m["f1"])["model"]
    best_model = trained[best_name]
    print(f"[SM] Best model: {best_name}")

    os.makedirs(args.model_dir, exist_ok=True)

    artifact = {"model": best_model, "feature_cols": FEATURE_COLS, "model_name": best_name}
    with open(os.path.join(args.model_dir, "model.pkl"), "wb") as f:
        pickle.dump(artifact, f)

    metrics_out = {"best_model": best_name, "models": all_metrics, "feature_cols": FEATURE_COLS}
    with open(os.path.join(args.model_dir, "metrics.json"), "w") as f:
        json.dump(metrics_out, f, indent=2)

    print(f"[SM] Artifacts saved to {args.model_dir}")
