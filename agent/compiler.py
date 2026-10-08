"""Intent -> SQL, deterministically. The only place SQL is written, and it is a template.

Every identifier comes from the semantic manifest; every literal has already been checked against the
values that exist in the data (guardrails), and is escaped anyway. The query reads one published view.
"""

from __future__ import annotations

from .intent import Intent
from .semantic import Catalogue, Measure

ROW_LIMIT = 500


def _literal(value: str) -> str:
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def _aggregate(measure: Measure) -> str:
    agg, expr = measure.agg, measure.expr
    if agg == "count_distinct":
        return f"count(distinct {expr})"
    if agg == "sum_boolean":
        return f"sum(case when {expr} then 1 else 0 end)"
    return f"{'avg' if agg == 'average' else agg}({expr})"


def metric_expression(cat: Catalogue, metric_name: str) -> str:
    metric = cat.metrics[metric_name]
    if metric.type == "simple":
        return _aggregate(cat.measures[metric.measure])
    num = _aggregate(cat.simple_measure(metric.numerator))
    den = _aggregate(cat.simple_measure(metric.denominator))
    return f"{num} / nullif({den}, 0)"


def compile_sql(intent: Intent, cat: Catalogue, published_schema: str) -> str:
    metric = cat.metrics[intent.metric]
    model = cat.model_of(metric)
    dims = model.dimensions
    time_dim = dims[model.time_dimension]

    select, group = [], []
    if intent.group_by_time:
        select.append(f"{time_dim.expr} as {time_dim.name}")
        group.append(time_dim.expr)
    for d in intent.group_by:
        select.append(f"{dims[d].expr} as {d}")
        group.append(dims[d].expr)
    select.append(f"{metric_expression(cat, metric.name)} as {metric.name}")

    where = []
    if intent.time_start:
        where.append(f"{time_dim.expr} >= date'{intent.time_start.isoformat()}'")
    if intent.time_end:
        where.append(f"{time_dim.expr} <= date'{intent.time_end.isoformat()}'")
    for d, values in sorted(intent.filters.items()):
        where.append(f"{dims[d].expr} in ({', '.join(_literal(v) for v in values)})")

    sql = "select\n    " + ",\n    ".join(select) + f"\nfrom {published_schema}.{model.alias}"
    if where:
        sql += "\nwhere " + "\n  and ".join(where)
    if group:
        sql += "\ngroup by " + ", ".join(group)
        if intent.order:
            sql += f"\norder by {metric.name} {intent.order}"
        else:
            sql += "\norder by " + ", ".join(group)
    sql += f"\nlimit {ROW_LIMIT}"
    return sql
