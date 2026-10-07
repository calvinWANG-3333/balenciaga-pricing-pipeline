"""
Synthetic Balenciaga crawl generator - command-line entry point.

    python -m generator.generate --seed 42 --products 2000 --out data

Writes
    data/raw/balenciaga/ALT_<date>_<epoch_ms>_balenciaga.ndjson     <- what "the crawler" delivers
    data/_truth/product_master.csv     ground-truth catalogue (never loaded as a source)
    data/_truth/price_changes.csv      every planted price change (individual + September increase)
    data/_truth/hero_products.csv      the 8 hero SKUs used to seed the Micro pointers
    data/_truth/defect_manifest.csv    ANSWER KEY: every planted row-level defect, with file + line
    data/_truth/batch_manifest.csv     every delivered file + batch-level defects (F family)

Same seed -> byte-identical output (checked by generator/validate.py --determinism).
"""

import argparse
import csv
import gzip
import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config
from .catalog import build_product_master
from .defects import DefectInjector
from .pricing import local_price
from .render import render_row

UTC = timezone.utc
CRAWL_ORDER = ["ARE", "AUS", "CAN", "CHN", "FRA", "GBR", "HKG", "JPN", "KOR", "MEX", "MYS", "SAU", "SGP",
               "THA", "TWN", "USA"]

# Batch-level scenarios (family F + chunk-level B/E defects). Keyed by crawl date.
SCENARIOS = {
    "2026-08-10": {"seconds_timestamps": "HKG", "duplicate_file": True},
    "2026-08-17": {"partial_crawl": {"KOR": 0.45, "HKG": 0.45}, "geo_redirect": ("USA", 60)},
    "2026-09-14": {"missing_market": "JPN"},
}
STALE_REIMPORT = {"source_crawl": "2026-08-31", "delivered_as": "2026-09-15"}


def epoch_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def plan_price_changes(rng, products, crawl_dates):
    """Return {sku: [(week_index, multiplier), ...]} plus a list of change records."""
    changes, records = {}, []
    for w in range(1, len(crawl_dates)):
        for p in products:
            if p.is_hero and p.hero_id not in ("HERO-02", "HERO-06"):
                continue           # most heroes only move with the September event
            if rng.random() < config.WEEKLY_INDIVIDUAL_CHANGE_SHARE or (
                    p.hero_id == "HERO-02" and w == 4) or (p.hero_id == "HERO-06" and w == 10):
                pct = rng.uniform(0.05, 0.15) * (1 if rng.random() < 0.7 else -1)
                changes.setdefault(p.sku, []).append((w, 1 + pct))
                records.append(dict(sku=p.sku, effective_crawl=crawl_dates[w].isoformat(),
                                    change_type="individual", market="ALL", pct=round(pct, 4)))
    ev = config.SEPTEMBER_INCREASE
    in_event = set()
    for p in products:
        if p.family in ev["families"] and (p.is_hero or rng.random() < ev["share_of_products"]):
            in_event.add(p.sku)
            for m in p.markets:
                records.append(dict(sku=p.sku, effective_crawl=ev["effective"].isoformat(),
                                    change_type="september_increase", market=m,
                                    pct=ev["pct_by_market"].get(m, ev["default_pct"])))
    return changes, in_event, records


def price_at(p, market, week, crawl_date, changes, in_event):
    mult = 1.0
    for w, m in changes.get(p.sku, []):
        if w <= week:
            mult *= m
    ev = config.SEPTEMBER_INCREASE
    if p.sku in in_event and crawl_date >= ev["effective"]:
        mult *= 1 + ev["pct_by_market"].get(market, ev["default_pct"])
    return local_price(p.eur_price * mult, p.markets[market], market)


def build_batch(rng, products, week, crawl_date, markets, changes, in_event):
    start = datetime(crawl_date.year, crawl_date.month, crawl_date.day, 1, 0, tzinfo=UTC) + \
        timedelta(minutes=rng.randint(0, 50))
    rows, t = [], start
    for m in [m for m in CRAWL_ORDER if m in markets]:
        t += timedelta(minutes=rng.randint(2, 9), milliseconds=rng.randint(0, 999))
        i = 0
        for p in products:
            if m not in p.markets or p.launch_week > week or (p.end_week is not None and week >= p.end_week):
                continue
            if i % 25 == 0:
                t += timedelta(seconds=rng.randint(2, 9), milliseconds=rng.randint(0, 999))
            rows.append(render_row(p, m, week, price_at(p, m, week, crawl_date, changes, in_event), epoch_ms(t)))
            i += 1
    return rows, t


def write_ndjson(path: Path, rows, gz: bool):
    data = "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in rows).encode("utf-8")
    if gz:
        path = path.with_suffix(path.suffix + ".gz")
        with gzip.GzipFile(path, "wb", mtime=0) as f:
            f.write(data)
    else:
        path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--products", type=int, default=2000)
    ap.add_argument("--out", default="data")
    ap.add_argument("--gzip", action="store_true", help="write .ndjson.gz instead of .ndjson")
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    out = Path(args.out)
    raw_dir, truth_dir = out / "raw" / "balenciaga", out / "_truth"
    raw_dir.mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)

    crawl_dates = [config.FIRST_CRAWL + timedelta(weeks=w) for w in range(config.N_WEEKS)]
    products = build_product_master(rng, args.products, config.N_WEEKS)
    by_sku = {p.sku: p for p in products}
    changes, in_event, change_records = plan_price_changes(rng, products, crawl_dates)
    inj = DefectInjector(rng)

    deliveries = []        # (file_name, rows, batch_type, crawl_date, note)
    stash = {}             # crawl date iso -> (rows, file_name) for re-delivery scenarios
    for week, cd in enumerate(crawl_dates):
        iso = cd.isoformat()
        extended = cd in config.EXTENDED_CRAWLS
        markets = set(config.ALL_MARKETS if extended else config.WEEKLY_MARKETS)
        sc = SCENARIOS.get(iso, {})
        if "missing_market" in sc:
            markets.discard(sc["missing_market"])
        rows, t_end = build_batch(rng, products, week, cd, markets, changes, in_event)
        file_ms = epoch_ms(t_end + timedelta(hours=rng.randint(3, 8), minutes=rng.randint(0, 59)))
        fname = f"ALT_{iso}_{file_ms}_balenciaga.ndjson"

        # ---- batch / chunk level scenarios ----
        if "partial_crawl" in sc:
            for m, keep in sc["partial_crawl"].items():
                m_rows = [r for r in rows if r["market"] == m]
                cut = set(map(id, m_rows[int(len(m_rows) * keep):]))
                rows = [r for r in rows if id(r) not in cut]
                inj.batch_record(fname, "F03_partial_crawl", "warn",
                                 f"{m}: crawler stopped after {keep:.0%} of the catalogue "
                                 f"({int(len(m_rows) * keep)} of {len(m_rows)} rows delivered)", m)
        if "missing_market" in sc:
            inj.batch_record(fname, "F04_missing_market", "warn",
                             f"{sc['missing_market']} absent from a weekly batch", sc["missing_market"])

        # ---- row-level defects, then chunk-level ones ----
        rows = inj.apply_row_defects(rows)
        if "geo_redirect" in sc:
            m, n = sc["geo_redirect"]
            inj.geo_redirect(rows, m, n, lambda r: by_sku[r["skus"][0]].eur_price
                             if r["skus"] and r["skus"][0] in by_sku else None)
        if "seconds_timestamps" in sc:
            inj.seconds_timestamps(rows, sc["seconds_timestamps"])
        rows = inj.non_product_rows(rows, epoch_ms(t_end))

        batch_type = "extended_monthly" if extended else "weekly"
        deliveries.append((fname, rows, batch_type, iso, ""))
        stash[iso] = (rows, fname)

        if sc.get("duplicate_file"):
            dup_name = fname.replace(".ndjson", " (1).ndjson")
            deliveries.append((dup_name, rows, "duplicate_file", iso, f"byte-identical copy of {fname}"))
            inj.batch_record(dup_name, "F01_duplicate_file", "block",
                             f"byte-identical re-delivery of {fname} (same sha256)")

        # F02 - the incident: an OLD crawl re-delivered under a NEW date (the day after the 09-14 crawl)
        if iso == "2026-09-14":
            src_rows, src_name = stash[STALE_REIMPORT["source_crawl"]]
            export_ms = epoch_ms(datetime(2026, 9, 15, 9, 12, tzinfo=UTC))
            stale = []
            for r in src_rows:
                r2 = json.loads(json.dumps(r))
                if isinstance(r2.get("updatedAt"), int) and r2["updatedAt"] > 10**12:
                    r2["updatedAt"] = export_ms              # export touched updatedAt, crawl date unchanged
                stale.append(r2)
            stale_name = f"ALT_{STALE_REIMPORT['delivered_as']}_{export_ms}_balenciaga.ndjson"
            deliveries.append((stale_name, stale, "stale_reimport", STALE_REIMPORT["source_crawl"],
                               f"content of {src_name} re-exported on 2026-09-15"))
            inj.batch_record(stale_name, "F02_stale_reimport", "block",
                             f"file dated 2026-09-15 but every createdAt is from the 2026-08-31 extended crawl "
                             f"({src_name}); loading it as 'latest' would roll prices back two weeks")

    # ---- write files ----
    line_of = {}
    batch_rows = []
    for fname, rows, btype, iso, note in deliveries:
        path, sha = write_ndjson(raw_dir / fname, rows, args.gzip)
        if btype not in ("duplicate_file", "stale_reimport"):
            for i, r in enumerate(rows, start=1):
                line_of[id(r)] = (path.name, i)
        markets = sorted({r.get("market") or r["source"].split("_")[-1] for r in rows})
        batch_rows.append(dict(file_name=path.name, crawl_date=iso, batch_type=btype, n_rows=len(rows),
                               n_markets=len(markets), markets="|".join(markets), sha256=sha, note=note))

    with open(truth_dir / "defect_manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file_name", "line_number", "object_id", "defect_code", "defect_family", "field",
                    "clean_value", "dirty_value", "expected_handling", "note"])
        for rec in inj.records:
            fname, line = line_of[id(rec["row"])]
            w.writerow([fname, line, rec["object_id"], rec["defect_code"], rec["defect_family"], rec["field"],
                        rec["clean_value"], rec["dirty_value"], rec["expected_handling"], rec["note"]])
        for rec in inj.batch_records:
            fname = rec["file_name"] + (".gz" if args.gzip else "")
            w.writerow([fname, "", "", rec["defect_code"], "F", rec["market"], "", rec["detail"],
                        rec["expected_handling"], ""])

    with open(truth_dir / "batch_manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(batch_rows[0]))
        w.writeheader()
        w.writerows(batch_rows)

    with open(truth_dir / "product_master.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sku", "style_code", "name", "macro_tag", "gender", "family", "color", "color_id",
                    "collection", "eur_reference_price", "launch_crawl", "end_crawl", "markets", "hero_id"])
        for p in products:
            w.writerow([p.sku, p.style, p.name, p.macro_tag, p.gender, p.family, p.color, p.color_id,
                        p.collection, p.eur_price, crawl_dates[p.launch_week].isoformat(),
                        crawl_dates[p.end_week].isoformat() if p.end_week is not None else "",
                        "|".join(sorted(p.markets)), p.hero_id or ""])

    with open(truth_dir / "hero_products.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["hero_id", "sku", "name", "family", "macro_tag"])
        for p in products:
            if p.is_hero:
                w.writerow([p.hero_id, p.sku, p.name, p.family, p.macro_tag])

    with open(truth_dir / "price_changes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["sku", "effective_crawl", "change_type", "market", "pct"])
        w.writeheader()
        w.writerows(change_records)

    n_rows = sum(b["n_rows"] for b in batch_rows)
    print(f"products={len(products)}  files={len(batch_rows)}  rows={n_rows:,}  "
          f"row_defects={len(inj.records):,}  batch_defects={len(inj.batch_records)}  -> {out.resolve()}")


if __name__ == "__main__":
    main()
