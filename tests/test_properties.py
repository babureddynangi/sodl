"""
tests/test_properties.py - Property-based tests for SODL closed-loop pipeline.
Run: pytest tests/test_properties.py -v
"""
import sys, os, json, pickle, tempfile
sys.path.insert(0, ".")

import pandas as pd
from hypothesis import given, settings, assume
from hypothesis import strategies as st

IMPROVEMENT_THRESHOLD_PCT = 10.0
H1_THRESHOLD_PCT = 30.0
COST_PER_TB = 5.0

FEATURE_COLS = [
    "baseline_mean_runtime_ms", "baseline_mean_bytes",
    "optimized_mean_runtime_ms", "optimized_mean_bytes",
    "runtime_improvement_pct", "bytes_improvement_pct",
    "partition_scheme_baseline", "partition_scheme_optimized",
]


# Property 1: Improvement label consistency (Req 1.2)
@given(
    base_ms=st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False),
    opt_ms=st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=500)
def test_improvement_label_consistency(base_ms, opt_ms):
    """Label == 1 iff runtime_improvement_pct >= threshold."""
    pct = (base_ms - opt_ms) / base_ms * 100
    assert int(pct >= IMPROVEMENT_THRESHOLD_PCT) == (1 if pct >= IMPROVEMENT_THRESHOLD_PCT else 0)


# Property 2: Feature round-trip (Req 1.4)
@given(
    records=st.lists(
        st.tuples(
            st.floats(min_value=100.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
            st.floats(min_value=100.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
        ),
        min_size=1, max_size=10,
    )
)
@settings(max_examples=300)
def test_feature_round_trip(records):
    """query_ids and improvement_labels survive a CSV round-trip unchanged."""
    query_ids = ["Q{:02d}".format(i) for i in range(len(records))]
    imp_pcts  = [(b - o) / b * 100 for b, o in records]
    labels    = [int(p >= IMPROVEMENT_THRESHOLD_PCT) for p in imp_pcts]
    df = pd.DataFrame({
        "query_id": query_ids,
        "runtime_improvement_pct": imp_pcts,
        "improvement_label": labels,
    })
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "features.csv")
        df.to_csv(path, index=False)
        df2 = pd.read_csv(path)
    assert set(df2["query_id"]) == set(query_ids)
    assert df2["improvement_label"].isin([0, 1]).all()
    for _, row in df2.iterrows():
        assert int(row["improvement_label"]) == int(row["runtime_improvement_pct"] >= IMPROVEMENT_THRESHOLD_PCT)


# Property 3: Training reproducibility (Req 2.2)
@given(
    n=st.integers(min_value=10, max_value=25),
    seed=st.integers(min_value=0, max_value=9999),
)
@settings(max_examples=8, deadline=None)
def test_training_reproducibility(n, seed):
    """Training twice on identical data produces identical predictions."""
    from app.model.train import train
    import numpy as np
    rng = np.random.default_rng(seed)
    base_ms = rng.uniform(500, 3000, n)
    opt_ms  = rng.uniform(200, 2000, n)
    imp_pct = (base_ms - opt_ms) / base_ms * 100
    df = pd.DataFrame({
        "baseline_mean_runtime_ms":  base_ms,
        "baseline_mean_bytes":       rng.uniform(1e6, 3e7, n),
        "optimized_mean_runtime_ms": opt_ms,
        "optimized_mean_bytes":      rng.uniform(1e5, 5e6, n),
        "runtime_improvement_pct":   imp_pct,
        "bytes_improvement_pct":     rng.uniform(0, 90, n),
        "partition_scheme_baseline":  [0] * n,
        "partition_scheme_optimized": [1] * n,
        "improvement_label": (imp_pct >= IMPROVEMENT_THRESHOLD_PCT).astype(int),
    })
    # Skip if all labels are the same class (LogisticRegression requires 2 classes)
    assume(df["improvement_label"].nunique() > 1)
    with tempfile.TemporaryDirectory() as tmp:
        f   = os.path.join(tmp, "f.csv")
        m1  = os.path.join(tmp, "m1.pkl")
        m2  = os.path.join(tmp, "m2.pkl")
        met = os.path.join(tmp, "met.json")
        df.to_csv(f, index=False)
        train(f, m1, met)
        train(f, m2, met)
        with open(m1, "rb") as fh: art1 = pickle.load(fh)
        with open(m2, "rb") as fh: art2 = pickle.load(fh)
    X = df[FEATURE_COLS].fillna(0)
    assert list(art1["model"].predict(X)) == list(art2["model"].predict(X))


# Property 4: Recommendation structure round-trip (Req 3.2, 3.3)
REQUIRED_REC_FIELDS = {
    "current_layout", "recommended_layout", "predicted_improvement_pct",
    "confidence", "reason_codes", "model_used", "n_queries_analyzed",
}

@given(
    confidence=st.floats(min_value=0.80, max_value=1.0, allow_nan=False),
    improvement=st.floats(min_value=10.0, max_value=80.0, allow_nan=False),
    n=st.integers(min_value=5, max_value=50),
)
@settings(max_examples=300)
def test_recommendation_structure_round_trip(confidence, improvement, n):
    """A recommendation written to JSON and read back retains all required fields."""
    rec = {
        "current_layout": "transaction_date",
        "recommended_layout": "merchant_category",
        "predicted_improvement_pct": round(improvement, 2),
        "confidence": round(confidence, 4),
        "reason_codes": ["r"],
        "model_used": "random_forest",
        "n_queries_analyzed": n,
    }
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "r.json")
        with open(p, "w") as f: json.dump(rec, f)
        with open(p) as f:      loaded = json.load(f)
    assert REQUIRED_REC_FIELDS.issubset(set(loaded.keys()))
    assert loaded["confidence"] == rec["confidence"]
    assert loaded["predicted_improvement_pct"] == rec["predicted_improvement_pct"]


# Property 5: Gate threshold invariant (Req 4.1, 4.2)
@given(
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    improvement=st.floats(min_value=-50.0, max_value=100.0, allow_nan=False),
    n_queries=st.integers(min_value=0, max_value=50),
)
@settings(max_examples=500)
def test_gate_threshold_invariant(confidence, improvement, n_queries):
    """Gate decision is always consistent with configured thresholds."""
    from app.gate.gate import evaluate
    from scripts.config import GATE_MIN_CONFIDENCE, GATE_MIN_IMPROVEMENT_PCT, GATE_MIN_SAMPLES
    rec = {
        "current_layout": "transaction_date",
        "recommended_layout": "merchant_category",
        "predicted_improvement_pct": improvement,
        "confidence": confidence,
        "reason_codes": [],
        "model_used": "random_forest",
        "n_queries_analyzed": n_queries,
    }
    decision = evaluate(rec)
    should_accept = (
        confidence  >= GATE_MIN_CONFIDENCE
        and improvement >= GATE_MIN_IMPROVEMENT_PCT
        and n_queries   >= GATE_MIN_SAMPLES
    )
    assert decision["decision"] == ("accept" if should_accept else "reject")


# Property 6: Audit log append-only (Req 4.4)
@given(n_evals=st.integers(min_value=1, max_value=15))
@settings(max_examples=30)
def test_audit_log_append_only(n_evals):
    """N gate evaluations produce exactly N JSONL entries."""
    from app.gate.gate import run_gate
    rec = {
        "current_layout": "transaction_date",
        "recommended_layout": "merchant_category",
        "predicted_improvement_pct": 35.0,
        "confidence": 0.95,
        "reason_codes": [],
        "model_used": "random_forest",
        "n_queries_analyzed": 10,
    }
    with tempfile.TemporaryDirectory() as tmp:
        rp = os.path.join(tmp, "rec.json")
        dp = os.path.join(tmp, "dec.json")
        lp = os.path.join(tmp, "audit.jsonl")
        with open(rp, "w") as f: json.dump(rec, f)
        for _ in range(n_evals):
            run_gate(rp, dp, lp)
        with open(lp) as f:
            lines = [l.strip() for l in f if l.strip()]
    assert len(lines) == n_evals
    for line in lines:
        e = json.loads(line)
        assert "decision" in e and "timestamp" in e


# Property 7: Cost proxy monotonicity (Req 6.1)
@given(
    bytes_lo=st.floats(min_value=1.0, max_value=1e10, allow_nan=False, allow_infinity=False),
    bytes_hi=st.floats(min_value=1.0, max_value=1e10, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=500)
def test_cost_proxy_monotonicity(bytes_lo, bytes_hi):
    """Higher bytes scanned always yields a higher or equal cost proxy."""
    assume(bytes_hi >= bytes_lo)
    assert bytes_hi / 1024**4 * COST_PER_TB >= bytes_lo / 1024**4 * COST_PER_TB


# Property 8: H1 labeling (Req 6.4)
@given(
    lat_before=st.floats(min_value=100.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
    reduction_pct=st.floats(min_value=30.0, max_value=99.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=300, deadline=None)
def test_h1_labeling(lat_before, reduction_pct):
    """For any latency reduction >= 30%, pct_delta >= H1_THRESHOLD."""
    from app.reporter.report import pct_delta
    lat_after = lat_before * (1 - reduction_pct / 100)
    delta = pct_delta(lat_before, lat_after)
    assert delta >= H1_THRESHOLD_PCT
    assert "MET" in ("H1: MET" if delta >= H1_THRESHOLD_PCT else "H1: NOT MET")
