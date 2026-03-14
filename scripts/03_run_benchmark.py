#!/usr/bin/env python3
"""
03_run_benchmark.py  —  Day 3
Runs 25 benchmark queries against a Glue/Athena table N times.
Captures latency (ms) and bytes scanned for each execution.
Saves results to CSV.

Usage:
  python 03_run_benchmark.py baseline     # run against baseline table
  python 03_run_benchmark.py optimized    # run against optimized table
  python 03_run_benchmark.py both         # run both sequentially (default)
"""
import sys, os, time, csv, re
import boto3
sys.path.insert(0, ".")
from config import (
    AWS_REGION, AWS_PROFILE, GLUE_DATABASE,
    GLUE_TABLE_BASELINE, GLUE_TABLE_OPTIMIZED,
    ATHENA_WORKGROUP, ATHENA_OUTPUT_LOC, BENCHMARK_RUNS, QUERY_TIMEOUT_SEC,
    LOCAL_RESULTS_DIR, LOCAL_SQL_DIR
)

session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
ath = session.client("athena")


# ── Query loader ──────────────────────────────────────────────────────────────
def load_queries(sql_file: str) -> list[dict]:
    """Parse SQL file into list of {id, label, sql} dicts."""
    with open(sql_file) as f:
        content = f.read()

    queries = []
    # Split on "-- Q" comment markers
    parts = re.split(r"\n-- (Q\d+):\s*(.+?)\n", content)
    # parts = [preamble, id, label, sql, id, label, sql, ...]
    for i in range(1, len(parts), 3):
        qid   = parts[i]
        label = parts[i+1]
        sql   = parts[i+2].strip().rstrip(";")
        if sql:
            queries.append({"id": qid, "label": label, "sql": sql})
    return queries


# ── Athena runner ─────────────────────────────────────────────────────────────
def run_query(sql: str, timeout: int = QUERY_TIMEOUT_SEC) -> dict:
    """
    Execute one Athena query.
    Returns: {execution_id, status, latency_ms, bytes_scanned, rows_returned}
    """
    start = time.monotonic()

    resp = ath.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": GLUE_DATABASE},
        ResultConfiguration={"OutputLocation": ATHENA_OUTPUT_LOC},
        WorkGroup=ATHENA_WORKGROUP
    )
    exec_id = resp["QueryExecutionId"]

    # Poll until complete
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(1.5)
        status_resp = ath.get_query_execution(QueryExecutionId=exec_id)
        state = status_resp["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break

    elapsed_ms = int((time.monotonic() - start) * 1000)

    if state != "SUCCEEDED":
        reason = status_resp["QueryExecution"]["Status"].get("StateChangeReason", "unknown")
        raise RuntimeError(f"Query {exec_id} {state}: {reason}")

    stats     = status_resp["QueryExecution"]["Statistics"]
    engine_ms = stats.get("EngineExecutionTimeInMillis", elapsed_ms)
    bytes_sc  = stats.get("DataScannedInBytes", 0)

    # Get row count from results
    results = ath.get_query_results(QueryExecutionId=exec_id, MaxResults=1)
    # ResultSet.Rows includes header row; subtract 1
    rows = len(results["ResultSet"]["Rows"]) - 1

    return {
        "execution_id":   exec_id,
        "status":         state,
        "wall_clock_ms":  elapsed_ms,
        "engine_ms":      engine_ms,    # Athena's own engine time (more reproducible)
        "bytes_scanned":  bytes_sc,
        "rows_returned":  rows,
    }


# ── Benchmark runner ──────────────────────────────────────────────────────────
def run_benchmark(table_name: str, tag: str, queries: list[dict]) -> list[dict]:
    """
    Run all queries BENCHMARK_RUNS times against table_name.
    Returns list of result dicts.
    """
    full_table = f"{GLUE_DATABASE}.{table_name}"
    results = []

    print(f"\n{'='*60}")
    print(f"Benchmarking: {full_table}  ({BENCHMARK_RUNS} runs × {len(queries)} queries)")
    print(f"{'='*60}")

    for run in range(1, BENCHMARK_RUNS + 1):
        print(f"\n  Run {run}/{BENCHMARK_RUNS}")
        for q in queries:
            # Substitute table placeholder
            sql = q["sql"].replace("{TABLE}", full_table)
            try:
                r = run_query(sql)
                row = {
                    "tag":          tag,
                    "table":        table_name,
                    "run":          run,
                    "query_id":     q["id"],
                    "query_label":  q["label"],
                    "engine_ms":    r["engine_ms"],
                    "bytes_scanned": r["bytes_scanned"],
                    "rows_returned": r["rows_returned"],
                    "status":       r["status"],
                    "execution_id": r["execution_id"],
                }
                results.append(row)
                mb = r["bytes_scanned"] / 1024 / 1024
                print(f"    {q['id']:5s}  {r['engine_ms']:7,d} ms  {mb:8.1f} MB  "
                      f"{r['rows_returned']:6d} rows")
            except Exception as e:
                print(f"    {q['id']:5s}  ERROR: {e}")
                results.append({
                    "tag": tag, "table": table_name, "run": run,
                    "query_id": q["id"], "query_label": q["label"],
                    "engine_ms": None, "bytes_scanned": None,
                    "rows_returned": None, "status": "ERROR",
                    "execution_id": None,
                })

    return results


def save_results(results: list[dict], filename: str):
    os.makedirs(LOCAL_RESULTS_DIR, exist_ok=True)
    path = os.path.join(LOCAL_RESULTS_DIR, filename)
    if results:
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            writer.writeheader()
            writer.writerows(results)
        print(f"\n[OK] Results saved: {path}  ({len(results)} rows)")
    return path


def print_summary(results: list[dict], tag: str):
    import statistics
    rows = [r for r in results if r["status"] == "SUCCEEDED" and r["engine_ms"]]
    if not rows:
        print("No successful results.")
        return
    latencies = [r["engine_ms"] for r in rows]
    bytes_all = [r["bytes_scanned"] for r in rows]
    print(f"\n  Summary [{tag}]")
    print(f"    Successful queries : {len(rows)}")
    print(f"    Mean latency       : {statistics.mean(latencies):,.0f} ms")
    print(f"    Median latency     : {statistics.median(latencies):,.0f} ms")
    print(f"    P95 latency        : {sorted(latencies)[int(len(latencies)*0.95)]:,.0f} ms")
    print(f"    Mean bytes scanned : {statistics.mean(bytes_all)/1024/1024:.1f} MB")
    print(f"    Total bytes scanned: {sum(bytes_all)/1024/1024:.1f} MB")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"

    sql_file = os.path.join(LOCAL_SQL_DIR, "benchmark_queries.sql")
    queries  = load_queries(sql_file)
    print(f"Loaded {len(queries)} queries from {sql_file}")

    all_results = []

    if mode in ("baseline", "both"):
        res = run_benchmark(GLUE_TABLE_BASELINE, "baseline", queries)
        all_results.extend(res)
        save_results(res, "baseline.csv")
        print_summary(res, "baseline")

    if mode in ("optimized", "both"):
        res = run_benchmark(GLUE_TABLE_OPTIMIZED, "optimized", queries)
        all_results.extend(res)
        save_results(res, "optimized.csv")
        print_summary(res, "optimized")

    if mode == "both":
        save_results(all_results, "all_results.csv")

    print("\nBenchmark complete. Next: run 04_analyze_queries.py")
