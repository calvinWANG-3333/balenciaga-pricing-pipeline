"""Triage agent: turns the delivery gate's verdicts into a review note an analyst can act on.

The gate says WHAT failed (check results in ops.qa_check_results). Triage asks WHY, the way an analyst
would: for each check that did not pass it runs a few targeted drill-down queries (which crawl was
served, which file was partial, which reading was quarantined and for what reason, whether a price move
is shared by every market...), then writes:

    findings        what happened, with the evidence rows
    likely cause    the upstream reason, when the evidence shows it
    action          hold / release with a client note / verify on the website
    client note     a draft sentence for the client, for WARN deliveries

Deterministic by default (the explanations are rules over evidence). With ANTHROPIC_API_KEY set, Claude
can add an executive summary on top - it receives the findings, never the raw data, never the decision.
"""

from __future__ import annotations

import os
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

import yaml

from qa.catalog import CATALOGUE_PATH


@dataclass
class Finding:
    check_id: str
    status: str                          # warn | fail
    title: str
    detail: str
    evidence: list[dict] = field(default_factory=list)
    likely_cause: str = ""
    client_note: str = ""


@dataclass
class TriageNote:
    dataset: str
    scope: str
    as_of_date: date
    decision: str
    is_published: bool
    findings: list[Finding]
    action: str
    client_note: str
    summary: str | None = None


def _d(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def _pct(x) -> str:
    return "n/a" if x is None else f"{float(x):+.1%}"


class Triage:
    def __init__(self, db, settings):
        self.db = db
        self.marts = settings.schema("marts")
        self.quality = settings.schema("quality")
        self.ops = settings.schema("ops")
        self.intermediate = settings.schema("intermediate")
        self.check_docs = {c["id"]: " ".join(c["description"].split())
                           for c in yaml.safe_load(CATALOGUE_PATH.read_text())["checks"]}

    # ------------------------------------------------------------------------------- data access
    def _catalogue(self, dataset: str) -> str:
        if dataset == "legacy_replay":
            return (f"(select as_of_date, market, object_id, sku, legacy_crawl_date as served_crawl_date, "
                    f"price_local from {self.intermediate}.int_legacy__catalogue_replayed)")
        return (f"(select as_of_date, market, object_id, sku, presence_crawl_date as served_crawl_date, "
                f"price_local from {self.marts}.fct_catalogue_as_of)")

    def deliveries_to_review(self, dataset: str, scope: str | None, as_of: date | None) -> list[dict]:
        where = [f"dataset = '{dataset}'", "gate_decision != 'PASS'"]
        if scope:
            where.append(f"scope = '{scope}'")
        if as_of:
            where.append(f"as_of_date = date'{as_of.isoformat()}'")
        return self.db.query(f"select * from {self.marts}.mart_data_health__deliveries "
                             f"where {' and '.join(where)} order by scope, as_of_date")

    def results(self, run_id: str, dataset: str, scope: str, as_of: date) -> list[dict]:
        return self.db.query(f"""
            select check_id, dimension, severity, subject, observed, status, message
            from {self.ops}.qa_check_results
            where run_id = '{run_id}' and dataset = '{dataset}' and scope = '{scope}'
              and as_of_date = date'{as_of.isoformat()}' and status in ('warn', 'fail')
            order by check_id, subject""")

    def previous_delivery(self, scope: str, as_of: date) -> date | None:
        col, table = (("delivery_date", "mart_micro__hero_prices_weekly") if scope == "micro"
                      else ("as_of_date", "mart_macro__category_monthly"))
        rows = self.db.query(f"select max({col}) as d from {self.marts}.{table} where {col} < date'{as_of.isoformat()}'")
        return _d(rows[0]["d"]) if rows and rows[0]["d"] else None

    # ------------------------------------------------------------------------------- explainers
    def explain_stale(self, dataset, scope, as_of, rows) -> Finding:
        markets = sorted({r["subject"] for r in rows})
        evidence = []
        for m in markets:
            served = self.db.query(f"select max(served_crawl_date) as d from {self._catalogue(dataset)} c "
                                   f"where as_of_date = date'{as_of}' and market = '{m}'")[0]["d"]
            files = self.db.query(f"""
                select delivered_file_name, content_crawl_date, file_status,
                       array_contains(missing_markets, '{m}') as market_missing,
                       array_contains(partial_markets, '{m}') as market_partial,
                       is_duplicate_content, is_stale_content
                from {self.quality}.qa_raw__file_profile
                where content_crawl_date > date'{_d(served) if served else as_of - timedelta(days=30)}'
                  and content_crawl_date <= date'{as_of}'
                   or (file_crawl_date > date'{as_of - timedelta(days=10)}' and file_crawl_date <= date'{as_of}')
                order by content_crawl_date""")
            # the new design ignores blocked files, so for it only missing / partial markets matter;
            # the old design imported everything, so a blocked file is often the cause there
            relevant = [f for f in files if f["market_missing"] or f["market_partial"]
                        or (dataset == "legacy_replay" and (f["is_duplicate_content"] or f["is_stale_content"]))]
            for f in relevant or [{"delivered_file_name": "(no newer file for this market)"}]:
                problem = ("market missing from the file" if f.get("market_missing") else
                           "market only partially crawled" if f.get("market_partial") else
                           "stale re-export (old content, new name)" if f.get("is_stale_content") else
                           "duplicate of an earlier file" if f.get("is_duplicate_content") else "-")
                evidence.append({"market": m, "crawl served": str(served),
                                 "file": f.get("delivered_file_name"),
                                 "crawl in file": str(f.get("content_crawl_date", "")),
                                 "problem": problem})
        ages = ", ".join(f"{r['subject']} {int(float(r['observed']))} days" for r in rows)
        if dataset == "legacy_replay":
            cause = ("The old design served whatever file was imported last. The newest import was not the "
                     "newest crawl (see 'problem'), so markets were served old data.")
        else:
            cause = ("This period's crawl for these markets was missing or incomplete (see 'problem'), so the "
                     "point-in-time catalogue correctly fell back to the latest complete crawl.")
        return Finding("served_crawl_age_days", rows[0]["status"], "Stale crawl served",
                       f"Served crawl age: {ages}.", evidence, cause,
                       client_note=f"Prices for {', '.join(markets)} reflect the crawl of "
                                   f"{evidence[0]['crawl served'] if evidence else 'an earlier date'}; "
                                   "this week's crawl for these markets was incomplete.")

    def explain_carried_forward(self, dataset, scope, as_of, rows) -> Finding:
        cells = self.db.query(f"""
            select pointer_id, product_label, market, sku, price_local, price_crawl_date, crawl_date_used
            from {self.marts}.mart_micro__hero_prices_weekly
            where delivery_date = date'{as_of}' and is_price_carried_forward
            order by pointer_id, market""")
        evidence = []
        for c in cells:
            q = self.db.query(f"""
                select concat_ws(', ', quarantine_reasons) as reasons,
                       original_price_raw, original_currency_raw, expected_currency
                from {self.quality}.qa_raw__quarantined_lines
                where sku = '{c['sku']}' and market = '{c['market']}' and file_crawl_date = date'{c['crawl_date_used']}'
                limit 1""")
            reason = q[0] if q else {}
            evidence.append({"hero": c["pointer_id"], "market": c["market"], "price shown": str(c["price_local"]),
                             "from crawl": str(c["price_crawl_date"]),
                             "this week's reading": (f"quarantined: {reason.get('reasons')} "
                                                     f"(raw {reason.get('original_price_raw')} {reason.get('original_currency_raw')})")
                             if reason else "not found in quarantine (check classification)"})
        reasons = sorted({e["this week's reading"].split(" (raw")[0] for e in evidence})
        return Finding("hero_carried_forward", rows[0]["status"], "Prices carried forward",
                       f"{len(cells)} hero cell(s) show last week's price.", evidence,
                       "This week's reading was rejected by the staging rules: " + "; ".join(reasons) + ".",
                       client_note=f"{len(cells)} price(s) repeat last week's value because this week's "
                                   "reading could not be validated.")

    def explain_large_moves(self, dataset, scope, as_of, rows) -> Finding:
        moves = self.db.query(f"""
            select product_label, market, previous_price_local, price_local, change_vs_previous_pct
            from {self.marts}.mart_micro__hero_prices_weekly
            where delivery_date = date'{as_of}' and abs(change_vs_previous_pct) > 0.10
            order by product_label, market""")
        by_product: dict[str, list[float]] = {}
        for m in moves:
            by_product.setdefault(m["product_label"], []).append(float(m["change_vs_previous_pct"]))
        verdicts = []
        for product, changes in by_product.items():
            spread = statistics.pstdev(changes) if len(changes) > 1 else 0.0
            if len(changes) >= 3 and spread < 0.02:
                verdicts.append(f"{product}: {_pct(statistics.fmean(changes))} in {len(changes)} markets, "
                                f"almost identical everywhere -> a coordinated price change (real).")
            else:
                verdicts.append(f"{product}: {len(changes)} market(s), changes differ -> verify on the brand "
                                "website (candidate for the Browser-Use verification agent).")
        evidence = [{"hero": m["product_label"], "market": m["market"],
                     "before": str(m["previous_price_local"]), "after": str(m["price_local"]),
                     "change": _pct(m["change_vs_previous_pct"])} for m in moves]
        return Finding("hero_large_moves", rows[0]["status"], "Large hero price moves (> 10%)",
                       f"{len(moves)} hero cell(s) moved more than 10%.", evidence, " ".join(verdicts),
                       client_note="; ".join(f"{p} changed by {_pct(statistics.fmean(c))} "
                                             f"in {len(c)} market(s)" for p, c in by_product.items()) + ".")

    def explain_change_anomaly(self, dataset, scope, as_of, rows) -> Finding:
        prev = self.previous_delivery(scope, as_of)
        evidence = self.db.query(f"""
            with cur as (select * from {self._catalogue(dataset)} c where as_of_date = date'{as_of}' and price_local is not null),
                 prv as (select * from {self._catalogue(dataset)} c where as_of_date = date'{prev}' and price_local is not null)
            select coalesce(p.macro_category, 'out of Macro scope') as category,
                   count(*) as products,
                   round(avg(case when cur.price_local != prv.price_local then 1.0 else 0.0 end), 3) as share_changed,
                   round(avg(case when cur.price_local != prv.price_local
                                  then cur.price_local / prv.price_local - 1 end), 4) as avg_change_when_changed,
                   count(distinct case when cur.price_local != prv.price_local then cur.market end) as markets_with_changes
            from cur
            inner join prv on prv.object_id = cur.object_id
            left join {self.marts}.dim_product p on p.sku = cur.sku
            group by 1 order by share_changed desc""") if prev else []
        movers = [e for e in evidence if float(e["share_changed"] or 0) > 0.2]
        if movers and all(float(e["avg_change_when_changed"] or 0) > 0 for e in movers):
            cause = (f"Concentrated in {', '.join(e['category'] for e in movers)} "
                     f"({', '.join(_pct(e['avg_change_when_changed']) for e in movers)} on average), upward, "
                     "in many markets at once: the signature of a brand-wide price campaign. Real event.")
            note = (f"The brand raised prices on {', '.join(e['category'] for e in movers)} "
                    f"(about {_pct(statistics.fmean(float(e['avg_change_when_changed']) for e in movers))}).")
        else:
            cause = "Changes are not concentrated in one direction or category: investigate before releasing."
            note = ""
        for e in evidence:
            e["share_changed"] = _pct(e["share_changed"]).lstrip("+")
            e["avg_change_when_changed"] = _pct(e["avg_change_when_changed"])
        return Finding("price_change_share_anomaly", rows[0]["status"], "Unusually many price changes",
                       rows[0]["message"], evidence, cause, client_note=note)

    def explain_reversion(self, dataset, scope, as_of, rows) -> Finding:
        prev = self.previous_delivery(scope, as_of)
        prev2 = self.previous_delivery(scope, prev) if prev else None
        evidence = self.db.query(f"""
            select market,
                   max(case when as_of_date = date'{as_of}' then served_crawl_date end) as crawl_now,
                   max(case when as_of_date = date'{prev}' then served_crawl_date end) as crawl_previous,
                   max(case when as_of_date = date'{prev2}' then served_crawl_date end) as crawl_two_before
            from {self._catalogue(dataset)} c
            where as_of_date in (date'{as_of}', date'{prev}', date'{prev2}')
            group by market order by market""") if prev2 else []
        subjects = {r["subject"] for r in rows}
        evidence = [e for e in evidence if e["market"] in subjects]
        older = [e for e in evidence if e["crawl_now"] and e["crawl_previous"] and _d(e["crawl_now"]) < _d(e["crawl_previous"])]
        cause = (f"In {len(older)} market(s) the crawl served now is OLDER than the one served last time "
                 "(see evidence): an old crawl was served again, so prices went back to their earlier values."
                 if older else "Prices returned to an earlier value; check which crawl was served.")
        return Finding(rows[0]["check_id"], rows[0]["status"],
                       "Prices went back to an older state (and broadly decreased)"
                       if rows[0]["check_id"] == "price_reversion_share" else "Broad price decrease",
                       "; ".join(f"{r['subject']}: {_pct(r['observed']).lstrip('+')}" for r in rows),
                       [{k: str(v) for k, v in e.items()} for e in evidence], cause)

    def explain_count_drop(self, dataset, scope, as_of, rows) -> Finding:
        f = self.explain_stale(dataset, scope, as_of, rows)
        f.check_id, f.title = "product_count_change", "Products disappeared from the catalogue"
        f.detail = "; ".join(f"{r['subject']}: {_pct(r['observed'])}" for r in rows)
        if dataset == "legacy_replay":
            f.likely_cause = ("The old design overwrote the catalogue with the last imported file, here a partial "
                              "crawl (see 'problem'): every product missing from it disappeared.")
        return f

    def explain_generic(self, dataset, scope, as_of, rows) -> Finding:
        cid = rows[0]["check_id"]
        return Finding(cid, rows[0]["status"], cid.replace("_", " ").capitalize(),
                       "; ".join(r["message"] for r in rows), [], self.check_docs.get(cid, ""))

    EXPLAINERS = {
        "served_crawl_age_days": "explain_stale",
        "hero_carried_forward": "explain_carried_forward",
        "hero_large_moves": "explain_large_moves",
        "price_change_share_anomaly": "explain_change_anomaly",
        "price_reversion_share": "explain_reversion",
        "price_decrease_share": "explain_reversion",
        "product_count_change": "explain_count_drop",
    }

    # ------------------------------------------------------------------------------------ main
    def review(self, dataset: str = "marts", scope: str | None = None, as_of: date | None = None) -> list[TriageNote]:
        notes = []
        for d in self.deliveries_to_review(dataset, scope, as_of):
            day = _d(d["as_of_date"])
            results = self.results(d["run_id"], dataset, d["scope"], day)
            by_check: dict[str, list[dict]] = {}
            for r in results:
                by_check.setdefault(r["check_id"], []).append(r)
            findings = []
            for cid, rows in by_check.items():
                if cid == "hero_stale_share" and "served_crawl_age_days" in by_check:
                    continue                      # same cause, explained once (hero view of the stale crawl)
                if cid == "price_decrease_share" and "price_reversion_share" in by_check:
                    continue                      # the decrease IS the reversion: one cause, one finding
                method = getattr(self, self.EXPLAINERS.get(cid, "explain_generic"))
                findings.append(method(dataset, d["scope"], day, rows))
            findings.sort(key=lambda f: (f.status != "fail", f.check_id))
            if d["gate_decision"] == "BLOCK":
                action = ("HOLD - do not release. Fix the cause upstream and re-audit "
                          f"(`python -m qa.gate audit --as-of {day}`). If the data is right after all, a human can "
                          f"release it with `python -m qa.gate release --scope {d['scope']} --as-of {day} --force --reason \"...\"`.")
                client = ""
            else:
                action = "RELEASE WITH A NOTE - the data is correct; the warnings describe real events or known fallbacks."
                client = " ".join(f.client_note for f in findings if f.client_note)
            notes.append(TriageNote(dataset, d["scope"], day, d["gate_decision"], bool(d["is_published"]),
                                    findings, action, client))
        return notes


def summarise_with_claude(note: TriageNote) -> str | None:
    """Optional executive summary. Claude sees the findings (already evidenced), not the raw tables."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        return None
    text = render_markdown([note])
    msg = anthropic.Anthropic().messages.create(
        model=os.environ.get("AGENT_MODEL", "claude-sonnet-4-5"), max_tokens=300,
        system="Summarise this data-quality review for a delivery manager in 3 sentences. Use only facts stated in it.",
        messages=[{"role": "user", "content": text}])
    return "".join(getattr(b, "text", "") for b in msg.content).strip() or None


def _table(rows: list[dict]) -> list[str]:
    if not rows:
        return []
    keys = list(rows[0])
    out = ["| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
    out += ["| " + " | ".join(str(r.get(k, "")) for k in keys) + " |" for r in rows[:40]]
    if len(rows) > 40:
        out.append(f"| ... {len(rows) - 40} more | " + " | " * (len(keys) - 1))
    return out


def render_markdown(notes: list[TriageNote]) -> str:
    if not notes:
        return "Nothing to triage: every audited delivery passed the gate.\n"
    out = []
    for n in notes:
        out += [f"## {n.scope} {n.as_of_date} - {n.decision}"
                + (" (published)" if n.is_published else " (not published)") + f" - dataset `{n.dataset}`", ""]
        if n.summary:
            out += [f"> {n.summary}", ""]
        out += [f"**Action:** {n.action}", ""]
        for f in n.findings:
            out += [f"### {f.status.upper()} - {f.title} (`{f.check_id}`)", "", f.detail, ""]
            if f.likely_cause:
                out += [f"**Likely cause:** {f.likely_cause}", ""]
            out += _table(f.evidence) + ([""] if f.evidence else [])
        if n.client_note:
            out += [f"**Draft client note:** {n.client_note}", ""]
    return "\n".join(out)
