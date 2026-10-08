"""Turn result rows into an answer. Deterministic templates by default; Claude can rephrase, never compute.

The numbers in the answer are always the numbers the query returned: the LLM narrator (optional) only
receives the finished table, and the deterministic text is kept next to it for comparison.
"""

from __future__ import annotations

import json
import os
from datetime import date
from decimal import Decimal

from .intent import Intent
from .semantic import Catalogue, Metric
from .vocabulary import Vocabulary


def fmt_value(value, metric: Metric, currency: str | None = None) -> str:
    if value is None:
        return "n/a"
    v = float(value) if isinstance(value, Decimal) else value
    if metric.unit == "percent":
        return f"{v:+.2%}"
    if metric.unit == "currency":
        return f"{v:,.0f} {currency}" if currency else f"{v:,.0f} (local currency)"
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def _currency(row: dict, intent: Intent, vocab: Vocabulary) -> str | None:
    market = row.get("market") or (intent.filters.get("market") or [None])[0]
    return vocab.market_currency.get(market) if market else None


def _scope_text(intent: Intent) -> str:
    parts = []
    for d, values in sorted(intent.filters.items()):
        parts.append(" / ".join(values))
    return ", ".join(parts)


def narrate(intent: Intent, rows: list[dict], cat: Catalogue, vocab: Vocabulary) -> str:
    metric = cat.metrics[intent.metric]
    period = intent.time_label or "all published history"
    scope = _scope_text(intent)
    head = f"**{metric.label}**" + (f" - {scope}" if scope else "") + f" - {period}"
    if not rows:
        return head + ": no data in the released deliveries for this selection."
    if len(rows) == 1 and not intent.group_by and not intent.group_by_time:
        value = rows[0][metric.name]
        return f"{head}: **{fmt_value(value, metric, _currency(rows[0], intent, vocab))}**."

    keys = [k for k in rows[0] if k != metric.name]
    lines = [head + ":", "", "| " + " | ".join(keys + [metric.label]) + " |",
             "|" + "---|" * (len(keys) + 1)]
    for r in rows:
        cells = [r[k].isoformat() if isinstance(r[k], date) else str(r[k]) for k in keys]
        lines.append("| " + " | ".join(cells + [fmt_value(r[metric.name], metric, _currency(r, intent, vocab))]) + " |")
    numeric = [r for r in rows if r[metric.name] is not None]
    if len(numeric) > 1 and metric.unit != "currency" and keys:
        top = max(numeric, key=lambda r: float(r[metric.name]))
        low = min(numeric, key=lambda r: float(r[metric.name]))
        label = lambda r: " / ".join(str(r[k]) for k in keys)   # noqa: E731
        lines += ["", f"Highest: {label(top)} ({fmt_value(top[metric.name], metric)}); "
                      f"lowest: {label(low)} ({fmt_value(low[metric.name], metric)})."]
    return "\n".join(lines)


def narrate_with_claude(question: str, deterministic: str, rows: list[dict], metric: Metric) -> str | None:
    """Optional: rephrase for a business reader. Gets the finished table; told not to compute anything."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        return None
    client = anthropic.Anthropic()
    payload = json.dumps(rows[:50], default=str)
    msg = client.messages.create(
        model=os.environ.get("AGENT_MODEL", "claude-sonnet-4-5"), max_tokens=400,
        system=("You explain query results to a business reader in 2-4 sentences. Use ONLY numbers present "
                "in the result; do not compute new ones, do not speculate about causes."),
        messages=[{"role": "user", "content": f"Question: {question}\nMetric: {metric.label} - {metric.description}\n"
                                              f"Result rows: {payload}\nDraft answer: {deterministic}"}],
    )
    return "".join(getattr(b, "text", "") for b in msg.content).strip() or None
