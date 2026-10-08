"""Command line of the agent.

    python -m agent metrics                          the governed metrics (from the dbt semantic layer)
    python -m agent ask "How much is the Le City bag in the USA?"
    python -m agent chat                             ask several questions in a row
    python -m agent eval                             run the evaluation set (agent/evals/questions.yml)
    python -m agent triage                           review every delivery the gate did not PASS
    python -m agent triage --dataset legacy_replay --out triage_legacy.md

Connection settings are the delivery gate's (QA_BACKEND, QA_SCHEMA_PREFIX, DATABRICKS_* ...).
Set ANTHROPIC_API_KEY to let Claude translate questions (--translator claude) and narrate (--llm).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from qa.backends import connect
from qa.config import Settings

from . import semantic, vocabulary
from .ask import Agent, render
from .translate import make_translator


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def build_agent(settings: Settings, prefer: str = "auto") -> Agent:
    cat = semantic.load()
    _log(f"Semantic layer: {len(cat.public_metrics())} governed metrics from {semantic.manifest_path()}")
    db = connect(settings)
    published = settings.schema("published")
    _log(f"Loading vocabulary from {published} ...")
    vocab = vocabulary.load(cat, db, published)
    translator = make_translator(cat, vocab, prefer)
    _log(f"Translator: {translator.name}")
    return Agent(cat, vocab, db, published, translator)


def cmd_metrics(args, settings) -> int:
    cat = semantic.load()
    for m in cat.public_metrics():
        model = cat.model_of(m)
        dims = [d for d in model.dimensions if d != model.time_dimension]
        print(f"{m.name}\n    {m.label} [{m.unit}] - {m.description}\n"
              f"    by: {', '.join(dims)}  |  time: {model.time_dimension}"
              f"{'  |  requires: ' + ', '.join(m.requires) if m.requires else ''}\n"
              f"    source: {model.alias}\n")
    return 0


def cmd_ask(args, settings) -> int:
    agent = build_agent(settings, args.translator)
    answer = agent.ask(" ".join(args.question), use_llm_narration=args.llm)
    print(render(answer, show_sql=not args.no_sql))
    return 0 if answer.ok else 2


def cmd_chat(args, settings) -> int:
    agent = build_agent(settings, args.translator)
    print("Ask a question about Balenciaga prices (empty line to quit).")
    while True:
        try:
            q = input("\n> ").strip()
        except EOFError:
            break
        if not q:
            break
        print(render(agent.ask(q, use_llm_narration=args.llm), show_sql=not args.no_sql))
    return 0


def cmd_eval(args, settings) -> int:
    from .evaluation import run_eval
    agent = build_agent(settings, args.translator)
    return run_eval(agent, verbose=args.verbose)


def cmd_triage(args, settings) -> int:
    from .triage import Triage, render_markdown, summarise_with_claude
    db = connect(settings)
    try:
        notes = Triage(db, settings).review(args.dataset, args.scope,
                                            date.fromisoformat(args.as_of) if args.as_of else None)
        if args.llm:
            for n in notes:
                n.summary = summarise_with_claude(n)
        text = f"# Delivery triage - dataset `{args.dataset}`\n\n" + render_markdown(notes)
        if args.out:
            Path(args.out).write_text(text)
            _log(f"Written to {args.out}")
        print(text)
    finally:
        db.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agent", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("metrics", help="list governed metrics")

    for name in ("ask", "chat", "eval"):
        p = sub.add_parser(name)
        p.add_argument("--translator", choices=["auto", "rules", "claude"], default="auto")
        if name == "ask":
            p.add_argument("question", nargs="+")
        if name in ("ask", "chat"):
            p.add_argument("--llm", action="store_true", help="let Claude phrase the answer (needs ANTHROPIC_API_KEY)")
            p.add_argument("--no-sql", action="store_true")
        if name == "eval":
            p.add_argument("-v", "--verbose", action="store_true")

    t = sub.add_parser("triage", help="explain the gate's WARN / BLOCK verdicts")
    t.add_argument("--dataset", default="marts", choices=["marts", "legacy_replay"])
    t.add_argument("--scope", choices=["micro", "macro"])
    t.add_argument("--as-of")
    t.add_argument("--out", help="also write the markdown note to this file")
    t.add_argument("--llm", action="store_true", help="add a Claude executive summary (needs ANTHROPIC_API_KEY)")

    args = parser.parse_args(argv)
    settings = Settings.from_env()
    return {"metrics": cmd_metrics, "ask": cmd_ask, "chat": cmd_chat, "eval": cmd_eval,
            "triage": cmd_triage}[args.command](args, settings)
