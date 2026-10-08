"""The check catalogue itself is code: validate it like code."""

import textwrap
from pathlib import Path

import pytest

from qa import catalog as cat


def test_shipped_catalogue_is_valid():
    catalogue = cat.load()
    assert len(catalogue.checks) >= 10
    assert {c.dimension for c in catalogue.checks} == cat.DIMENSIONS     # every dimension is covered
    for c in catalogue.checks:
        assert c.description, c.id
        for scope in c.scopes:
            assert c.rules_for(scope)


def test_every_check_renders_valid_looking_sql():
    catalogue = cat.load()
    calendar = [cat.Delivery("micro", __import__("datetime").date(2026, 9, 15), None, None)]
    ph = {"marts": "m", "intermediate": "i", "ops": "o"}
    for name, dataset in catalogue.datasets.items():
        for check in catalogue.checks:
            if name in check.datasets:
                sql = cat.render(check, dataset, calendar, ph)
                assert sql.lower().startswith("with deliveries as")
                assert "{" not in sql, f"unfilled placeholder in {check.id}"


def _write(tmp_path: Path, checks_yaml: str) -> Path:
    doc = textwrap.dedent("""
        version: 1
        datasets:
          marts:
            publishable: true
            deliveries: {micro: "select 1", macro: "select 1"}
            catalogue: "select 1"
        checks:
    """) + textwrap.indent(textwrap.dedent(checks_yaml), "  ")
    p = tmp_path / "checks.yml"
    p.write_text(doc)
    return p


def test_warn_check_cannot_fail(tmp_path):
    p = _write(tmp_path, """
        - id: x
          dimension: validity
          severity: warn
          scopes: [micro]
          datasets: [marts]
          description: d
          rules: {fail_above: 1}
          sql: select 1
    """)
    with pytest.raises(cat.CatalogueError, match="cannot have fail"):
        cat.load(p)


def test_unknown_dimension_is_rejected(tmp_path):
    p = _write(tmp_path, """
        - id: x
          dimension: vibes
          severity: block
          scopes: [micro]
          datasets: [marts]
          description: d
          rules: {fail_above: 1}
          sql: select 1
    """)
    with pytest.raises(cat.CatalogueError, match="dimension"):
        cat.load(p)
