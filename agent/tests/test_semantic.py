"""The committed manifest fixture must match the semantic YAML in dbt - otherwise tests test the past."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_fixture_matches_dbt_yaml(catalogue):
    metrics_yaml = yaml.safe_load((ROOT / "dbt/models/semantic/_metrics.yml").read_text())["metrics"]
    assert {m["name"] for m in metrics_yaml} == set(catalogue.metrics), \
        "metrics changed: run `dbt parse` and copy target/semantic_manifest.json to agent/tests/fixtures/"
    for m in metrics_yaml:
        meta = m.get("config", {}).get("meta", {}).get("agent", {})
        assert tuple(s.lower() for s in meta.get("synonyms", [])) == catalogue.metrics[m["name"]].synonyms, m["name"]


def test_every_public_metric_is_documented(catalogue):
    for m in catalogue.public_metrics():
        assert m.description and m.unit in {"percent", "currency", "count"}, m.name
        assert m.synonyms, f"{m.name} has no synonyms: the agent could never pick it"


def test_currency_metrics_require_a_market(catalogue):
    for m in catalogue.public_metrics():
        if m.unit == "currency":
            assert "market" in m.requires, f"{m.name} would average currencies"


def test_ratio_metric_resolves_to_two_measures(catalogue):
    m = catalogue.metrics["category_lfl_change_product_weighted"]
    assert m.type == "ratio" and m.semantic_model == "category_monthly"
    assert catalogue.simple_measure(m.numerator).expr == "lfl_mean_change * lfl_n_products"
