"""
Self-check for the generated data - run it after every generation.

    python -m generator.validate --out data                 # realism + answer-key checks
    python -m generator.validate --out data --determinism   # also prove same seed -> same bytes

What it proves (each check prints PASS / FAIL):
  1. Schema parity     every row has the real crawler's 19 top-level keys, in the real order
                       (except rows where a schema defect was planted on purpose)
  2. Price realism     every CLEAN price sits inside the envelope measured on real data for its
                       category x market; EUR reference prices never leave the real min-max
  3. Answer key        every manifest entry points at a line that really contains that defect
  4. Batch scenarios   duplicate file is byte-identical, stale re-import is NOT byte-identical
                       but carries the old crawl dates, partial / missing markets really are short
  5. Planted signal    the September increase and hero price moves are visible
"""

import argparse
import csv
import hashlib
import json
import statistics
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from . import config
from .pricing import real_bounds

REAL_TOP_KEYS = ["objectID", "brandId", "name", "url", "price", "categories", "productDetails", "previewUrl",
                 "status", "source", "importSource", "crawlerName", "createdAt", "updatedAt", "releasedAt",
                 "skus", "market", "validationErrors", "isValid"]
REAL_PD_KEYS = {"collection", "packshotType", "brand", "color", "colorId", "category", "topCategory",
                "productCategory", "macroCategory", "microCategory", "superMicroCategory", "subCategory",
                "stock", "list", "material"}

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  - {detail}" if detail else ""))


def load_lines(path: Path):
    import gzip
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return f.read().splitlines()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data")
    ap.add_argument("--determinism", action="store_true")
    args = ap.parse_args(argv)
    out = Path(args.out)
    raw_dir, truth = out / "raw" / "balenciaga", out / "_truth"

    batches = list(csv.DictReader(open(truth / "batch_manifest.csv", encoding="utf-8")))
    manifest = list(csv.DictReader(open(truth / "defect_manifest.csv", encoding="utf-8")))
    master = {r["sku"]: r for r in csv.DictReader(open(truth / "product_master.csv", encoding="utf-8"))}
    heroes = list(csv.DictReader(open(truth / "hero_products.csv", encoding="utf-8")))

    defect_lines = defaultdict(set)          # file -> set(line numbers) carrying a row-level defect
    for m in manifest:
        if m["line_number"]:
            defect_lines[m["file_name"]].add(int(m["line_number"]))

    files = {b["file_name"]: load_lines(raw_dir / b["file_name"]) for b in batches}
    primary = [b for b in batches if b["batch_type"] in ("weekly", "extended_monthly")]

    # ---------------------------------------------------------------- 1. schema parity
    print("\n1. Schema parity with the real crawler output")
    bad_keys = bad_pd = n_clean = 0
    for b in primary:
        dl = defect_lines[b["file_name"]]
        for i, line in enumerate(files[b["file_name"]], start=1):
            if i in dl:
                continue
            r = json.loads(line)
            if r["skus"] and r["skus"][0].startswith(("GIFTCARD", "TEST")):
                continue
            n_clean += 1
            if list(r.keys()) != REAL_TOP_KEYS:
                bad_keys += 1
            if not {d["key"] for d in r["productDetails"]} <= REAL_PD_KEYS:
                bad_pd += 1
    check("top-level keys + order identical to real rows", bad_keys == 0, f"{n_clean:,} clean rows, {bad_keys} mismatches")
    check("productDetails keys are a subset of real keys", bad_pd == 0)

    # ---------------------------------------------------------------- 2. price realism
    print("\n2. Price realism (clean rows only)")
    out_of_env, eur_out = 0, 0
    per_cell = defaultdict(list)
    for p in master.values():
        q = config.MACRO_TAGS[p["macro_tag"]]["eur_quantiles"]
        if not q[0] <= float(p["eur_reference_price"]) <= q[-1]:
            eur_out += 1
    for b in primary:
        dl = defect_lines[b["file_name"]]
        for i, line in enumerate(files[b["file_name"]], start=1):
            if i in dl:
                continue
            r = json.loads(line)
            sku = r["skus"][0] if r["skus"] else None
            if sku not in master:
                continue
            tag, m = master[sku]["macro_tag"], r["market"]
            v = float(r["price"]["original_price"])
            lo, hi = real_bounds(tag, m)
            if not lo <= v <= hi:
                out_of_env += 1
            per_cell[(config.MACRO_TAGS[tag]["family"], m)].append(v)
    check("EUR reference prices inside real min-max per category", eur_out == 0, f"{eur_out} outside")
    check("every clean local price inside the real category x market envelope", out_of_env == 0,
          f"{out_of_env} outside")
    print("     median clean price, selected cells (local currency):")
    for fam in ("bags", "leather_goods", "slg", "shoes", "accessories"):
        cells = "  ".join(f"{m} {statistics.median(per_cell[(fam, m)]):,.0f}"
                          for m in ("FRA", "USA", "JPN", "CHN") if per_cell[(fam, m)])
        print(f"       {fam:<14} {cells}")

    # ---------------------------------------------------------------- 3. answer key
    print("\n3. Answer key (defect_manifest.csv) reconciles with the files")
    mismatched = 0
    for m in manifest:
        if not m["line_number"]:
            continue
        r = json.loads(files[m["file_name"]][int(m["line_number"]) - 1])
        if m["object_id"] and r.get("objectID") != m["object_id"]:
            mismatched += 1
            continue
        if m["field"] == "price.original_price" and m["defect_code"] != "A10_numeric_type_drift":
            if str(r["price"].get("original_price")) != m["dirty_value"]:
                mismatched += 1
    row_level = [m for m in manifest if m["line_number"]]
    check("every manifest row points at the right line + value", mismatched == 0,
          f"{len(row_level):,} row-level entries, {mismatched} mismatches")
    by_code = Counter(m["defect_code"] for m in manifest)
    print("     planted defects by code:")
    for code, n in sorted(by_code.items()):
        print(f"       {code:<34} {n:>6,}")

    # ---------------------------------------------------------------- 4. batch scenarios
    print("\n4. Batch-level scenarios")
    sha = {b["file_name"]: b["sha256"] for b in batches}
    dup = next(b for b in batches if b["batch_type"] == "duplicate_file")
    orig = dup["file_name"].replace(" (1)", "")
    check("F01 duplicate file is byte-identical to its original", sha[dup["file_name"]] == sha[orig])
    stale = next(b for b in batches if b["batch_type"] == "stale_reimport")
    src = next(b for b in primary if b["crawl_date"] == stale["crawl_date"])
    stale_created = {json.loads(line)["createdAt"] for line in files[stale["file_name"]]}
    src_created = {json.loads(line)["createdAt"] for line in files[src["file_name"]]}
    check("F02 stale re-import differs byte-wise (so a file hash alone will NOT catch it)",
          sha[stale["file_name"]] != sha[src["file_name"]])
    check("F02 ... but carries exactly the old crawl's createdAt values", stale_created == src_created)
    counts = defaultdict(Counter)
    for b in primary:
        for line in files[b["file_name"]]:
            r = json.loads(line)
            counts[b["crawl_date"]][r.get("market") or r["source"].split("_")[-1]] += 1
    check("F03 partial crawl: KOR on 2026-08-17 is < 60% of the week before",
          counts["2026-08-17"]["KOR"] < 0.6 * counts["2026-08-10"]["KOR"],
          f"{counts['2026-08-10']['KOR']} -> {counts['2026-08-17']['KOR']}")
    check("F04 missing market: no JPN rows on 2026-09-14", counts["2026-09-14"]["JPN"] == 0)
    print("     rows per crawl (weekly markets shown):")
    for d in sorted(counts):
        print(f"       {d}  total {sum(counts[d].values()):>6,}   " +
              " ".join(f"{m}:{counts[d][m]}" for m in config.WEEKLY_MARKETS))

    # ---------------------------------------------------------------- 5. planted signal
    print("\n5. Planted price signal")
    hero_skus = {h["sku"]: h["hero_id"] for h in heroes}
    hero_prices = defaultdict(dict)
    usa_by_date = defaultdict(dict)
    for b in primary:
        for line in files[b["file_name"]]:
            r = json.loads(line)
            if r.get("market") != "USA" or not r["skus"]:
                continue
            try:
                v = float(r["price"]["original_price"])
            except (TypeError, ValueError):
                continue
            usa_by_date[b["crawl_date"]][r["skus"][0]] = v
            if r["skus"][0] in hero_skus:
                hero_prices[hero_skus[r["skus"][0]]][b["crawl_date"]] = v
    before, after = usa_by_date["2026-08-31"], usa_by_date["2026-09-07"]
    moves = defaultdict(list)
    for sku in set(before) & set(after):
        if sku in master and before[sku] > 0:
            moves[master[sku]["family"]].append(after[sku] / before[sku] - 1)
    for fam in ("bags", "leather_goods", "slg", "shoes", "rtw"):
        if moves[fam]:
            print(f"       USA {fam:<14} median change 08-31 -> 09-07: {statistics.median(moves[fam]):+.1%}")
    check("September increase visible on bags (USA median >= +5%)", statistics.median(moves["bags"]) >= 0.05)
    check("shoes untouched by the increase (USA median ~0%)", abs(statistics.median(moves["shoes"])) < 0.01)
    print("     hero prices in USA by crawl:")
    for hid in sorted(hero_prices):
        series = hero_prices[hid]
        print(f"       {hid}  " + "  ".join(f"{d[5:]}:{series[d]:,.0f}" for d in sorted(series)))

    # ---------------------------------------------------------------- determinism
    if args.determinism:
        print("\n6. Determinism")
        from .generate import main as gen_main
        with tempfile.TemporaryDirectory() as tmp:
            gen_main(["--seed", "42", "--products", "300", "--out", f"{tmp}/a"])
            gen_main(["--seed", "42", "--products", "300", "--out", f"{tmp}/b"])
            ha = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(f"{tmp}/a").rglob("*.*")}
            hb = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(f"{tmp}/b").rglob("*.*")}
            check("same seed -> byte-identical output", ha == hb, f"{len(ha)} files compared")

    print(f"\n{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
