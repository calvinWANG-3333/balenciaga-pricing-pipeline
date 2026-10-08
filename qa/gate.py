"""The delivery gate: audit each delivery in the warehouse, record the verdict, release what passes.

    python -m qa.gate audit                       audit every unreleased delivery, release what passes
    python -m qa.gate audit --scope micro --as-of 2026-09-15 --dry-run
    python -m qa.gate audit --dataset legacy_replay   audit the replay of the old design (never released)
    python -m qa.gate release --scope micro --as-of 2026-09-15 --force --reason "..."
    python -m qa.gate status
    python -m qa.gate checks                      list the check catalogue

Write-audit-publish:
    WRITE    dbt build puts every delivery in the marts schema (BI cannot see it: BI reads `published`)
    AUDIT    this gate runs the check catalogue on the delivery, straight in the warehouse
    PUBLISH  if no blocking check fails, it appends a row to ops.delivery_releases; the published views
             expose the delivery from that moment on
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from . import catalog as cat
from .backends import Backend, connect
from .config import Settings
from .evaluate import Result, decide, evaluate
from .report import markdown_report, print_report

SCOPES = cat.SCOPES


# ------------------------------------------------------------------------------------------ helpers

def _sql_str(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(float(value))
    if isinstance(value, datetime):
        return f"timestamp'{value.strftime('%Y-%m-%d %H:%M:%S')}'"
    if isinstance(value, date):
        return f"date'{value.isoformat()}'"
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def _as_date(v) -> date:
    return v if isinstance(v, date) and not isinstance(v, datetime) else date.fromisoformat(str(v)[:10])


def load_deliveries(db: Backend, dataset: cat.Dataset, placeholders: dict[str, str]) -> list[cat.Delivery]:
    """The delivery calendar of each scope, each delivery linked to the two before it."""
    out: list[cat.Delivery] = []
    for scope in SCOPES:
        rows = db.query(dataset.deliveries[scope].format(**placeholders))
        dates = sorted(_as_date(r["as_of_date"]) for r in rows)
        for i, d in enumerate(dates):
            out.append(cat.Delivery(scope, d,
                                    dates[i - 1] if i >= 1 else None,
                                    dates[i - 2] if i >= 2 else None))
    return out


def released_deliveries(db: Backend, ops: str) -> set[tuple[str, date]]:
    rows = db.query(f"select distinct scope, as_of_date from {ops}.delivery_releases")
    return {(r["scope"], _as_date(r["as_of_date"])) for r in rows}


def measure(db: Backend, catalogue: cat.Catalogue, dataset: cat.Dataset, deliveries: list[cat.Delivery],
            placeholders: dict[str, str]) -> dict[str, list[dict]]:
    """Run every applicable check ONCE over the whole calendar: values for all deliveries."""
    measured: dict[str, list[dict]] = {}
    scopes_in_calendar = {d.scope for d in deliveries}
    for check in catalogue.checks:
        if dataset.name not in check.datasets or not (set(check.scopes) & scopes_in_calendar):
            continue
        sql = cat.render(check, dataset, deliveries, placeholders)
        try:
            measured[check.id] = db.query(sql)
        except Exception as exc:                     # a broken check must be visible, not silent
            raise SystemExit(f"Check {check.id} failed to run:\n{exc}\n\n--- SQL ---\n{sql}") from exc
    return measured


def judge(catalogue: cat.Catalogue, dataset: cat.Dataset, calendar: list[cat.Delivery],
          targets: list[cat.Delivery], released: set[tuple[str, date]], measured: dict[str, list[dict]],
          remeasure) -> tuple[dict[cat.Delivery, list[Result]], dict[cat.Delivery, str]]:
    """Evaluate the targeted deliveries, oldest first.

    Baseline rule: a delivery is compared with the last delivery that was ACCEPTED - released earlier, or
    passed earlier in this run - never with one that was blocked. Comparing with a blocked delivery would
    make the first correct delivery after an incident look wrong (prices "jumping back" to normal).
    When the accepted baseline differs from the calendar one, that delivery is measured again with the
    adjusted baseline (`remeasure`). Anomaly rules only learn from accepted deliveries, too.
    """
    target_keys = {(d.scope, d.as_of_date) for d in targets}
    verdicts: dict[cat.Delivery, list[Result]] = {}
    decisions: dict[cat.Delivery, str] = {}
    accepted: set[tuple[str, date]] = {k for k in released}

    for scope in SCOPES:
        for delivery in sorted((d for d in calendar if d.scope == scope), key=lambda d: d.as_of_date):
            key = (scope, delivery.as_of_date)
            if key not in target_keys:
                continue
            earlier = sorted(d.as_of_date for d in calendar
                             if d.scope == scope and d.as_of_date < delivery.as_of_date and (scope, d.as_of_date) in accepted)
            prev = earlier[-1] if earlier else None
            prev2 = earlier[-2] if len(earlier) >= 2 else None
            values, note = measured, ""
            if (prev, prev2) != (delivery.prev_date, delivery.prev2_date) and delivery.prev_date is not None:
                adjusted = cat.Delivery(scope, delivery.as_of_date, prev, prev2)
                values = remeasure(adjusted)
                skipped = sorted(set(filter(None, (delivery.prev_date, delivery.prev2_date))) - set(filter(None, (prev, prev2))))
                note = f" [baseline {prev}; skips non-accepted {', '.join(map(str, skipped))}]"

            results = []
            for check in catalogue.checks_for(dataset.name, scope):
                rows = [r for r in values.get(check.id, []) if r["scope"] == scope]
                hist_rows = [r for r in measured.get(check.id, []) if r["scope"] == scope]
                current = {str(r["subject"]): (None if r["observed"] is None else float(r["observed"]))
                           for r in rows if _as_date(r["as_of_date"]) == delivery.as_of_date}
                if not current:
                    results.append(evaluate(check, scope, delivery.as_of_date, "all", None))
                    continue
                for subject in sorted(current):
                    history = [None if r["observed"] is None else float(r["observed"])
                               for r in sorted(hist_rows, key=lambda r: _as_date(r["as_of_date"]))
                               if str(r["subject"]) == subject
                               and _as_date(r["as_of_date"]) < delivery.as_of_date
                               and (scope, _as_date(r["as_of_date"])) in accepted]
                    res = evaluate(check, scope, delivery.as_of_date, subject, current[subject], history)
                    if note and res.status != "skip":
                        res = Result(**{**res.__dict__, "message": res.message + note})
                    results.append(res)

            verdicts[delivery] = results
            decisions[delivery] = decide(results)
            if decisions[delivery] != "BLOCK":
                accepted.add(key)
    return verdicts, decisions


def persist_results(db: Backend, ops: str, run_id: str, checked_at: datetime, dataset: str,
                    verdicts: dict[cat.Delivery, list[Result]]) -> None:
    rows = [
        "(" + ", ".join(_sql_str(v) for v in (
            run_id, checked_at, dataset, r.scope, r.as_of_date, r.check_id, r.dimension, r.severity,
            r.subject, r.observed, r.warn_rule, r.fail_rule, r.status, r.message)) + ")"
        for results in verdicts.values() for r in results
    ]
    for i in range(0, len(rows), 200):
        db.execute(f"insert into {ops}.qa_check_results values\n" + ",\n".join(rows[i:i + 200]))


def persist_release(db: Backend, ops: str, scope: str, as_of_date: date, run_id: str, decision: str,
                    released_by: str, forced: bool = False, reason: str | None = None) -> None:
    values = (str(uuid.uuid4()), scope, as_of_date, run_id, decision, forced, reason,
              datetime.now(timezone.utc).replace(tzinfo=None), released_by)
    db.execute(f"insert into {ops}.delivery_releases values ({', '.join(_sql_str(v) for v in values)})")


# --------------------------------------------------------------------------------------- commands

def cmd_audit(args, settings: Settings) -> int:
    catalogue = cat.load()
    dataset = catalogue.datasets[args.dataset]
    ph = settings.placeholders()
    db = connect(settings)
    try:
        deliveries = load_deliveries(db, dataset, ph)
        scopes = SCOPES if args.scope == "all" else (args.scope,)
        deliveries = [d for d in deliveries if d.scope in scopes]

        released = released_deliveries(db, ph["ops"]) if dataset.publishable else set()
        if args.as_of:
            targets = [d for d in deliveries if d.as_of_date == date.fromisoformat(args.as_of)]
            if not targets:
                raise SystemExit(f"No {args.scope} delivery on {args.as_of} in {args.dataset}.")
        elif dataset.publishable and not args.all:
            targets = [d for d in deliveries if (d.scope, d.as_of_date) not in released]
        else:
            targets = deliveries
        if not targets:
            print("Nothing to audit: every delivery is already released.")
            return 0

        measured = measure(db, catalogue, dataset, deliveries, ph)

        def remeasure(adjusted: cat.Delivery) -> dict[str, list[dict]]:
            # a small calendar: the delivery and the two accepted deliveries it is compared with
            mini = [adjusted] + [cat.Delivery(adjusted.scope, d, None, None)
                                 for d in (adjusted.prev_date, adjusted.prev2_date) if d]
            return measure(db, catalogue, dataset, mini, ph)

        verdicts, decisions = judge(catalogue, dataset, deliveries, targets, released, measured, remeasure)

        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
        checked_at = datetime.now(timezone.utc).replace(tzinfo=None)
        print_report(args.dataset, run_id, verdicts, decisions, verbose=args.verbose)

        if args.report:
            Path(args.report).write_text(markdown_report(args.dataset, run_id, verdicts, decisions))
            print(f"\nReport written to {args.report}")

        if args.dry_run:
            print("\nDry run: nothing written.")
            return 0

        persist_results(db, ph["ops"], run_id, checked_at, args.dataset, verdicts)
        print(f"\nRecorded {sum(len(r) for r in verdicts.values())} check results (run {run_id}).")

        if not dataset.publishable:
            print(f"Dataset {args.dataset} is audit-only: nothing is released.")
            return 0

        n_released = 0
        for delivery, decision in sorted(decisions.items(), key=lambda kv: (kv[0].scope, kv[0].as_of_date)):
            if decision == "BLOCK" or args.no_publish or (delivery.scope, delivery.as_of_date) in released:
                continue
            persist_release(db, ph["ops"], delivery.scope, delivery.as_of_date, run_id, decision, settings.run_by)
            n_released += 1
        blocked = [d for d, x in decisions.items() if x == "BLOCK"]
        print(f"Released {n_released} deliver{'y' if n_released == 1 else 'ies'}; "
              f"{len(blocked)} blocked." + (" (--no-publish: nothing released)" if args.no_publish else ""))
        return 1 if blocked else 0
    finally:
        db.close()


def cmd_release(args, settings: Settings) -> int:
    """Manual release: a human overrides a BLOCK. Always needs a reason, always recorded as forced."""
    if not args.force or not args.reason:
        raise SystemExit("A manual release needs --force and --reason \"why it is safe\".")
    db = connect(settings)
    try:
        ops = settings.placeholders()["ops"]
        last = db.query(f"""
            select run_id from {ops}.qa_check_results
            where dataset = 'marts' and scope = '{args.scope}' and as_of_date = date'{args.as_of}'
            order by checked_at desc limit 1""")
        if not last:
            raise SystemExit("This delivery has never been audited: run `audit` first.")
        persist_release(db, ops, args.scope, date.fromisoformat(args.as_of), last[0]["run_id"],
                        "BLOCK", settings.run_by, forced=True, reason=args.reason)
        print(f"Forced release of {args.scope} {args.as_of} recorded (run {last[0]['run_id']}).")
        return 0
    finally:
        db.close()


def cmd_status(args, settings: Settings) -> int:
    db = connect(settings)
    try:
        ph = settings.placeholders()
        rows = db.query(f"""
            select scope, as_of_date, max_by(decision, released_at) as decision,
                   bool_or(is_forced) as forced, max(released_at) as released_at
            from {ph['ops']}.delivery_releases group by scope, as_of_date order by scope, as_of_date""")
        if not rows:
            print("No delivery released yet.")
        for r in rows:
            print(f"{r['scope']:<6} {_as_date(r['as_of_date'])}  {r['decision']:<5}"
                  f"{'  FORCED' if r['forced'] else ''}  released {r['released_at']}")
        return 0
    finally:
        db.close()


def cmd_checks(args, settings: Settings) -> int:
    catalogue = cat.load()
    for c in catalogue.checks:
        print(f"{c.id:<32} {c.dimension:<13} {c.severity:<6} {','.join(c.scopes):<12} {c.description}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m qa.gate", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    a = sub.add_parser("audit", help="audit deliveries and release those that pass")
    a.add_argument("--dataset", default="marts", choices=["marts", "legacy_replay"])
    a.add_argument("--scope", default="all", choices=["all", *SCOPES])
    a.add_argument("--as-of", help="audit only this delivery date (YYYY-MM-DD)")
    a.add_argument("--all", action="store_true", help="re-audit every delivery, released or not")
    a.add_argument("--dry-run", action="store_true", help="measure and report, write nothing")
    a.add_argument("--no-publish", action="store_true", help="record results but release nothing")
    a.add_argument("--report", help="also write a markdown report to this path")
    a.add_argument("-v", "--verbose", action="store_true", help="also list passing checks")

    r = sub.add_parser("release", help="force the release of a blocked delivery (human override)")
    r.add_argument("--scope", required=True, choices=SCOPES)
    r.add_argument("--as-of", required=True)
    r.add_argument("--force", action="store_true")
    r.add_argument("--reason")

    sub.add_parser("status", help="list released deliveries")
    sub.add_parser("checks", help="list the check catalogue")

    args = parser.parse_args(argv)
    settings = Settings.from_env()
    return {"audit": cmd_audit, "release": cmd_release, "status": cmd_status, "checks": cmd_checks}[args.command](args, settings)


if __name__ == "__main__":
    sys.exit(main())
