"""The SQL is a template over the semantic layer: same intent, same SQL, reading the published view."""

from datetime import date

from agent.compiler import compile_sql
from agent.intent import Intent
from agent.narrate import fmt_value


def test_simple_metric_sql(catalogue):
    intent = Intent(metric="category_lfl_change", group_by=["market"], filters={"macro_category": ["Bags"]},
                    time_start=date(2026, 9, 1), time_end=date(2026, 9, 1), order="desc")
    sql = compile_sql(intent, catalogue, "pub")
    assert "avg(lfl_mean_change) as category_lfl_change" in sql
    assert "from pub.pub_macro__category_monthly" in sql
    assert "macro_category in ('Bags')" in sql
    assert "order by category_lfl_change desc" in sql
    assert sql.rstrip().endswith("limit 500")


def test_ratio_metric_sql(catalogue):
    sql = compile_sql(Intent(metric="category_lfl_change_product_weighted"), catalogue, "pub")
    assert "sum(lfl_mean_change * lfl_n_products) / nullif(sum(case when lfl_mean_change" in sql


def test_literals_are_escaped(catalogue):
    sql = compile_sql(Intent(metric="hero_price", filters={"market": ["USA' or '1'='1"]}), catalogue, "pub")
    assert "'USA\\' or \\'1\\'=\\'1'" in sql                   # (guardrails reject it before anyway)


def test_formatting(catalogue):
    assert fmt_value(0.0524, catalogue.metrics["category_lfl_change"]) == "+5.24%"
    assert fmt_value(3310, catalogue.metrics["hero_price"], "USD") == "3,310 USD"
    assert fmt_value(444, catalogue.metrics["price_change_count"]) == "444"
