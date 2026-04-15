#!/usr/bin/env python3
"""
Comparison framework: Hermes Agent vs n8n log monitoring workflows.

Runs both against the same Loki time window and saves outputs side-by-side.
Over time, track which catches more real issues vs false positives.

Usage:
    python3 compare.py [--hours 4] [--output ./results]
    python3 compare.py --list      # Show all past comparison runs
"""

import argparse
import json
import subprocess
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

LOKI_URL = "http://localhost:3100"  # Mac Mini host (not container)
HERMES_OUTPUT_DIR = Path.home() / "hermes-agent/data/cron/output"
RESULTS_DIR = Path.home() / "hermes-agent/comparison-results"


def loki_query(logql: str, hours: int = 4, limit: int = 200) -> dict:
    """Query Loki HTTP API directly."""
    end_ns = int(time.time() * 1e9)
    start_ns = int((time.time() - hours * 3600) * 1e9)

    params = urllib.parse.urlencode({
        "query": logql,
        "start": str(start_ns),
        "end": str(end_ns),
        "limit": str(limit),
    })
    url = f"{LOKI_URL}/loki/api/v1/query_range?{params}"

    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def get_n8n_baseline(hours: int) -> dict:
    """
    Replicate the n8n Container Error Monitor query.
    n8n queries Loki for errors, then passes to Ollama for analysis.
    Here we just capture the raw Loki results as the baseline.
    """
    queries = {
        "container_errors": '{job="docker"} |= "error" != "loki" != "promtail" != "n8n"',
        "container_fatal": '{job="docker"} |= "fatal"',
        "device_offline": '{container="mqtt-logger-deepthought"} |= "Offline"',
        "device_errors": '{container="mqtt-logger-deepthought"} |= "error"',
    }
    results = {}
    for name, query in queries.items():
        data = loki_query(query, hours=hours)
        result_count = 0
        if "data" in data and "result" in data["data"]:
            for stream in data["data"]["result"]:
                result_count += len(stream.get("values", []))
        results[name] = {
            "query": query,
            "log_lines": result_count,
            "raw": data,
        }
        print(f"  [{name}] {result_count} log lines")
    return results


def get_latest_hermes_output(job_id: str) -> str | None:
    """Find the most recent Hermes cron output for a given job."""
    job_dir = HERMES_OUTPUT_DIR / job_id
    if not job_dir.exists():
        return None
    reports = sorted(job_dir.glob("*.md"), reverse=True)
    if not reports:
        return None
    return reports[0].read_text()


def run_comparison(hours: int, output_dir: Path) -> Path:
    """Run a full comparison and save results."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_dir / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Hermes vs n8n Comparison Run ===")
    print(f"Time window: last {hours}h")
    print(f"Output: {run_dir}\n")

    # 1. Get n8n baseline (raw Loki queries)
    print("1. Querying Loki (n8n baseline)...")
    n8n_data = get_n8n_baseline(hours)
    n8n_file = run_dir / "n8n_raw_loki.json"
    n8n_file.write_text(json.dumps(n8n_data, indent=2))
    print(f"   Saved: {n8n_file}")

    # 2. Get latest Hermes output
    print("\n2. Reading latest Hermes output...")
    hermes_results = {}
    for job_id in ["container-error-monitor", "device-error-monitor"]:
        report = get_latest_hermes_output(job_id)
        if report:
            hermes_results[job_id] = report
            (run_dir / f"hermes_{job_id}.md").write_text(report)
            print(f"   Found: {job_id}")
        else:
            hermes_results[job_id] = "NO OUTPUT YET — cron job hasn't run"
            print(f"   Missing: {job_id} (cron hasn't run yet)")

    # 3. Write comparison summary
    summary = f"""# Comparison Run: {timestamp}
Window: last {hours}h

## Raw Loki Data (n8n baseline)
"""
    for name, result in n8n_data.items():
        summary += f"\n### {name}\n- Query: `{result['query']}`\n- Log lines: {result['log_lines']}\n"

    summary += "\n## Hermes Analysis Output\n"
    for job_id, report in hermes_results.items():
        summary += f"\n### {job_id}\n```\n{report[:2000]}\n```\n"

    summary += f"""
## Scoring (fill in manually after review)

| Metric | n8n | Hermes |
|--------|-----|--------|
| Real issues caught | | |
| False positives | | |
| False negatives | | |
| Report clarity (1-5) | | |
| Notes | | |
"""
    summary_file = run_dir / "COMPARISON.md"
    summary_file.write_text(summary)
    print(f"\n3. Summary saved: {summary_file}")
    print(f"\nDone. Review {run_dir}/COMPARISON.md")
    return run_dir


def list_runs(output_dir: Path):
    """List all past comparison runs."""
    runs = sorted(output_dir.glob("*/COMPARISON.md"), reverse=True)
    if not runs:
        print("No comparison runs yet.")
        return
    print(f"Past runs ({len(runs)}):")
    for r in runs:
        print(f"  {r.parent.name}")


def main():
    parser = argparse.ArgumentParser(description="Hermes vs n8n comparison framework")
    parser.add_argument("--hours", type=int, default=4, help="Time window in hours (default: 4)")
    parser.add_argument("--output", type=Path, default=RESULTS_DIR, help="Output directory")
    parser.add_argument("--list", action="store_true", help="List past runs")
    args = parser.parse_args()

    if args.list:
        list_runs(args.output)
    else:
        run_comparison(args.hours, args.output)


if __name__ == "__main__":
    main()
