"""The baseline rule: a delivery is compared with the last ACCEPTED delivery, never a blocked one."""

from datetime import date

from qa import catalog as cat
from qa.gate import judge

W = [date(2026, 9, d) for d in (1, 8, 15, 22)]


def catalogue_with_reversion_check():
    check = cat.Check(id="price_reversion_share", dimension="plausibility", severity="block",
                      scopes=("micro",), datasets=("legacy_replay",), description="",
                      rules={"micro": {"fail_above": 0.05}}, sql="")
    ds = cat.Dataset("legacy_replay", False, {}, "")
    return cat.Catalogue(datasets={"legacy_replay": ds}, checks=[check]), ds


def test_delivery_after_a_blocked_one_is_compared_with_the_last_accepted_one():
    catalogue, ds = catalogue_with_reversion_check()
    calendar = [cat.Delivery("micro", d, W[i - 1] if i else None, W[i - 2] if i > 1 else None)
                for i, d in enumerate(W)]
    # calendar baseline: 09-15 reverts prices (incident), 09-22 "reverts back" because 09-15 was wrong
    measured = {"price_reversion_share": [
        {"scope": "micro", "as_of_date": W[0], "subject": "FRA", "observed": None},
        {"scope": "micro", "as_of_date": W[1], "subject": "FRA", "observed": None},
        {"scope": "micro", "as_of_date": W[2], "subject": "FRA", "observed": 0.26},
        {"scope": "micro", "as_of_date": W[3], "subject": "FRA", "observed": 0.26},
    ]}
    calls = []

    def remeasure(adjusted):
        calls.append(adjusted)
        # against the accepted baseline (09-08, 09-01) nothing reverted on 09-22
        return {"price_reversion_share": [
            {"scope": "micro", "as_of_date": adjusted.as_of_date, "subject": "FRA", "observed": 0.0}]}

    _, decisions = judge(catalogue, ds, calendar, calendar, set(), measured, remeasure)
    by_date = {d.as_of_date: x for d, x in decisions.items()}
    assert by_date[W[2]] == "BLOCK"
    assert by_date[W[3]] == "PASS"
    assert calls == [cat.Delivery("micro", W[3], W[1], W[0])]
