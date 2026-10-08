"""Deterministic checks between 'what the translator understood' and 'what runs on the warehouse'.

Whoever filled the Intent (rules or an LLM), nothing runs unless every check passes. A failure is a
plain refusal with the reason and what can be asked instead - never a guess.
"""

from __future__ import annotations

from .intent import Intent, Refusal
from .semantic import Catalogue
from .vocabulary import Vocabulary


def check(intent: Intent, cat: Catalogue, vocab: Vocabulary) -> Refusal | None:
    if not intent.metric or intent.metric not in cat.metrics:
        return Refusal(f"'{intent.metric}' is not a governed metric.",
                       "Governed metrics: " + ", ".join(m.name for m in cat.public_metrics()))
    metric = cat.metrics[intent.metric]
    if metric.hidden:
        return Refusal(f"{metric.name} is a building block of another metric and is not answered on its own.")
    model = cat.model_of(metric)
    dims = cat.dimensions_of(metric)

    # 1. dimensions must belong to the metric's semantic model
    unknown = [d for d in list(intent.group_by) + list(intent.filters) if d not in dims]
    if unknown:
        return Refusal(f"'{metric.label}' cannot be broken down by {', '.join(sorted(set(unknown)))}.",
                       f"Available for this metric: {', '.join(d for d in dims if d != model.time_dimension)}.")

    # 2. filter values must exist in the published data - no invented market, product or category
    for dim, values in intent.filters.items():
        allowed = set(vocab.values_for(model.name, dim))
        bad = [v for v in values if v not in allowed]
        if bad:
            return Refusal(f"{', '.join(bad)} is not a known value of {dim}.",
                           f"Known values: {', '.join(sorted(allowed))}.")
        if not values:
            return Refusal(f"Empty filter on {dim}.")

    # 3. no adding up currencies: currency metrics need ONE market at a time
    for req in metric.requires:
        if req not in intent.group_by and len(intent.filters.get(req, [])) != 1:
            return Refusal(
                f"'{metric.label}' is in local currency: averaging EUR, JPY and KRW together has no meaning.",
                f"Ask for one {req} (e.g. '... in France') or per {req} (e.g. '... by market').")

    # 4. the period must contain published data
    bounds = vocab.bounds(model.name)
    if bounds and intent.time_start and intent.time_end:
        if intent.time_end < bounds[0] or intent.time_start > bounds[1]:
            return Refusal(f"No published data for {intent.time_label or 'this period'}.",
                           f"{metric.label} is available from {bounds[0]} to {bounds[1]} (released deliveries only).")
        if intent.time_start > intent.time_end:
            return Refusal("The period ends before it starts.")
    return None
