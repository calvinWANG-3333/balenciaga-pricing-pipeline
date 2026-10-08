"""Human-readable output of a gate run: a console summary and a markdown report (PR comment, triage)."""

from __future__ import annotations

from collections import Counter

from .catalog import Delivery
from .evaluate import Result

ICON = {"PASS": "PASS ", "WARN": "WARN ", "BLOCK": "BLOCK"}


def _not_passing(results: list[Result]) -> list[Result]:
    order = {"fail": 0, "warn": 1}
    return sorted((r for r in results if r.status in order),
                  key=lambda r: (order[r.status], r.severity != "block", r.check_id, r.subject))


def print_report(dataset: str, run_id: str, verdicts: dict[Delivery, list[Result]],
                 decisions: dict[Delivery, str], verbose: bool = False) -> None:
    print(f"Delivery gate - dataset: {dataset} - run {run_id}")
    print("=" * 96)
    for delivery in sorted(verdicts, key=lambda d: (d.scope, d.as_of_date)):
        results = verdicts[delivery]
        counts = Counter(r.status for r in results)
        print(f"{ICON[decisions[delivery]]}  {delivery.scope:<5} {delivery.as_of_date}   "
              f"pass {counts['pass']:>3}  warn {counts['warn']:>2}  fail {counts['fail']:>2}  skip {counts['skip']:>2}")
        shown = results if verbose else _not_passing(results)
        for r in shown:
            tag = f"{r.status.upper()}{'*' if r.status == 'fail' and r.severity == 'block' else ''}"
            print(f"         {tag:<6} {r.check_id:<30} {r.message}")
    print("-" * 96)
    print("FAIL* = failure of a blocking check (stops the release)")


def markdown_report(dataset: str, run_id: str, verdicts: dict[Delivery, list[Result]],
                    decisions: dict[Delivery, str]) -> str:
    lines = [f"# Delivery gate report", "", f"- dataset: `{dataset}`", f"- run: `{run_id}`", "",
             "| Scope | Delivery | Decision | Pass | Warn | Fail |", "|---|---|---|---:|---:|---:|"]
    for delivery in sorted(verdicts, key=lambda d: (d.scope, d.as_of_date)):
        c = Counter(r.status for r in verdicts[delivery])
        lines.append(f"| {delivery.scope} | {delivery.as_of_date} | **{decisions[delivery]}** | "
                     f"{c['pass']} | {c['warn']} | {c['fail']} |")
    for delivery in sorted(verdicts, key=lambda d: (d.scope, d.as_of_date)):
        issues = _not_passing(verdicts[delivery])
        if not issues:
            continue
        lines += ["", f"## {delivery.scope} {delivery.as_of_date} - {decisions[delivery]}", "",
                  "| Status | Check | Dimension | Detail |", "|---|---|---|---|"]
        for r in issues:
            blocking = " (blocking)" if r.status == "fail" and r.severity == "block" else ""
            lines.append(f"| {r.status}{blocking} | `{r.check_id}` | {r.dimension} | {r.message} |")
    return "\n".join(lines) + "\n"
