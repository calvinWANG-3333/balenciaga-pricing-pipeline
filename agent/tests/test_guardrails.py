"""Guardrails judge the Intent, whoever filled it: here, intents an LLM could plausibly produce."""

from datetime import date

from agent import guardrails
from agent.intent import Intent


def test_refuses_to_average_currencies(catalogue, vocab):
    intent = Intent(metric="category_median_price", filters={"macro_category": ["Bags"]})
    refusal = guardrails.check(intent, catalogue, vocab)
    assert refusal and "local currency" in refusal.reason


def test_accepts_one_market_or_per_market(catalogue, vocab):
    one = Intent(metric="category_median_price", filters={"market": ["FRA"]})
    per = Intent(metric="category_median_price", group_by=["market"])
    assert guardrails.check(one, catalogue, vocab) is None
    assert guardrails.check(per, catalogue, vocab) is None


def test_refuses_invented_values(catalogue, vocab):
    intent = Intent(metric="category_lfl_change", filters={"market": ["DEU"]})
    assert "not a known value" in guardrails.check(intent, catalogue, vocab).reason


def test_refuses_dimension_of_another_model(catalogue, vocab):
    intent = Intent(metric="hero_price", group_by=["macro_category"], filters={"market": ["USA"]})
    assert "cannot be broken down" in guardrails.check(intent, catalogue, vocab).reason


def test_refuses_unknown_and_hidden_metrics(catalogue, vocab):
    assert guardrails.check(Intent(metric="revenue"), catalogue, vocab)
    assert guardrails.check(Intent(metric="lfl_weighted_numerator"), catalogue, vocab)


def test_refuses_period_without_published_data(catalogue, vocab):
    intent = Intent(metric="price_change_count", time_start=date(2027, 1, 1), time_end=date(2027, 1, 31))
    assert "No published data" in guardrails.check(intent, catalogue, vocab).reason
