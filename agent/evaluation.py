"""Evaluate the translator on a fixed question set: does it pick the right metric, filters and grouping,
and does it REFUSE what it must refuse? An agent is only trustworthy if this is measured.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .intent import Refusal

EVAL_PATH = Path(__file__).with_name("evals") / "questions.yml"


def load_cases(path: Path = EVAL_PATH) -> list[dict]:
    return yaml.safe_load(path.read_text())["cases"]


def score_case(case: dict, result) -> list[str]:
    """Return the list of mismatches (empty = pass)."""
    expect = case["expect"]
    if expect.get("refuse"):
        return [] if isinstance(result, Refusal) else [f"should refuse, got metric={getattr(result, 'metric', None)}"]
    if isinstance(result, Refusal):
        return [f"refused: {result.reason}"]
    problems = []
    if result.metric != expect["metric"]:
        problems.append(f"metric {result.metric} != {expect['metric']}")
    for dim, values in (expect.get("filters") or {}).items():
        if sorted(result.filters.get(dim, [])) != sorted(values):
            problems.append(f"filter {dim}={result.filters.get(dim)} != {values}")
    if "group_by" in expect and sorted(result.group_by) != sorted(expect["group_by"]):
        problems.append(f"group_by {result.group_by} != {expect['group_by']}")
    if "time_start" in expect and str(result.time_start) != str(expect["time_start"]):
        problems.append(f"time_start {result.time_start} != {expect['time_start']}")
    if "time_end" in expect and str(result.time_end) != str(expect["time_end"]):
        problems.append(f"time_end {result.time_end} != {expect['time_end']}")
    if "order" in expect and result.order != expect["order"]:
        problems.append(f"order {result.order} != {expect['order']}")
    return problems


def run_eval(agent, verbose: bool = False) -> int:
    from . import guardrails
    cases = load_cases()
    passed = 0
    for case in cases:
        result = agent.translator.translate(case["question"])
        if not isinstance(result, Refusal):          # guardrails are part of the agent's behaviour
            refusal = guardrails.check(result, agent.cat, agent.vocab)
            result = refusal or result
        problems = score_case(case, result)
        passed += not problems
        if problems or verbose:
            print(f"{'PASS' if not problems else 'FAIL'}  {case['question']}")
            for p in problems:
                print(f"        {p}")
    print(f"\n{passed}/{len(cases)} questions handled as expected ({agent.translator.name} translator).")
    return 0 if passed == len(cases) else 1
