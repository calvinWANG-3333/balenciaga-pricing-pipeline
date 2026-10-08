"""Turn measured values into verdicts. Pure functions, no warehouse: everything here is unit-tested.

check level     observed value + rules            -> pass | warn | fail | skip
delivery level  all check results of a delivery   -> PASS | WARN | BLOCK
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

from .catalog import Check


@dataclass(frozen=True)
class Result:
    check_id: str
    dimension: str
    severity: str
    scope: str
    as_of_date: date
    subject: str
    observed: float | None
    status: str                 # pass | warn | fail | skip
    warn_rule: str
    fail_rule: str
    message: str


def _fmt(x: float | None) -> str:
    if x is None:
        return "n/a"
    if abs(x) < 1 and x != 0:
        return f"{x:.2%}"
    return f"{x:g}"


def describe_rules(rules: dict[str, Any]) -> tuple[str, str]:
    """Human-readable warn / fail rule, stored with every result (the rule may change later)."""
    def side(prefix: str) -> str:
        parts = []
        if f"{prefix}_below" in rules:
            parts.append(f"< {rules[f'{prefix}_below']}")
        if f"{prefix}_above" in rules:
            parts.append(f"> {rules[f'{prefix}_above']}")
        return " or ".join(parts)

    warn = side("warn")
    if "anomaly" in rules:
        a = rules["anomaly"]
        anomaly = f"> mean + {a.get('z', 3)} sd of last {a.get('window', 6)} deliveries"
        warn = f"{warn} or {anomaly}" if warn else anomaly
    return warn, side("fail")


def anomaly_flag(value: float, history: list[float], window: int = 6, min_history: int = 3,
                 z: float = 3.0, min_value: float = 0.0) -> tuple[bool, str]:
    """Is `value` unusually HIGH compared with its own recent history?

    Mean + z standard deviations of the last `window` values. A floor on the standard deviation stops
    a perfectly flat history (sd = 0) from turning any tiny move into an alarm; `min_value` ignores
    anomalies too small to matter.
    """
    recent = [h for h in history if h is not None][-window:]
    if len(recent) < min_history:
        return False, f"not enough history ({len(recent)} < {min_history})"
    mean = statistics.fmean(recent)
    sd = max(statistics.pstdev(recent), 0.005)
    threshold = mean + z * sd
    if value > threshold and value > min_value:
        return True, f"{_fmt(value)} vs usual {_fmt(mean)} (threshold {_fmt(threshold)})"
    return False, f"usual {_fmt(mean)}"


def evaluate(check: Check, scope: str, as_of_date: date, subject: str, observed: float | None,
             history: Iterable[float | None] = ()) -> Result:
    rules = check.rules_for(scope)
    warn_rule, fail_rule = describe_rules(rules)

    def result(status: str, message: str) -> Result:
        return Result(check.id, check.dimension, check.severity, scope, as_of_date, subject,
                      observed, status, warn_rule, fail_rule, message)

    if observed is None or (isinstance(observed, float) and math.isnan(observed)):
        return result("skip", "no value (nothing to compare with, e.g. first delivery)")

    label = f"{subject}: {_fmt(observed)}"
    if ("fail_above" in rules and observed > rules["fail_above"]) or \
       ("fail_below" in rules and observed < rules["fail_below"]):
        return result("fail", f"{label} (fail {fail_rule})")
    if ("warn_above" in rules and observed > rules["warn_above"]) or \
       ("warn_below" in rules and observed < rules["warn_below"]):
        return result("warn", f"{label} (warn {warn_rule})")
    if "anomaly" in rules:
        flagged, why = anomaly_flag(observed, list(history), **rules["anomaly"])
        if flagged:
            return result("warn", f"{subject}: anomaly - {why}")
    return result("pass", label)


def decide(results: Iterable[Result]) -> str:
    """A delivery is BLOCKed by any failure of a blocking check, WARNed by anything not clean."""
    results = list(results)
    if any(r.status == "fail" and r.severity == "block" for r in results):
        return "BLOCK"
    if any(r.status in {"warn", "fail"} for r in results):
        return "WARN"
    return "PASS"
