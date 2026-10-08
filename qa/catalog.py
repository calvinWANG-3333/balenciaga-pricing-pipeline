"""Load and validate the check catalogue (checks.yml), and render each check into runnable SQL."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

CATALOGUE_PATH = Path(__file__).with_name("checks.yml")

DIMENSIONS = {"timeliness", "completeness", "validity", "plausibility", "consistency"}
SEVERITIES = {"block", "warn"}
SCOPES = ("micro", "macro")
THRESHOLD_KEYS = {"warn_above", "warn_below", "fail_above", "fail_below"}
ANOMALY_KEYS = {"window", "min_history", "z", "min_value"}


@dataclass(frozen=True)
class Delivery:
    """One delivery of one scope, with the two deliveries before it (for change and reversion checks)."""
    scope: str
    as_of_date: date
    prev_date: date | None
    prev2_date: date | None


@dataclass(frozen=True)
class Check:
    id: str
    dimension: str
    severity: str
    scopes: tuple[str, ...]
    datasets: tuple[str, ...]
    description: str
    rules: dict[str, dict[str, Any]]          # scope -> rule set
    sql: str

    def rules_for(self, scope: str) -> dict[str, Any]:
        return self.rules[scope]


@dataclass(frozen=True)
class Dataset:
    name: str
    publishable: bool
    deliveries: dict[str, str]
    catalogue: str


@dataclass
class Catalogue:
    datasets: dict[str, Dataset]
    checks: list[Check] = field(default_factory=list)

    def checks_for(self, dataset: str, scope: str) -> list[Check]:
        return [c for c in self.checks if dataset in c.datasets and scope in c.scopes]


class CatalogueError(ValueError):
    pass


def _normalise_rules(check_id: str, raw: dict[str, Any], scopes: tuple[str, ...], severity: str) -> dict[str, dict]:
    """Rules can be written once for all scopes, or per scope. Return them per scope, validated."""
    per_scope = raw if set(raw) <= set(SCOPES) and raw else {s: raw for s in scopes}
    for scope in scopes:
        if scope not in per_scope:
            raise CatalogueError(f"{check_id}: no rules for scope {scope!r}")
        rules = per_scope[scope]
        unknown = set(rules) - THRESHOLD_KEYS - {"anomaly"}
        if unknown:
            raise CatalogueError(f"{check_id}: unknown rule(s) {sorted(unknown)}")
        if not rules:
            raise CatalogueError(f"{check_id}: empty rule set for {scope}")
        if "anomaly" in rules and set(rules["anomaly"]) - ANOMALY_KEYS:
            raise CatalogueError(f"{check_id}: unknown anomaly setting(s) {sorted(set(rules['anomaly']) - ANOMALY_KEYS)}")
        if severity == "warn" and {"fail_above", "fail_below"} & set(rules):
            raise CatalogueError(f"{check_id}: a severity 'warn' check cannot have fail_* rules")
    return per_scope


def load(path: Path = CATALOGUE_PATH) -> Catalogue:
    doc = yaml.safe_load(path.read_text())
    datasets = {
        name: Dataset(name=name, publishable=bool(d.get("publishable", False)),
                      deliveries=d["deliveries"], catalogue=d["catalogue"])
        for name, d in doc["datasets"].items()
    }
    checks, seen = [], set()
    for raw in doc["checks"]:
        cid = raw["id"]
        if cid in seen:
            raise CatalogueError(f"duplicate check id {cid}")
        seen.add(cid)
        if raw["dimension"] not in DIMENSIONS:
            raise CatalogueError(f"{cid}: dimension must be one of {sorted(DIMENSIONS)}")
        if raw["severity"] not in SEVERITIES:
            raise CatalogueError(f"{cid}: severity must be one of {sorted(SEVERITIES)}")
        scopes = tuple(raw["scopes"])
        unknown_ds = set(raw["datasets"]) - set(datasets)
        if unknown_ds:
            raise CatalogueError(f"{cid}: unknown dataset(s) {sorted(unknown_ds)}")
        checks.append(Check(
            id=cid,
            dimension=raw["dimension"],
            severity=raw["severity"],
            scopes=scopes,
            datasets=tuple(raw["datasets"]),
            description=" ".join(raw["description"].split()),
            rules=_normalise_rules(cid, raw["rules"], scopes, raw["severity"]),
            sql=raw["sql"],
        ))
    return Catalogue(datasets=datasets, checks=checks)


# ---------------------------------------------------------------------------------------------- SQL

def _date_literal(d: date | None) -> str:
    return f"date'{d.isoformat()}'" if d else "cast(null as date)"


def deliveries_values(deliveries: list[Delivery]) -> str:
    """The delivery calendar as an inline table, so every check sees the same calendar."""
    rows = ",\n        ".join(
        f"('{d.scope}', {_date_literal(d.as_of_date)}, {_date_literal(d.prev_date)}, {_date_literal(d.prev2_date)})"
        for d in deliveries
    )
    return f"select * from values\n        {rows}\n    as t(scope, as_of_date, prev_date, prev2_date)"


def render(check: Check, dataset: Dataset, deliveries: list[Delivery], placeholders: dict[str, str]) -> str:
    """Wrap a check's query with the shared CTEs (deliveries, catalogue, scoped)."""
    catalogue_sql = dataset.catalogue.format(**placeholders).strip()
    body = check.sql.format(**placeholders).strip()
    # A check that starts with its own WITH merges its CTEs into ours.
    if body.lower().startswith("with "):
        body = ",\n" + body[5:]
        joiner = ""
    else:
        joiner = "\n"
    prelude = f"""with deliveries as (
    {deliveries_values(deliveries)}
),
catalogue as (
    {catalogue_sql}
),
scoped as (
    select d.scope, d.as_of_date, d.prev_date, d.prev2_date,
           c.market, c.object_id, c.served_crawl_date, c.price_local
    from deliveries d
    inner join catalogue c
        on c.as_of_date = d.as_of_date
    inner join {placeholders['marts']}.dim_market m
        on m.market = c.market
    where d.scope = 'macro' or m.is_in_micro_scope
)"""
    return prelude + joiner + body
