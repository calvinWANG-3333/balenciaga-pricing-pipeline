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

        # group by: explicit words, then any dimension given several values (added by the policy)
        intent.group_by = [d for d, pat in GROUP_PATTERNS.items() if d in dims and re.search(pat, text)]
        intent.group_by_time = wants_time_series(text)
        if re.search(ORDER_DESC, text):
            intent.order = "desc"
        elif re.search(ORDER_ASC, text):
            intent.order = "asc"
        intent.time_start, intent.time_end, intent.time_label = parse_period(
            text, self.vocab.periods.get(model.name, []))
        return apply_policy(intent, self.cat, self.vocab)


# --------------------------------------------------------------------------------------------- policy

def wants_time_series(text: str) -> bool:
    """'by month', 'over time', 'trend'... - NOT 'week on week', which describes the metric itself."""
    return bool(re.search(TIME_GROUP, text))


def apply_policy(intent: Intent, cat: Catalogue, vocab: Vocabulary) -> Intent:
    """The agent's business rules, applied to EVERY intent whoever filled it (rules or Claude).

    A translator only says what the question mentions: metric, values, maybe a period. How a level or a
    change is shown (which delivery, per market or not, one period or each period) is decided here,
    deterministically - so two translators that read the question the same way give the same answer.
    """
    metric = cat.metrics[intent.metric]
    model = cat.model_of(metric)
    dims = cat.dimensions_of(metric)
    tdim = dims[model.time_dimension]

    # the time dimension is the period, not a grouping column
    intent.group_by = [d for d in dict.fromkeys(intent.group_by) if d != tdim.name]
    # grouping by a dimension already pinned to one value adds a column, not an answer
    intent.group_by = [d for d in intent.group_by if len(intent.filters.get(d, [])) != 1]
    # a currency is an attribute of a market: "per currency" means per market
    if "currency_code" in intent.group_by:
        intent.group_by.remove("currency_code")
        if "market" in dims and "market" not in intent.group_by and len(intent.filters.get("market", [])) != 1:
            intent.group_by.append("market")
    # several values of a dimension are compared side by side
    intent.group_by += [d for d, vals in intent.filters.items()
                        if len(vals) > 1 and d not in intent.group_by and d in dims]
    if not intent.group_by and not intent.group_by_time:
        intent.group_by = [d for d in metric.default_group_by
                           if d in dims and len(intent.filters.get(d, [])) != 1]
    for req in metric.requires:                           # currency metrics: one market at a time
        if req not in intent.group_by and len(intent.filters.get(req, [])) != 1:
            intent.group_by.append(req)
            intent.notes.append(f"Prices are in local currency, so they are shown per {req}.")

    # period
    periods = vocab.periods.get(model.name, [])
    start, end, label = intent.time_start, intent.time_end, intent.time_label
    if start and not end:
        end = start
    if end and not start:
        start = end
    if start is None and metric.default_time == "latest" and periods and not intent.group_by_time:
        start = end = periods[-1]
        label = (f"latest month ({start:%B %Y})" if tdim.granularity == "month"
                 else f"latest delivery ({start.isoformat()})")
    if start is not None and not intent.group_by_time:
        in_range = [p for p in periods if start <= p <= end]
        if len(in_range) == 1:
            start = end = in_range[0]
        elif len(in_range) > 1 and metric.point_in_time:
            # a level (a price, a number of listed products): adding or averaging weeks means nothing
            start = end = in_range[-1]
            intent.notes.append(f"{metric.label} is a point-in-time value: using the latest delivery in "
                                f"{label or 'the period'}, {start.isoformat()}.")
        elif len(in_range) > 1 and metric.unit == "percent":
            # changes are per period: show each period rather than an average of changes
            intent.group_by_time = True
            intent.notes.append(f"{metric.label} is measured per period: showing each period of "
                                f"{label or 'the range'}.")
    intent.time_start, intent.time_end = start, end
    intent.time_label = label or (f"{start} to {end}" if start else "all published history")
    return intent


# --------------------------------------------------------------------------------------------- LLM

class ClaudeTranslator:
    """Same form, filled by Claude through a forced tool call. Never sees SQL, never writes SQL.

    Division of labour: Claude READS the question (which metric, which values, which period, in any
    wording). Everything the agent DECIDES - default period, point-in-time vs per-period, grouping
    for currencies - is `apply_policy`, the same code as the rule translator. The form Claude returns is
    first cleaned into canonical values, then goes through the policy, then through the guardrails.
    """
    name = "claude"

    def __init__(self, catalogue: Catalogue, vocab: Vocabulary, model: str | None = None, client=None):
        if client is None:
            import anthropic  # optional dependency
            client = anthropic.Anthropic()
        self.client = client
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

    # -- the form ---------------------------------------------------------------------------------
    def _categorical_dims(self) -> dict[str, list[str]]:
        """Dimension -> every value it takes in the published data (time dimensions are not here)."""
        out: dict[str, set[str]] = defaultdict(set)
        for m in self.cat.public_metrics():
            model = self.cat.model_of(m)
            for name, d in self.cat.dimensions_of(m).items():
                if d.type != "time":
                    out[name].update(self.vocab.values_for(model.name, name))
        return {k: sorted(v) for k, v in sorted(out.items())}

    def _tool(self) -> dict:
        metrics = [m.name for m in self.cat.public_metrics()]
        values = self._categorical_dims()
        groupable = [d for d in values if d not in ("currency_code", "pointer_id")]
        filters = {d: {"type": "array", "items": {"type": "string", "enum": v} if v else {"type": "string"}}
                   for d, v in values.items() if d != "pointer_id"}
        return {
            "name": "structured_question",
            "description": "The question, restated as one governed metric with its filters, grouping and period.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "metric": {"type": ["string", "null"], "enum": metrics + [None],
                               "description": "null if no governed metric answers the question"},
                    "filters": {"type": "object", "properties": filters, "additionalProperties": False,
                                "description": "Only values the question names. Omit a dimension it does not name."},
                    "group_by": {"type": "array", "items": {"type": "string", "enum": groupable},
                                 "description": "Only when the question asks for a breakdown ('by market', "
                                                "'which category', 'compare ...'). Never a date column."},
                    "time_start": {"type": ["string", "null"],
                                   "description": "YYYY-MM-DD, first day of the period the question names. "
                                                  "null if it names no period: the agent applies its default."},
                    "time_end": {"type": ["string", "null"],
                                 "description": "YYYY-MM-DD, last day of that period (e.g. 2026-09-30 for September)."},
                    "time_label": {"type": ["string", "null"], "description": "The period in words."},
                    "group_by_time": {"type": "boolean",
                                      "description": "true ONLY if the user wants the evolution across periods "
                                                     "('by month', 'over time', 'trend', 'history'). "
                                                     "'week on week' / 'month on month' describe a change "
                                                     "metric, not a time series: false."},
                    "order": {"type": ["string", "null"], "enum": ["desc", "asc", None],
                              "description": "desc for highest/top/most, asc for lowest/least."},
                },
                "required": ["metric", "filters", "group_by", "group_by_time"],
            },
        }

    # -- cleaning: whatever Claude wrote, make it the canonical form ------------------------------
    def _canonical(self, dim: str, value: str) -> str:
        if value in self.vocab.aliases.get(dim, {}).values():
            return value
        return self.vocab.aliases.get(dim, {}).get(normalise(value), value)   # 'Japan' -> 'JPN'

    def _clean(self, raw: dict, text: str) -> Intent:
        intent = Intent.from_dict({k: v for k, v in raw.items() if k != "notes"})
        metric = self.cat.metrics[intent.metric]
        model = self.cat.model_of(metric)
        tdim = model.dimensions[model.time_dimension]
        time_like = {n for n, d in model.dimensions.items() if d.type == "time"}

        filters: dict[str, list[str]] = {}
        dates: list[date] = []
        for dim, values in intent.filters.items():
            if dim in time_like:                     # a date written as a filter is a period
                dates += [date.fromisoformat(str(v)[:10]) for v in values]
                continue
            if dim == "pointer_id":                  # HERO-01 -> its product
                labels = dict(zip(self.vocab.values_for("hero_prices", "pointer_id"),
                                  self.vocab.values_for("hero_prices", "product_label")))
                dim, values = "product_label", [labels.get(v, v) for v in values]
            canon = [self._canonical(dim, v) for v in values]
            filters.setdefault(dim, [])
            filters[dim] += [v for v in canon if v not in filters[dim]]
        intent.filters = {d: v for d, v in filters.items() if v}
        if "product_label" in intent.filters:        # a hero is more precise than its category
            intent.filters.pop("macro_category", None)
        if dates and intent.time_start is None:
            intent.time_start, intent.time_end = min(dates), max(dates)
            if tdim.granularity == "month":
                intent.time_end = _month_bounds(intent.time_end.year, intent.time_end.month)[1]

        # time series: the explicit flag, or the words; a date column in group_by alone is not enough
        intent.group_by_time = intent.group_by_time or wants_time_series(text)
        # the period: relative words ('last week', 'September') are anchored to the published data
        start, end, label = parse_period(text, self.vocab.periods.get(model.name, []))
        if start is not None:
            intent.time_start, intent.time_end, intent.time_label = start, end, label
        return intent

    def translate(self, question: str) -> Intent | Refusal:
        text = " " + normalise(question) + " "
        outside = [p for p in OTHER_PLACES if re.search(rf"\b{p}\b", text)]
        if outside:                                   # same rule as offline: never drop a place silently
            return Refusal(f"{outside[0].title()} is not one of the monitored markets.",
                           "Monitored markets: " + ", ".join(sorted(self.vocab.market_currency)) + ".")
        periods = {m: [p[0].isoformat(), p[-1].isoformat()] for m, p in self.vocab.periods.items() if p}
        system = (
            "You translate questions about Balenciaga price data into a structured form. "
            "Fill only what the question says: the metric, the values it names, the period it names. "
            "Do not add defaults - the agent applies its own rules for periods and grouping. "
            "Never invent a value. If no metric fits (revenue, forecasts, anything not listed), "
            "set metric to null.\n\n"
            f"Governed metrics:\n{self.cat.describe()}\n\n"
            f"Published periods per semantic model (first, last): {json.dumps(periods)}"
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
        if block.input["metric"] not in self.cat.metrics:
            return Refusal(f"'{block.input['metric']}' is not a governed metric.")
        return apply_policy(self._clean(block.input, text), self.cat, self.vocab)


def make_translator(catalogue: Catalogue, vocab: Vocabulary, prefer: str = "auto"):
    if prefer == "claude" or (prefer == "auto" and ClaudeTranslator.available()):
        return ClaudeTranslator(catalogue, vocab)
    return RuleTranslator(catalogue, vocab)
