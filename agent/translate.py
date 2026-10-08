"""Question -> structured Intent. Two interchangeable translators, same output form.

RuleTranslator    offline, deterministic: synonyms from the semantic layer + values from the data.
                  No API key, no cost, fully testable - the default.
ClaudeTranslator  an LLM fills the SAME form through a tool call (JSON schema). It is only a better
                  reader of messy questions: it still cannot write SQL, and its form goes through
                  exactly the same guardrails. Enabled when ANTHROPIC_API_KEY is set.
"""

from __future__ import annotations

import calendar
import json
import os
import re
from collections import defaultdict
from datetime import date

from .intent import Intent, Refusal
from .semantic import Catalogue, Metric
from .vocabulary import Vocabulary, normalise

MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
MONTHS["sept"] = 9
MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))

GROUP_PATTERNS = {
    "market": r"\b(by|per|each|every|across|which|all|in each) (the )?(market|markets|country|countries)\b|\bmarket by market\b",
    "macro_category": r"\b(by|per|each|every|across|which|all) (the )?(category|categories)\b",
    "product_label": r"\b(by|per|each|every|which|all) (the )?(hero|heroes|product|products)\b",
    "change_direction": r"\bby direction\b|\bincreases? (and|vs|versus) decreases?\b",
}
TIME_GROUP = r"\b(by|per|each|every) (month|week|delivery)\b|\bover time\b|\btrend\b|\bmonthly\b|\bweekly\b|\bhistory\b|\bevolution\b"
OTHER_PLACES = ["germany", "italy", "spain", "switzerland", "netherlands", "belgium", "austria", "portugal",
                "sweden", "norway", "denmark", "poland", "russia", "turkey", "india", "indonesia", "vietnam",
                "philippines", "brazil", "argentina", "chile", "colombia", "qatar", "kuwait", "bahrain", "israel",
                "egypt", "south africa", "nigeria", "new zealand", "macau", "macao"]
ORDER_DESC = r"\b(highest|largest|biggest|most|top|maximum|max)\b"
ORDER_ASC = r"\b(lowest|smallest|least|minimum|min)\b"


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def parse_period(text: str, periods: list[date]) -> tuple[date | None, date | None, str | None]:
    """Find the period a question talks about. Relative words are relative to the published data."""
    if not periods:
        return None, None, None
    latest, default_year = periods[-1], periods[-1].year

    def year_of(y: str | None) -> int:
        return int(y) if y else default_year

    m = re.search(rf"\b(?:from|between)\s+({MONTH_RE})(?:\s+(\d{{4}}))?\s+(?:to|and|until)\s+({MONTH_RE})(?:\s+(\d{{4}}))?\b", text)
    if m:
        s, _ = _month_bounds(year_of(m.group(2)), MONTHS[m.group(1)])
        _, e = _month_bounds(year_of(m.group(4)), MONTHS[m.group(3)])
        return s, e, f"{s:%B %Y} to {e:%B %Y}"
    m = re.search(rf"\bsince\s+({MONTH_RE})(?:\s+(\d{{4}}))?\b", text)
    if m:
        s, _ = _month_bounds(year_of(m.group(2)), MONTHS[m.group(1)])
        return s, latest, f"since {s:%B %Y}"
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if m:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return d, d, d.isoformat()
    m = re.search(r"\b(\d{4})-(\d{2})\b", text)
    if m:
        s, e = _month_bounds(int(m.group(1)), int(m.group(2)))
        return s, e, f"{s:%B %Y}"
    m = re.search(r"\bq([1-4])(?:\s+(\d{4}))?\b", text)
    if m:
        q, y = int(m.group(1)), year_of(m.group(2))
        s, _ = _month_bounds(y, 3 * q - 2)
        _, e = _month_bounds(y, 3 * q)
        return s, e, f"Q{q} {y}"
    for m in re.finditer(rf"\b({MONTH_RE})\b(?:\s+(\d{{4}}))?", text):
        word, year = m.group(1), m.group(2)
        if word == "may" and not year and not re.search(r"\b(in|of|for|during|since) may\b", text):
            continue                                       # "may" the verb
        s, e = _month_bounds(year_of(year), MONTHS[word])
        return s, e, f"{s:%B %Y}"
    if re.search(r"\b(last|this|previous|latest) month\b", text):
        s, e = _month_bounds(latest.year, latest.month)
        return s, e, f"{s:%B %Y} (latest month)"
    if re.search(r"\b(latest|most recent|last|this|current) (delivery|week)\b|\b(latest|now|today|currently|current)\b", text):
        return latest, latest, f"{latest.isoformat()} (latest delivery)"
    m = re.search(r"\b(20\d{2})\b", text)
    if m:
        y = int(m.group(1))
        return date(y, 1, 1), date(y, 12, 31), str(y)
    return None, None, None


class RuleTranslator:
    name = "rules"

    def __init__(self, catalogue: Catalogue, vocab: Vocabulary):
        self.cat = catalogue
        self.vocab = vocab

    # -- values ---------------------------------------------------------------------------------
    def _find_values(self, text: str) -> tuple[dict[str, list[str]], str]:
        """Longest alias first; a matched span is consumed so 'Le City bag' is not also 'bag'."""
        found: dict[str, list[str]] = defaultdict(list)
        pool = [(alias, dim, value) for dim, amap in self.vocab.aliases.items() if dim != "change_direction"
                for alias, value in amap.items()]
        for alias, dim, value in sorted(pool, key=lambda t: len(t[0]), reverse=True):
            pattern = r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])"
            if re.search(pattern, text):
                if value not in found[dim]:
                    found[dim].append(value)
                text = re.sub(pattern, " # ", text)
        if found.get("pointer_id"):                       # HERO-01 -> its product
            pointer_to_label = self._pointer_labels()
            for p in found.pop("pointer_id"):
                label = pointer_to_label.get(p)
                if label and label not in found["product_label"]:
                    found["product_label"].append(label)
        if found.get("product_label"):                    # "Triple S sneaker" is a hero, not the Shoes category
            found.pop("macro_category", None)
        return dict(found), text

    def _pointer_labels(self) -> dict[str, str]:
        ids = self.vocab.values_for("hero_prices", "pointer_id")
        labels = self.vocab.values_for("hero_prices", "product_label")
        return dict(zip(ids, labels)) if len(ids) == len(labels) else {}

    # -- metric ---------------------------------------------------------------------------------
    def _choose_metric(self, text: str, residue: str, dims: set[str]) -> Metric | None:
        candidates = [m for m in self.cat.public_metrics() if dims <= set(self.cat.dimensions_of(m))]
        if re.search(r"\bhero(es)?\b", text):
            candidates = [m for m in candidates if m.semantic_model == "hero_prices"] or candidates
        words = " " + re.sub(r"\s*#\s*", " ", residue) + " "

        def score(m: Metric) -> int:
            hits = [len(s) for s in m.synonyms
                    if re.search(r"(?<![a-z0-9])" + re.escape(s) + r"(?![a-z0-9])", words)]
            return max(hits, default=0)

        scored = sorted(candidates, key=score, reverse=True)
        if scored and score(scored[0]) > 0:
            return scored[0]
        # no synonym: the values mentioned still point at one semantic model -> its first metric
        if "product_label" in dims or re.search(r"\bhero(es)?\b", text):
            return self.cat.metrics.get("hero_price")
        return None

    # -- main -----------------------------------------------------------------------------------
    def translate(self, question: str) -> Intent | Refusal:
        text = " " + normalise(question) + " "
        filters, residue = self._find_values(text)
        outside = [p for p in OTHER_PLACES if re.search(rf"\b{p}\b", residue)]
        if outside:                                       # never silently drop a place we don't monitor
            return Refusal(f"{outside[0].title()} is not one of the monitored markets.",
                           "Monitored markets: " + ", ".join(sorted(self.vocab.market_currency)) + ".")
        metric = self._choose_metric(text, residue, set(filters))
        if metric is None:
            names = ", ".join(m.label for m in self.cat.public_metrics())
            return Refusal("I could not match this question to a governed metric.",
                           f"I can answer questions about: {names}. Try `python -m agent metrics`.")
        model = self.cat.model_of(metric)
        dims = self.cat.dimensions_of(metric)
        intent = Intent(metric=metric.name, filters=filters)

        if "change_direction" in dims:
            for alias, value in self.vocab.aliases.get("change_direction", {}).items():
                if re.search(rf"\b{re.escape(alias)}\b", residue):
                    intent.filters.setdefault("change_direction", [])
                    if value not in intent.filters["change_direction"]:
                        intent.filters["change_direction"].append(value)

        # group by: explicit words, then any dimension given several values, then the metric default
        explicit = [d for d, pat in GROUP_PATTERNS.items() if d in dims and re.search(pat, text)]
        multi = [d for d, vals in intent.filters.items() if len(vals) > 1 and d not in explicit]
        intent.group_by = explicit + multi
        intent.group_by_time = bool(re.search(TIME_GROUP, text))
        if not intent.group_by and not intent.group_by_time:
            intent.group_by = [d for d in metric.default_group_by
                               if d in dims and len(intent.filters.get(d, [])) != 1]
        for req in metric.requires:                       # currency metrics: one market at a time
            if req not in intent.group_by and len(intent.filters.get(req, [])) != 1:
                intent.group_by.append(req)
                intent.notes.append(f"Prices are in local currency, so they are shown per {req}.")

        if re.search(ORDER_DESC, text):
            intent.order = "desc"
        elif re.search(ORDER_ASC, text):
            intent.order = "asc"

        # time
        periods = self.vocab.periods.get(model.name, [])
        start, end, label = parse_period(text, periods)
        if start is None and metric.default_time == "latest" and periods and not intent.group_by_time:
            start = end = periods[-1]
            label = (f"latest month ({start:%B %Y})" if dims[model.time_dimension].granularity == "month"
                     else f"latest delivery ({start.isoformat()})")
        if start is not None and not intent.group_by_time:
            in_range = [p for p in periods if start <= p <= end]
            if len(in_range) == 1:
                start = end = in_range[0]
            elif len(in_range) > 1 and metric.point_in_time:
                # a level (a price, a number of listed products): adding or averaging weeks means nothing
                start = end = in_range[-1]
                intent.notes.append(f"{metric.label} is a point-in-time value: using the latest delivery in "
                                    f"{label}, {start.isoformat()}.")
            elif len(in_range) > 1 and metric.unit == "percent":
                # changes are per period: show each period rather than an average of changes
                intent.group_by_time = True
                intent.notes.append(f"{metric.label} is measured per period: showing each period of {label}.")
        intent.time_start, intent.time_end = start, end
        intent.time_label = label or "all published history"
        return intent


# --------------------------------------------------------------------------------------------- LLM

class ClaudeTranslator:
    """Same form, filled by Claude through a forced tool call. Never sees SQL, never writes SQL."""
    name = "claude"

    def __init__(self, catalogue: Catalogue, vocab: Vocabulary, model: str | None = None):
        import anthropic  # optional dependency

        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("AGENT_MODEL", "claude-sonnet-4-5")
        self.cat, self.vocab = catalogue, vocab

    @staticmethod
    def available() -> bool:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return False
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return True

    def _tool(self) -> dict:
        metrics = [m.name for m in self.cat.public_metrics()]
        dims = sorted({d for m in self.cat.public_metrics() for d in self.cat.dimensions_of(m)})
        return {
            "name": "structured_question",
            "description": "The question, restated as one governed metric with its dimensions, filters and period.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "metric": {"type": ["string", "null"], "enum": metrics + [None],
                               "description": "null if no governed metric answers the question"},
                    "group_by": {"type": "array", "items": {"type": "string", "enum": dims}},
                    "filters": {"type": "object", "additionalProperties": {"type": "array", "items": {"type": "string"}}},
                    "time_start": {"type": ["string", "null"], "description": "YYYY-MM-DD inclusive"},
                    "time_end": {"type": ["string", "null"], "description": "YYYY-MM-DD inclusive"},
                    "time_label": {"type": ["string", "null"]},
                    "group_by_time": {"type": "boolean"},
                    "order": {"type": ["string", "null"], "enum": ["desc", "asc", None]},
                },
                "required": ["metric", "group_by", "filters", "group_by_time"],
            },
        }

    def translate(self, question: str) -> Intent | Refusal:
        values = {f"{m}.{d}": v[:40] for (m, d), v in self.vocab.values.items()}
        periods = {m: [p[0].isoformat(), p[-1].isoformat()] for m, p in self.vocab.periods.items() if p}
        system = (
            "You translate questions about Balenciaga price data into a structured form. "
            "Only use the metrics, dimensions and values listed. Never invent a value. "
            "If no metric fits, set metric to null.\n\n"
            f"Governed metrics:\n{self.cat.describe()}\n\n"
            f"Allowed dimension values (semantic_model.dimension -> values): {json.dumps(values)}\n"
            f"Published periods per semantic model: {json.dumps(periods)}\n"
            "Prices are in local currency: currency metrics must be grouped by or filtered to one market."
        )
        response = self.client.messages.create(
            model=self.model, max_tokens=800, system=system,
            tools=[self._tool()], tool_choice={"type": "tool", "name": "structured_question"},
            messages=[{"role": "user", "content": question}],
        )
        block = next((b for b in response.content if getattr(b, "type", "") == "tool_use"), None)
        if block is None or not block.input.get("metric"):
            return Refusal("No governed metric answers this question.",
                           "Try `python -m agent metrics` to see what can be asked.")
        return Intent.from_dict(block.input)


def make_translator(catalogue: Catalogue, vocab: Vocabulary, prefer: str = "auto"):
    if prefer == "claude" or (prefer == "auto" and ClaudeTranslator.available()):
        return ClaudeTranslator(catalogue, vocab)
    return RuleTranslator(catalogue, vocab)
