"""The structured question: the ONLY thing a translator (rules or LLM) is allowed to produce.

A translator never writes SQL. It fills this form; guardrails check it; a deterministic compiler
turns it into SQL. Whatever the LLM gets wrong, it can only get wrong inside this form.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date


@dataclass
class Intent:
    metric: str | None
    group_by: list[str] = field(default_factory=list)
    filters: dict[str, list[str]] = field(default_factory=dict)   # dimension -> allowed values
    time_start: date | None = None                                # inclusive
    time_end: date | None = None                                  # inclusive
    time_label: str | None = None                                 # how the period was understood
    group_by_time: bool = False                                   # "by month", "over time"
    order: str | None = None                                      # desc | asc (sort by the metric)
    notes: list[str] = field(default_factory=list)                # assumptions made, shown to the user

    def to_dict(self) -> dict:
        d = asdict(self)
        d["time_start"] = self.time_start.isoformat() if self.time_start else None
        d["time_end"] = self.time_end.isoformat() if self.time_end else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Intent":
        def as_date(v):
            return date.fromisoformat(v) if v else None
        return cls(
            metric=d.get("metric"),
            group_by=list(d.get("group_by") or []),
            filters={k: list(v) for k, v in (d.get("filters") or {}).items()},
            time_start=as_date(d.get("time_start")),
            time_end=as_date(d.get("time_end")),
            time_label=d.get("time_label"),
            group_by_time=bool(d.get("group_by_time")),
            order=d.get("order"),
            notes=list(d.get("notes") or []),
        )


@dataclass
class Refusal:
    """A deterministic 'no', with the reason and what the user can ask instead."""
    reason: str
    suggestion: str = ""
