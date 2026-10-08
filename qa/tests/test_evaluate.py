"""Unit tests of the verdict logic - no warehouse needed (pytest qa/tests)."""

from datetime import date

import pytest

from qa.catalog import Check
from qa.evaluate import anomaly_flag, decide, evaluate

D = date(2026, 9, 15)


def make_check(rules, severity="block"):
    return Check(id="c", dimension="plausibility", severity=severity, scopes=("micro",),
                 datasets=("marts",), description="", rules={"micro": rules}, sql="")


@pytest.mark.parametrize("observed, expected", [
    (0.00, "pass"),
    (0.02, "warn"),     # above warn_above 0.01
    (0.26, "fail"),     # above fail_above 0.05: the 2026-09-15 incident
    (None, "skip"),
])
def test_threshold_statuses(observed, expected):
    check = make_check({"warn_above": 0.01, "fail_above": 0.05})
    assert evaluate(check, "micro", D, "FRA", observed).status == expected


def test_below_rules():
    check = make_check({"warn_below": -0.05, "fail_below": -0.20})
    assert evaluate(check, "micro", D, "KOR", -0.55).status == "fail"     # half the catalogue gone
    assert evaluate(check, "micro", D, "KOR", -0.10).status == "warn"
    assert evaluate(check, "micro", D, "KOR", 0.01).status == "pass"


def test_anomaly_needs_history():
    flagged, why = anomaly_flag(0.25, [0.001, 0.002], min_history=3)
    assert not flagged and "not enough history" in why


def test_anomaly_detects_a_price_campaign():
    history = [0.001, 0.002, 0.0015, 0.003, 0.002]
    assert anomaly_flag(0.2567, history, z=4, min_value=0.02)[0]
    assert not anomaly_flag(0.004, history, z=4, min_value=0.02)[0]      # tiny move: under min_value


def test_flat_history_does_not_alarm_on_noise():
    # sd = 0 would make any change an anomaly; the sd floor prevents that
    assert not anomaly_flag(0.003, [0.0, 0.0, 0.0, 0.0], z=3, min_value=0.0)[0]


def test_warn_check_never_blocks():
    check = make_check({"warn_above": 0}, severity="warn")
    results = [evaluate(check, "micro", D, "all", 7)]
    assert results[0].status == "warn"
    assert decide(results) == "WARN"


def test_decision_ladder():
    block = make_check({"fail_above": 0.05})
    warn = make_check({"warn_above": 0}, severity="warn")
    ok = evaluate(block, "micro", D, "FRA", 0.0)
    w = evaluate(warn, "micro", D, "all", 3)
    f = evaluate(block, "micro", D, "USA", 0.26)
    assert decide([ok]) == "PASS"
    assert decide([ok, w]) == "WARN"
    assert decide([ok, w, f]) == "BLOCK"
