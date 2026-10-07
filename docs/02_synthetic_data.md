# 02 · Phase 1a – The synthetic crawl generator

**Goal:** realistic, reproducible, *dirty* crawl files that look exactly like what a real price crawler
delivers – plus an answer key listing every problem we planted.

```bash
python3 -m generator.generate --seed 42 --products 2000 --out data   # ~30 s, standard library only
python3 -m generator.validate --out data --determinism               # 13 PASS / FAIL checks
```

Requires Python ≥ 3.10. No packages to install.

---

## 1. Why synthetic, and why it is still honest

**Plain.** We cannot publish a former employer's data, but fake data with random prices would teach nothing
– a €40 Le City bag makes every downstream number meaningless. So we fake the *shop*, not the *numbers*:
the generator invents products, but their prices follow the real price distribution of their category and
the real price ladder between countries.

**What the calibration contains** (`generator/calibration/category_profiles.json`): only aggregates measured
on four real weekly Balenciaga crawls – 13 EUR price quantiles per brand category, the localized label
vocabularies, and pools of public product names. No raw rows, no real SKUs, no per-product prices.

**Realism guarantees** (enforced by `validate.py`):

| Check | Result (seed 42) |
|---|---|
| EUR reference price inside the real min–max of its category | 2,001 / 2,001 products |
| Every clean local price inside the real category × market envelope | 188,946 / 188,946 rows |
| 19 top-level keys in the real order, real `productDetails` keys | 0 mismatches |

Real vs synthetic price distribution (p05 / median / p95, local currency; real = one real weekly crawl,
synthetic = the 2026-08-31 crawl, before the planted September increase):

| Family | Market | Real | Synthetic |
|---|---|---|---|
| bags | FRA | 895 / 2,150 / 3,800 | 825 / 2,190 / 3,790 |
| bags | USA | 1,150 / 2,650 / 4,590 | 1,150 / 2,760 / 4,950 |
| bags | JPN | 158,400 / 376,200 / 671,000 | 172,200 / 402,100 / 683,700 |
| bags | CHN | 9,500 / 19,900 / 34,500 | 9,500 / 20,900 / 38,000 |
| slg | FRA | 225 / 425 / 1,390 | 245 / 395 / 1,190 |
| slg | USA | 295 / 525 / 1,690 | 290 / 505 / 1,520 |
| shoes | FRA | 595 / 950 / 1,690 | 515 / 945 / 1,590 |
| shoes | USA | 625 / 1,190 / 1,990 | 650 / 1,170 / 1,980 |
| accessories | FRA | 120 / 395 / 895 | 170 / 395 / 920 |
| rtw | USA | 750 / 1,490 / 5,990 | 730 / 1,480 / 6,140 |

Known gap: RTW in China has a heavier synthetic top tail (p95 ¥51,000 vs ¥27,800 real) because the real
China site carries fewer high-end RTW pieces. It does not affect Micro or Macro (both are leather goods,
shoes and accessories).

---

## 2. How it works – shop first, crawls second

```
catalog.py   build the "shop": ~2,000 products (style code + material + colour = SKU), category,
             launch / retire week, EUR reference price, which markets sell it and at which ratio
pricing.py   EUR price  = inverse-CDF sample from the category's real quantiles, snapped to retail
                          price points (595, 1,190, 2,490 ...)
             local price = EUR x per-product market ratio (drawn inside the real p05-p95 band),
                          rounded like the website (JPY to 100, KRW to 10,000 ...)
render.py    "visit" product P in market M on crawl date D -> one raw record, field-for-field
defects.py   plant dirty data + write every planted defect to the answer key
generate.py  calendar, price events, batch-level scenarios, file writing
validate.py  prove all of the above
```

**Crawl calendar** – one crawl every Monday from 2026-07-06 to 2026-09-28 (13 crawls). On the last Monday of
each month (07-27, 08-31, 09-28) the crawl is **extended**: 16 markets instead of the 8 weekly ones. Weekly
crawls feed Micro; extended crawls feed Macro. That is the real cadence that caused the original incident.

**Planted business signal** (so the marts have something true to find):
- **September price increase** – from the 2026-09-07 crawl, ~85% of bags / leather goods / SLG go up by
  5–8% depending on the market (USA +7%, JPN +8%, CHN +5% …). Shoes and RTW do not move.
- **Individual re-pricings** – ~0.15% of products per week move ±5–15% (real crawls show 1–2 per week).
- **Assortment churn** – ~8% of products launch mid-period, up to ~7% are retired.
- **8 hero products** (`_truth/hero_products.csv`) – Le City, Rodeo, Hourglass, Le Cagole, Triple S.2, 3XL,
  Le City card holder, Cash wallet – always sold in all 8 weekly markets. They become the Micro "pointers".

---

## 3. Systemic quirks (present on every row – handled by design, not listed in the answer key)

All of these were **observed in the real exports**.

| Code | Quirk | Consequence for staging |
|---|---|---|
| S1 | `price.price` is in minor units (×100) except for CHN, SAU, FRA – and `price.currency` always says `EUR` | never use `price.price`; parse `original_price` + `original_currency` |
| S2 | category labels are in the site's language: `FEMME / Sacs`, `女士 / 包袋`, `MUJER / Bolsos` | a harmonized category layer is mandatory |
| S3 | the free-text `productCategory` label changes week to week for the same product (~55%) | never categorize on that label alone |
| S4 | brand tags contain typos: `ba_micro_…`, `Bal_super_micro_…` | normalize case / prefix before matching |
| S5 | China is a different crawler: 2 SKUs (`[style, numeric id]`), Title Case names, empty `productDetails` | crawler-aware parsing |

---

## 4. The defect catalogue (planted, graded)

`expected_handling`: **fix** = deterministic repair in staging, raw value kept · **quarantine** = excluded
from marts and surfaced in a `qa_` model · **warn** = kept but surfaced · **block** = the file must not be
trusted / loaded twice.
**Origin**: *sample* = seen in the real exports · *work* = met during the internship, reproduced here.

| Code | Family | What it looks like | Handling | Origin | Count (seed 42) |
|---|---|---|---|---|---:|
| A01_us_thousands_separator | price format | `"1,250"` | fix | work | 655 |
| A02_eu_decimal_format | price format | `"1.250,00"`, `"1 250,00"` (narrow NBSP) | fix | work | 643 |
| A03_currency_symbol_in_price | price format | `"$1,250"`, `"1 250 €"`, `"HK$10,600"` | fix | work | 597 |
| A04_trailing_decimals | price format | `"1250.00"` | fix | sample (KRN feeds) | 419 |
| A05_price_on_request | price format | `"Price upon request"`, `"Sur demande"`, `"价格请咨询"` | quarantine | work | 154 |
| A06_from_price | price format | `"From 1,250"`, `"À partir de 1 250 €"` | quarantine | work | 94 |
| A07_placeholder_price | price format | `"0"`, `"99999999"` | quarantine | work | 108 |
| A08_non_ascii_digits | price format | full-width `１２５０`, Arabic-Indic `١٢٥٠` | fix | work | 144 |
| A09_minor_units_leak | price format | original price written ×100 | quarantine | sample (S1 cousin) | 191 |
| A10_numeric_type_drift | price format | `original_price` is a JSON number, not a string | fix | sample (LV feed) | 394 |
| A11_dot_thousands_ambiguous | price format | `"2.490"` – 2,490 or 2.49? | fix (by currency rule) | work | 107 |
| B01_currency_code_notation | currency | `"usd"`, `"$"` | fix | work | 194 |
| B02_geo_redirect_currency | currency | USA rows priced in EUR (crawler hit the site from an EU IP) | quarantine | work | 60 |
| C01_html_entity_in_name | text | `&amp;`, `&nbsp;`, `&#39;` | fix | sample (LV feed) | 572 |
| C02_whitespace_noise | text | leading / trailing / double space, NBSP, newline | fix | sample | 975 |
| C03_mojibake | text | `PrÃªt-Ã€-Porter`, `å¥³å£«` (UTF-8 read as Latin-1) | fix | work | 98 |
| C04_missing_name | text | `""` / `null` | quarantine | work | 113 |
| C05_case_drift | text | `LE CITY BAG MEDIUM` | fix | sample (mixed casing) | 379 |
| D01_exact_duplicate_row | identity | same line twice | fix (dedup) | sample (KRN feed) | 605 |
| D02_conflicting_duplicate | identity | same objectID, different price + URL variant | quarantine | sample (KRN feed) | 114 |
| D03_sku_format_variant | identity | lower-case / spaced / hyphenated SKU – objectID changes too | fix | sample (Cartier `CR` prefix) | 388 |
| D04_missing_sku | identity | `skus: []` | fix (from objectID) | work | 97 |
| E01_missing_price_value | schema | `price.price` key absent | fix | sample (4,148 KRN rows) | 570 |
| E02_null_url | schema | `url: null` | warn | work | 97 |
| E03_empty_preview_url | schema | `previewUrl: ""` | warn | sample (~17% of LV rows) | 1,635 |
| E04_epoch_seconds_timestamp | schema | HKG chunk of 2026-08-10 in epoch **seconds** | fix | work | 1,625 |
| E05_boolean_as_string | schema | `isValid: "true"` | fix | work | 208 |
| E06_missing_market_field | schema | `market` key absent (recover from `source`) | fix | work | 109 |
| F01_duplicate_file | batch | `… (1).ndjson`: byte-identical copy of 2026-08-10 | block | sample (`(1)` file in exports) | 1 |
| **F02_stale_reimport** | batch | 2026-08-31 crawl re-delivered as a 2026-09-15 file – **the incident** | block | **work** | 1 |
| F03_partial_crawl | batch | 2026-08-17: KOR and HKG stop at 45% of the catalogue | warn | work | 2 |
| F04_missing_market | batch | 2026-09-14: no JPN at all | warn | sample (market coverage varies) | 1 |
| G01_unit_scale_error | plausibility | price ×10 or ÷10 | quarantine | work | 105 |
| G02_non_product_page | plausibility | e-gift cards, `test product - do not buy` | quarantine | work | 131 |
| G03_http_error_row | plausibility | `status: 404`, `isValid: false` | quarantine | work | 200 |
| G04_isvalid_contradiction | plausibility | `validationErrors` present but `isValid: true` | quarantine | sample (KRN feed) | 97 |

Total: **11,878 row-level** defects (~5% of 238,707 rows) and **5 batch-level** defects across 15 files.

**Why F02 matters most.** The stale file is *not* byte-identical to the original (the export touched
`updatedAt`), so a naive "skip files we have already seen" check by file hash does not catch it. Only
content-level logic – "this file's crawl timestamps are older than a crawl we already hold" – does. Loading it
as *latest* would silently roll every Macro price back two weeks: exactly what happened in production.

---

## 5. Outputs

```
data/raw/balenciaga/            15 NDJSON files (13 crawls + 1 duplicate + 1 stale re-import), ~330 MB
data/_truth/defect_manifest.csv answer key: file, line, objectID, code, field, clean value, dirty value, handling
data/_truth/batch_manifest.csv  every file: crawl date, type, rows, markets, sha256
data/_truth/product_master.csv  the "shop" (ground truth, never loaded as a source)
data/_truth/price_changes.csv   every planted price change
data/_truth/hero_products.csv   the 8 hero SKUs
```

Use `--gzip` to write `.ndjson.gz` (≈14× smaller) for uploading; Databricks reads gzip transparently.

---

## 6. Interview lines

> "The source data is synthetic but calibrated: prices are sampled from the real per-category distribution
> and converted with the real cross-market price ladder, so every clean price sits inside the envelope seen in
> production. I can show the validation that proves it."

> "I planted about 35 kinds of crawl defects – most of them seen in real feeds – and the generator writes an
> answer key with file and line number. My QA layer is graded against that key: every defect has to be either
> repaired or quarantined, and nothing may disappear silently."

> "The nastiest one is a stale re-import: an old crawl re-delivered with a new file name and a different file
> hash. A file-level dedup misses it; you need content-level batch logic. That is the bug that broke our
> weekly and monthly deliveries in production."
