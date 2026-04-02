"""
Apollo AI Coach — LLM Evaluation Framework
Runs a benchmark suite and produces a markdown + JSON report.
"""

import os
import sys
import json
import time
import requests
from datetime import datetime

API_URL = "http://localhost:8000"

# ── Benchmark Suite ──────────────────────────────────────────────────────────
# expected_cols: ANY of these column name substrings must appear (case-insensitive)
# This is flexible — "sleep" matches "avg_sleep_score", "sleep_score" etc.

BENCHMARK = [
    {
        "id": "B01",
        "question": "Show average sprint distance by position",
        "expected_col_hints": ["position", "sprint"],
        "expected_rows": 3,
        "min_rows": None,
        "kpi_should_match": "avg_sprint_distance",
        "tags": ["aggregation", "groupby", "kpi-retrieval"],
    },
    {
        "id": "B02",
        "question": "Who had the highest total distance?",
        "expected_col_hints": ["name", "distance"],
        "expected_rows": None,
        "min_rows": 1,
        "kpi_should_match": "workload",
        "tags": ["ranking", "kpi-retrieval"],
    },
    {
        "id": "B03",
        "question": "Show fatigue scores for all athletes",
        "expected_col_hints": ["name", "fatigue"],
        "expected_rows": None,
        "min_rows": 6,
        "kpi_should_match": "fatigue_trend",
        "tags": ["wellness", "kpi-retrieval"],
    },
    {
        "id": "B04",
        "question": "What is the average sleep score per athlete?",
        "expected_col_hints": ["name", "sleep"],
        "expected_rows": None,
        "min_rows": 6,
        "kpi_should_match": "sleep_quality_avg",
        "tags": ["wellness", "aggregation"],
    },
    {
        "id": "B05",
        "question": "Compare match vs training total distance",
        "expected_col_hints": ["session_type", "distance"],
        "expected_rows": 2,
        "min_rows": None,
        "kpi_should_match": "match_vs_training",
        "tags": ["comparison", "session-type"],
    },
    {
        "id": "B06",
        "question": "Which athletes are on team A?",
        "expected_col_hints": ["name", "team"],
        "expected_rows": None,
        "min_rows": 1,
        "kpi_should_match": None,
        "tags": ["filter", "simple"],
    },
    {
        "id": "B07",
        "question": "Show total high intensity efforts per athlete",
        "expected_col_hints": ["name", "hie"],
        "expected_rows": None,
        "min_rows": 6,
        "kpi_should_match": "total_high_intensity",
        "tags": ["aggregation", "kpi-retrieval"],
    },
    {
        "id": "B08",
        "question": "What is the average distance per minute across all sessions?",
        "expected_col_hints": ["distance", "minute"],
        "expected_rows": None,
        "min_rows": 1,
        "kpi_should_match": "distance_per_minute",
        "tags": ["derived-metric", "kpi-retrieval"],
    },
    {
        "id": "B09",
        "question": "Show all athletes and their positions",
        "expected_col_hints": ["name", "position"],
        "expected_rows": 15,
        "min_rows": None,
        "kpi_should_match": None,
        "tags": ["simple", "no-join"],
    },
    {
        "id": "B10",
        "question": "Which session type has more high intensity efforts on average?",
        "expected_col_hints": ["session_type", "intensity"],
        "expected_rows": 2,
        "min_rows": None,
        "kpi_should_match": "total_high_intensity",
        "tags": ["comparison", "aggregation"],
    },
    {
        "id": "B11",
        "question": "Show sprint distance for forwards only",
        "expected_col_hints": ["name", "sprint"],
        "expected_rows": None,
        "min_rows": 1,
        "kpi_should_match": "avg_sprint_distance",
        "tags": ["filter", "position"],
    },
    {
        "id": "B12",
        "question": "Who slept the worst on average?",
        "expected_col_hints": ["name", "sleep"],
        "expected_rows": None,
        "min_rows": 1,
        "kpi_should_match": "sleep_quality_avg",
        "tags": ["ranking", "wellness"],
    },
    {
        "id": "B13",
        "question": "List all training sessions with their duration",
        "expected_col_hints": ["session", "duration"],
        "expected_rows": None,
        "min_rows": 1,
        "kpi_should_match": None,
        "tags": ["filter", "simple"],
    },
    {
        "id": "B14",
        "question": "What is the total workload per team?",
        "expected_col_hints": ["team", "workload"],
        "expected_rows": 2,
        "min_rows": None,
        "kpi_should_match": "workload",
        "tags": ["aggregation", "groupby", "kpi-retrieval"],
    },
    {
        "id": "B15",
        "question": "Show the high intensity rate per athlete",
        "expected_col_hints": ["name", "hie"],
        "expected_rows": None,
        "min_rows": 1,
        "kpi_should_match": "high_intensity_rate",
        "tags": ["derived-metric", "kpi-retrieval"],
    },
]


# ── Evaluation Logic ──────────────────────────────────────────────────────────

def check_columns(result_cols, hints):
    """
    Flexible column check — each hint must appear as a substring in at least
    one result column (case-insensitive). This handles avg_sleep_score matching 'sleep'.
    """
    if not hints:
        return True, []
    result_lower = [c.lower() for c in result_cols]
    missing = []
    for hint in hints:
        if not any(hint.lower() in col for col in result_lower):
            missing.append(hint)
    return len(missing) == 0, missing


def check_row_count(row_count, expected_rows, min_rows):
    if expected_rows is not None:
        return row_count == expected_rows, f"expected {expected_rows}, got {row_count}"
    if min_rows is not None:
        return row_count >= min_rows, f"expected >={min_rows}, got {row_count}"
    return True, ""


def check_kpi_retrieval(kpis_retrieved, kpi_should_match):
    if kpi_should_match is None:
        return True, None
    retrieved_ids = [k.get("kpi_id", "") for k in kpis_retrieved]
    found = kpi_should_match in retrieved_ids
    return found, retrieved_ids


def warmup(n=2):
    """Send a couple of warm-up queries so ChromaDB is ready before benchmarking."""
    print("  Warming up backend...")
    for _ in range(n):
        try:
            requests.post(f"{API_URL}/query",
                json={"question": "Show all athletes"},
                timeout=60)
        except Exception:
            pass
    print("  Warm-up complete.\n")


def run_benchmark(skip_warmup=False):
    print(f"\n{'='*60}")
    print(f"  Apollo AI Coach — Evaluation Run")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # Check backend is running
    try:
        r = requests.get(f"{API_URL}/health", timeout=5)
        r.raise_for_status()
        print(f"✓ Backend healthy at {API_URL}\n")
    except Exception as e:
        print(f"✗ Backend not reachable: {e}")
        print("  Make sure uvicorn is running on port 8000")
        sys.exit(1)

    if not skip_warmup:
        warmup()

    results = []
    passed = 0
    failed = 0

    for test in BENCHMARK:
        print(f"[{test['id']}] {test['question'][:55]}...")
        start = time.time()

        try:
            resp = requests.post(
                f"{API_URL}/query",
                json={"question": test["question"]},
                timeout=120
            )
            data = resp.json()
            latency = round(time.time() - start, 2)

            has_error = bool(data.get("error"))
            columns = data.get("columns", [])
            rows = data.get("rows", [])
            row_count = data.get("row_count", 0)
            kpis = data.get("kpis_retrieved", [])
            verification = data.get("verification", {})
            verdict = verification.get("verdict", "unknown") if verification else "unknown"
            sql = data.get("sql", "")

            col_ok, missing_cols = check_columns(columns, test["expected_col_hints"])
            row_ok, row_msg = check_row_count(row_count, test["expected_rows"], test["min_rows"])
            kpi_ok, retrieved_ids = check_kpi_retrieval(kpis, test["kpi_should_match"])

            overall_pass = not has_error and col_ok and row_ok

            status = "PASS" if overall_pass else "FAIL"
            if overall_pass:
                passed += 1
                print(f"  ✓ {status} | {latency}s | {row_count} rows | verdict={verdict}")
            else:
                failed += 1
                reasons = []
                if has_error: reasons.append(f"error: {str(data.get('error',''))[:80]}")
                if not col_ok: reasons.append(f"missing col hints: {missing_cols}")
                if not row_ok: reasons.append(f"row count: {row_msg}")
                print(f"  ✗ {status} | {latency}s | {' | '.join(reasons)}")

            if test["kpi_should_match"]:
                sym = "✓" if kpi_ok else "✗"
                print(f"  {sym} KPI retrieval: expected '{test['kpi_should_match']}' | got {retrieved_ids}")

            results.append({
                "id": test["id"],
                "question": test["question"],
                "tags": test["tags"],
                "status": status,
                "latency_s": latency,
                "row_count": row_count,
                "has_error": has_error,
                "error_msg": data.get("error", ""),
                "columns": columns,
                "columns_ok": col_ok,
                "missing_col_hints": missing_cols,
                "row_count_ok": row_ok,
                "row_count_msg": row_msg,
                "kpi_match": kpi_ok,
                "kpi_expected": test["kpi_should_match"],
                "kpi_retrieved": retrieved_ids,
                "verification_verdict": verdict,
                "sql_generated": sql,
            })

        except Exception as e:
            latency = round(time.time() - start, 2)
            print(f"  ✗ EXCEPTION: {e}")
            failed += 1
            results.append({
                "id": test["id"],
                "question": test["question"],
                "tags": test["tags"],
                "status": "ERROR",
                "latency_s": latency,
                "error_msg": str(e),
                "columns": [],
                "kpi_match": False,
                "kpi_expected": test["kpi_should_match"],
                "kpi_retrieved": [],
            })

        print()

    return results, passed, failed


def generate_report(results, passed, failed):
    total = passed + failed
    pass_rate = round((passed / total) * 100, 1) if total > 0 else 0

    latencies = [r["latency_s"] for r in results if "latency_s" in r]
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0
    max_latency = max(latencies) if latencies else 0

    verdicts = [r.get("verification_verdict", "unknown") for r in results if r.get("verification_verdict")]
    verdict_dist = {v: verdicts.count(v) for v in set(verdicts)}

    kpi_tests = [r for r in results if r.get("kpi_expected")]
    kpi_hits = sum(1 for r in kpi_tests if r.get("kpi_match"))
    kpi_precision = round((kpi_hits / len(kpi_tests)) * 100, 1) if kpi_tests else 0

    tag_stats = {}
    for r in results:
        for tag in r.get("tags", []):
            if tag not in tag_stats:
                tag_stats[tag] = {"pass": 0, "fail": 0}
            if r["status"] == "PASS":
                tag_stats[tag]["pass"] += 1
            else:
                tag_stats[tag]["fail"] += 1

    errors = [r for r in results if r["status"] != "PASS"]

    print(f"\n{'='*60}")
    print(f"  EVALUATION SUMMARY")
    print(f"{'='*60}")
    print(f"  Overall pass rate    : {passed}/{total} ({pass_rate}%)")
    print(f"  Avg latency          : {avg_latency}s")
    print(f"  Max latency          : {max_latency}s")
    print(f"  KPI retrieval P@3    : {kpi_hits}/{len(kpi_tests)} ({kpi_precision}%)")
    print(f"  Verification verdicts: {verdict_dist}")
    print()

    print("  Results by tag:")
    for tag, stats in sorted(tag_stats.items()):
        total_tag = stats["pass"] + stats["fail"]
        bar = "█" * stats["pass"] + "░" * stats["fail"]
        print(f"    {tag:<22} {stats['pass']}/{total_tag}  {bar}")

    if errors:
        print(f"\n  Failed tests:")
        for r in errors:
            print(f"    [{r['id']}] {r['question'][:50]}")
            if r.get("error_msg"):
                print(f"          → {str(r['error_msg'])[:80]}")

    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total": total, "passed": passed, "failed": failed,
            "pass_rate_pct": pass_rate,
            "avg_latency_s": avg_latency,
            "max_latency_s": max_latency,
            "kpi_retrieval_precision_pct": kpi_precision,
            "verification_verdicts": verdict_dist,
            "tag_breakdown": tag_stats,
        },
        "results": results,
    }

    with open("eval_report.json", "w") as f:
        json.dump(report, f, indent=2)

    # Markdown report
    md = [
        "# Apollo AI Coach — Evaluation Report",
        f"**Run:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Summary",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Pass rate | {passed}/{total} ({pass_rate}%) |",
        f"| Avg latency | {avg_latency}s |",
        f"| Max latency | {max_latency}s |",
        f"| KPI retrieval P@3 | {kpi_precision}% |",
        f"| Verification verdicts | {verdict_dist} |",
        "",
        "## Results",
        "| ID | Question | Status | Rows | Latency | Verdict | KPI ✓ |",
        "|----|----------|--------|------|---------|---------|-------|",
    ]
    for r in results:
        q = r["question"][:38] + "..." if len(r["question"]) > 38 else r["question"]
        kpi_sym = "✓" if r.get("kpi_match") else ("—" if not r.get("kpi_expected") else "✗")
        md.append(
            f"| {r['id']} | {q} | {r['status']} | "
            f"{r.get('row_count','?')} | {r.get('latency_s','?')}s | "
            f"{r.get('verification_verdict','?')} | {kpi_sym} |"
        )

    with open("eval_report.md", "w") as f:
        f.write("\n".join(md))

    print(f"\n  Reports saved: eval_report.json  eval_report.md")
    print(f"\n{'='*60}\n")
    return report


if __name__ == "__main__":
    skip_warmup = "--no-warmup" in sys.argv
    results, passed, failed = run_benchmark(skip_warmup=skip_warmup)
    generate_report(results, passed, failed)