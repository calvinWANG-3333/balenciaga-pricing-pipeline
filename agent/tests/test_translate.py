"""The evaluation set, offline: every question must be understood (or refused) as specified."""

import pytest

from agent import guardrails
from agent.evaluation import load_cases, score_case
from agent.intent import Refusal
from agent.translate import RuleTranslator, parse_period
from agent.vocabulary import product_aliases

CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=[c["question"][:60] for c in CASES])
def test_eval_case(case, catalogue, vocab):
    result = RuleTranslator(catalogue, vocab).translate(case["question"])
    if not isinstance(result, Refusal):
        result = guardrails.check(result, catalogue, vocab) or result
    assert score_case(case, result) == []


def test_hero_aliases_are_unambiguous():
    aliases = product_aliases(["Le City Bag Medium (black)", "Le City Card Holder (black)"])
    assert "le city" not in aliases                       # would be ambiguous
    assert aliases["le city bag"] == "Le City Bag Medium (black)"
    assert aliases["le city card"] == "Le City Card Holder (black)"


def test_periods(vocab):
    weeks = vocab.periods["hero_prices"]
    assert parse_period(" in september ", weeks)[:2] == (weeks[8].replace(day=1), weeks[8].replace(day=30))
    assert parse_period(" latest ", weeks)[0] == weeks[-1]
    start, end, _ = parse_period(" q3 ", weeks)
    assert (start.month, end.month) == (7, 9)
    assert parse_period(" you may ask ", weeks) == (None, None, None)    # "may" the verb


def test_point_in_time_metric_uses_latest_delivery_of_the_month(catalogue, vocab):
    intent = RuleTranslator(catalogue, vocab).translate("Price of the Le City bag in the USA in August")
    assert intent.time_start == intent.time_end == vocab.periods["hero_prices"][7]   # 2026-08-25
    assert any("point-in-time" in n for n in intent.notes)
