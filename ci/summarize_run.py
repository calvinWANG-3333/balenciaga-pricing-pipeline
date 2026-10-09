"""Turn dbt's run_results.json into a short markdown summary for the GitHub Actions job page.

Usage:  python ci/summarize_run.py dbt/target/run_results.json "Slim CI build" >> "$GITHUB_STEP_SUMMARY"

Shows the counts per status, then every node that did not pass, so a reviewer sees at a glance what a
pull request built and what broke, without opening the logs.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ICON = {"success": "PASS", "pass": "PASS", "warn": "WARN", "error": "ERROR", "fail": "FAIL", "skipped": "SKIP",
        "no-op": "NO-OP"}


def summarize(path: Path, title: str) -> str:
    if not path.exists():
        return f"### {title}\n\nNo run_results.json: dbt did not run.\n"
    data = json.loads(path.read_text())
    results = data.get("results", [])
    counts = Counter(ICON.get(r["status"], r["status"].upper()) for r in results)
    elapsed = data.get("elapsed_time", 0)
    lines = [f"### {title}", "",
             f"{len(results)} nodes in {elapsed:.0f}s - " +
             ", ".join(f"{label} {n}" for label, n in sorted(counts.items())), ""]
    bad = [r for r in results if r["status"] in ("error", "fail", "warn")]
    if bad:
        lines += ["| Status | Node | Message |", "|---|---|---|"]
        for r in bad:
            node = r["unique_id"].split(".", 2)[-1]
            msg = (r.get("message") or "").replace("\n", " ").replace("|", "/")[:160]
            lines.append(f"| {ICON.get(r['status'], r['status'])} | `{node}` | {msg} |")
    else:
        lines.append("Every node passed.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(summarize(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "dbt"))
