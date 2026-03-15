#!/usr/bin/env python3
"""
app/gate/gate.py
Confidence gate: accepts or rejects a recommendation based on configurable
thresholds. Writes gate_decision.json and appends to gate_audit_log.jsonl.

Usage:
  python app/gate/gate.py
"""
import sys, os, json
from datetime import datetime, timezone

sys.path.insert(0, ".")
from scripts.config import (
    LOCAL_RESULTS_DIR,
    GATE_MIN_CONFIDENCE,
    GATE_MIN_IMPROVEMENT_PCT,
    GATE_MIN_SAMPLES,
)


def evaluate(recommendation: dict) -> dict:
    """
    Apply gate rules to a recommendation dict.
    Returns a GateDecision dict.
    """
    confidence   = recommendation.get("confidence", 0.0)
    improvement  = recommendation.get("predicted_improvement_pct", 0.0)
    n_queries    = recommendation.get("n_queries_analyzed", 0)
    ts           = datetime.now(timezone.utc).isoformat()

    # Rule 1: no-recommendation result from recommender
    if "recommended_layout" not in recommendation or recommendation.get("recommended_layout") is None:
        return {
            "decision": "reject",
            "confidence": confidence,
            "predicted_improvement_pct": improvement,
            "gate_reason": f"recommender returned no recommendation: {recommendation.get('reason', 'unknown')}",
            "timestamp": ts,
        }

    # Rule 2: minimum samples
    if n_queries < GATE_MIN_SAMPLES:
        return {
            "decision": "reject",
            "confidence": confidence,
            "predicted_improvement_pct": improvement,
            "gate_reason": f"insufficient samples: {n_queries} < {GATE_MIN_SAMPLES}",
            "timestamp": ts,
        }

    # Rule 3: confidence threshold
    if confidence < GATE_MIN_CONFIDENCE:
        return {
            "decision": "reject",
            "confidence": confidence,
            "predicted_improvement_pct": improvement,
            "gate_reason": f"confidence {confidence:.4f} < threshold {GATE_MIN_CONFIDENCE}",
            "timestamp": ts,
        }

    # Rule 4: improvement threshold
    if improvement < GATE_MIN_IMPROVEMENT_PCT:
        return {
            "decision": "reject",
            "confidence": confidence,
            "predicted_improvement_pct": improvement,
            "gate_reason": f"predicted improvement {improvement:.1f}% < threshold {GATE_MIN_IMPROVEMENT_PCT}%",
            "timestamp": ts,
        }

    return {
        "decision": "accept",
        "confidence": confidence,
        "predicted_improvement_pct": improvement,
        "gate_reason": "passes_all_thresholds",
        "recommended_layout": recommendation.get("recommended_layout"),
        "current_layout": recommendation.get("current_layout"),
        "timestamp": ts,
    }


def run_gate(rec_path: str, decision_out: str, audit_log: str) -> dict:
    if not os.path.exists(rec_path):
        raise FileNotFoundError(f"Recommendation file not found: {rec_path}")

    with open(rec_path) as f:
        recommendation = json.load(f)

    decision = evaluate(recommendation)

    with open(decision_out, "w") as f:
        json.dump(decision, f, indent=2)
    print(f"[OK] Gate decision saved: {decision_out}")

    # Append to audit log
    with open(audit_log, "a") as f:
        f.write(json.dumps(decision) + "\n")
    print(f"[OK] Audit log updated: {audit_log}")

    return decision


if __name__ == "__main__":
    rec_path     = os.path.join(LOCAL_RESULTS_DIR, "recommendation.json")
    decision_out = os.path.join(LOCAL_RESULTS_DIR, "gate_decision.json")
    audit_log    = os.path.join(LOCAL_RESULTS_DIR, "gate_audit_log.jsonl")

    print("=== Confidence Gate ===")
    decision = run_gate(rec_path, decision_out, audit_log)

    status = "✅ ACCEPTED" if decision["decision"] == "accept" else "❌ REJECTED"
    print(f"\n  Decision          : {status}")
    print(f"  Confidence        : {decision['confidence']:.4f}  (threshold: {GATE_MIN_CONFIDENCE})")
    print(f"  Predicted gain    : {decision['predicted_improvement_pct']:.1f}%  "
          f"(threshold: {GATE_MIN_IMPROVEMENT_PCT}%)")
    print(f"  Reason            : {decision['gate_reason']}")
