"""The ask pipeline: question -> intent -> guardrails -> SQL -> rows -> answer.

    translate   (rules or Claude)   what is being asked, as a structured form
    guardrails  (deterministic)     may this be answered? if not: refuse, with the reason
    compile     (deterministic)     the SQL, from the semantic layer definition
    execute     (warehouse)         on the published layer only (released deliveries)
    narrate     (template | Claude) the answer, with its provenance
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import guardrails
from .compiler import compile_sql
from .intent import Intent, Refusal
from .narrate import narrate, narrate_with_claude
from .semantic import Catalogue
from .vocabulary import Vocabulary


@dataclass
class Answer:
    question: str
    translator: str
    intent: Intent | None = None
    refusal: Refusal | None = None
    sql: str | None = None
    rows: list[dict] = field(default_factory=list)
    text: str = ""
    llm_text: str | None = None
    provenance: str = ""

    @property
    def ok(self) -> bool:
        return self.refusal is None


class Agent:
    def __init__(self, catalogue: Catalogue, vocab: Vocabulary, db, published_schema: str, translator):
        self.cat, self.vocab, self.db = catalogue, vocab, db
        self.schema = published_schema
        self.translator = translator

    def ask(self, question: str, use_llm_narration: bool = False) -> Answer:
        answer = Answer(question=question, translator=self.translator.name)
        result = self.translator.translate(question)
        if isinstance(result, Refusal):
            answer.refusal = result
            return answer
        answer.intent = result
        refusal = guardrails.check(result, self.cat, self.vocab)
        if refusal:
            answer.refusal = refusal
            return answer

        answer.sql = compile_sql(result, self.cat, self.schema)
        answer.rows = self.db.query(answer.sql)
        answer.text = narrate(result, answer.rows, self.cat, self.vocab)
        metric = self.cat.metrics[result.metric]
        model = self.cat.model_of(metric)
        answer.provenance = (f"Metric `{metric.name}` (dbt semantic layer, semantic model `{model.name}`) "
                             f"on `{self.schema}.{model.alias}` - released deliveries only.")
        if use_llm_narration:
            answer.llm_text = narrate_with_claude(question, answer.text, answer.rows, metric)
        return answer


def render(answer: Answer, show_sql: bool = True) -> str:
    """Plain-text rendering for the terminal."""
    out = [f"Q: {answer.question}", f"   (translator: {answer.translator})"]
    if answer.refusal:
        out += ["", f"I can't answer that: {answer.refusal.reason}"]
        if answer.refusal.suggestion:
            out.append(answer.refusal.suggestion)
        return "\n".join(out)
    i = answer.intent
    understood = f"metric={i.metric}"
    if i.filters:
        understood += f", filters={i.filters}"
    if i.group_by or i.group_by_time:
        understood += f", by={(['time'] if i.group_by_time else []) + i.group_by}"
    understood += f", period={i.time_label}"
    out += [f"   understood: {understood}"]
    out += [f"   note: {n}" for n in i.notes]
    out += ["", answer.llm_text or answer.text]
    if answer.llm_text:
        out += ["", "(deterministic version)", answer.text]
    out += ["", answer.provenance]
    if show_sql:
        out += ["", "SQL:", answer.sql]
    return "\n".join(out)
