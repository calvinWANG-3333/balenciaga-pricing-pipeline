"""The governed catalogue, read from dbt's compiled semantic manifest.

The agent never declares a metric itself. Everything it may answer comes from
dbt/target/semantic_manifest.json, produced by `dbt parse` from models/semantic/*.yml:
which metrics exist, how each is computed (measure, aggregation, column), which dimensions it can be
grouped or filtered by, and the agent-specific hints in `config.meta.agent`.
Change a metric in dbt -> re-run `dbt parse` -> the agent follows. One definition, no drift.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "dbt" / "target" / "semantic_manifest.json"

SQL_AGG = {"sum": "sum", "average": "avg", "count": "count", "min": "min", "max": "max",
           "count_distinct": "count_distinct", "sum_boolean": "sum_boolean"}


@dataclass(frozen=True)
class Dimension:
    name: str
    type: str                      # categorical | time
    expr: str                      # column (or SQL expression) in the relation
    granularity: str | None        # time dimensions only: day | month ...
    description: str = ""


@dataclass(frozen=True)
class Measure:
    name: str
    agg: str
    expr: str
    semantic_model: str


@dataclass
class SemanticModel:
    name: str
    alias: str                     # the published view, e.g. pub_micro__hero_prices_weekly
    description: str
    time_dimension: str
    dimensions: dict[str, Dimension] = field(default_factory=dict)


@dataclass(frozen=True)
class Metric:
    name: str
    label: str
    description: str
    type: str                      # simple | ratio
    measure: str | None            # simple
    numerator: str | None          # ratio: names of two simple metrics
    denominator: str | None
    semantic_model: str
    synonyms: tuple[str, ...]
    unit: str                      # percent | currency | count
    requires: tuple[str, ...]
    default_group_by: tuple[str, ...]
    default_time: str              # latest | all
    point_in_time: bool            # a level (price, listed products), not a flow
    hidden: bool


class Catalogue:
    def __init__(self, models: dict[str, SemanticModel], measures: dict[str, Measure], metrics: dict[str, Metric]):
        self.models = models
        self.measures = measures
        self.metrics = metrics

    def public_metrics(self) -> list[Metric]:
        return [m for m in self.metrics.values() if not m.hidden]

    def model_of(self, metric: Metric) -> SemanticModel:
        return self.models[metric.semantic_model]

    def dimensions_of(self, metric: Metric) -> dict[str, Dimension]:
        return self.model_of(metric).dimensions

    def simple_measure(self, metric_name: str) -> Measure:
        m = self.metrics[metric_name]
        if m.type != "simple":
            raise ValueError(f"{metric_name} is not a simple metric")
        return self.measures[m.measure]

    def describe(self) -> str:
        """A compact text description of the catalogue (used in the LLM prompt and the UI)."""
        lines = []
        for m in self.public_metrics():
            dims = ", ".join(self.dimensions_of(m))
            req = f" Requires: {', '.join(m.requires)}." if m.requires else ""
            lines.append(f"- {m.name} ({m.unit}): {m.description} Dimensions: {dims}.{req}")
        return "\n".join(lines)


def manifest_path() -> Path:
    return Path(os.environ.get("AGENT_SEMANTIC_MANIFEST", DEFAULT_MANIFEST))


def load(path: Path | None = None) -> Catalogue:
    path = path or manifest_path()
    if not path.exists():
        raise SystemExit(
            f"Semantic manifest not found at {path}.\n"
            "Run `dbt parse` in the dbt/ folder first (see docs/08_metrics_agent.md, step 3).")
    doc = json.loads(path.read_text())

    models: dict[str, SemanticModel] = {}
    measures: dict[str, Measure] = {}
    for sm in doc["semantic_models"]:
        model = SemanticModel(
            name=sm["name"],
            alias=sm["node_relation"]["alias"],
            description=sm.get("description") or "",
            time_dimension=sm["defaults"]["agg_time_dimension"],
        )
        for d in sm["dimensions"]:
            model.dimensions[d["name"]] = Dimension(
                name=d["name"],
                type=d["type"],
                expr=d.get("expr") or d["name"],
                granularity=(d.get("type_params") or {}).get("time_granularity"),
                description=d.get("description") or "",
            )
        models[model.name] = model
        for ms in sm["measures"]:
            measures[ms["name"]] = Measure(ms["name"], ms["agg"], ms.get("expr") or ms["name"], model.name)

    metrics: dict[str, Metric] = {}
    raw_metrics = {m["name"]: m for m in doc["metrics"]}
    for name, m in raw_metrics.items():
        tp = m["type_params"]
        agent_meta = ((m.get("config") or {}).get("meta") or {}).get("agent") or {}
        if m["type"] == "simple":
            measure_name = tp["measure"]["name"]
            sm_name = measures[measure_name].semantic_model
            numerator = denominator = None
        elif m["type"] == "ratio":
            measure_name = None
            numerator, denominator = tp["numerator"]["name"], tp["denominator"]["name"]
            sm_name = measures[raw_metrics[numerator]["type_params"]["measure"]["name"]].semantic_model
        else:   # derived / cumulative / conversion metrics are not supported by this agent yet
            continue
        metrics[name] = Metric(
            name=name,
            label=m.get("label") or name,
            description=" ".join((m.get("description") or "").split()),
            type=m["type"],
            measure=measure_name,
            numerator=numerator,
            denominator=denominator,
            semantic_model=sm_name,
            synonyms=tuple(s.lower() for s in agent_meta.get("synonyms", [])),
            unit=agent_meta.get("unit", "count"),
            requires=tuple(agent_meta.get("requires", [])),
            default_group_by=tuple(agent_meta.get("default_group_by", [])),
            default_time=agent_meta.get("default_time", "latest"),
            point_in_time=bool(agent_meta.get("point_in_time", False)),
            hidden=bool(agent_meta.get("hidden", False)),
        )
    return Catalogue(models, measures, metrics)
