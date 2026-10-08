# 05 · Phase 3 – Intermediate: trust, history and the point-in-time catalogue

**Goal of this phase:** build the layer that actually fixes the production incident. Every reporting date
gets the catalogue *as it was knowable on that date*, computed from the immutable history. Re-delivering an
old crawl, importing files in a different order, or a half-finished crawl can no longer change what a
deliverable shows.

**Result of the reference run (local Spark, seed 42):** `dbt build` **97 / 97 PASS**; answer-key recall **100% on
all 36 planted defect codes** (the two price-scale codes are now caught here); the replay of the old design
shows **3,305 wrong prices on 2026-09-15** and **1,802 missing products on 2026-08-18**. The new design
shows neither.

---

## 1. The picture first

```
stg_crawl__product_observations ─┬─► int_deliveries__profiled          1 row / file    trust each delivery
                                 │        │
                                 │        ▼
                                 ├─► int_market_batches__assessed      1 row / file × market   eligible?
                                 │        │
                                 ▼        ▼
                         int_observations__classified                 1 row / line    exactly one FATE
                                 │
                                 ▼
                         int_observations__accepted                   1 row / batch × product   clean history
                          │            │                 │
                          ▼            ▼                 ▼
     int_products__categorized   int_prices__historized   int_catalogue__as_of  ◄── int_as_of_dates
     (seed-driven rule engine)   (SCD2 from history)      (THE FIX: point in time)
                                                                  │
                          int_legacy__catalogue_replayed ─────────┴──► qa_incident__legacy_vs_point_in_time
                          (the OLD rule, for comparison)
```

New seeds: `ly_category_tree`, `ly_category_rules`, `micro_pointers`.
Moved: the delivery checks now live in `int_deliveries__profiled`; `qa_raw__file_profile` just presents them.

---

## 2. Concepts, one at a time

### 2.1 Trust is decided per delivery

**Plain.** Before unpacking a delivery, the warehouse decides whether to accept the whole truck: a truck that
is a copy of yesterday's, or that carries last month's goods with a new date on the paperwork, is refused at
the gate.

**Term.** `int_deliveries__profiled` computes, per file, `is_trusted` (not a duplicate, not stale) and keeps
two dates side by side: `file_crawl_date` (what the **name** claims) and `content_crawl_date` (what the
**data** says). Everything downstream uses the content date. The F02 file *claims* 2026-09-15 and
*contains* 2026-08-31.

**Deeper – why it moved out of the quality folder.** In Phase 2 this was a QA report. Now the pipeline *acts*
on it, so it is business logic and belongs in `intermediate`. The rule we keep: QA models may read business
models, business models never read QA models.

### 2.2 Market batches and eligibility

A *market batch* is "the crawl of market M inside delivery D". It is **eligible** to represent market M's
catalogue only if the delivery is trusted **and** M is complete in it. The 2026-08-17 crawls of KOR and HKG
stopped at 45%: their prices are still valid readings, but they cannot define *which products are on sale*.
Otherwise 55% of the catalogue would look delisted.

### 2.3 One fate per line: the books close here

`int_observations__classified` has exactly as many rows as staging (tested) and gives each line one fate:

| Fate | Lines (seed 42) | Meaning |
|---|---:|---|
| accepted | 198,653 | usable history |
| blocked_delivery | 37,968 | inside the `(1)` copy or the stale re-export |
| quarantined_in_staging | 1,185 | a staging rule quarantined it |
| exact_duplicate | 605 | second copy of an identical line |
| price_scale_outlier | 296 | ×10 / ×100 / ÷10 away from its reference price |

### 2.4 Price-scale outliers need context

**Plain.** ¥61,600,000 is a believable number for a Tokyo price list, until you notice the same bag was
¥616,000 in every other crawl.

**Term.** A reading is an outlier when `log10(price / reference)` lands within 0.1 of a non-zero integer, i.e.
a whole power of ten away. Genuine price moves (the September +5–8%, individual ±15%) are nowhere near that.

Two references, in order:

| Reference | When | How |
|---|---|---|
| history | the product has ≥ 3 readings in its market | median of its readings |
| price ladder | too little history (markets crawled only monthly) | same SKU in France, same crawl, × that market's typical local/EUR ratio, which is itself measured from the data |

Result: **296 flagged, 296 planted, 0 false positives.** The first version used history only and missed 5,
all in monthly-only markets (CAN, SAU, THA, TWN, SGP). The price-ladder reference fixed them. The grading
model found the gap, which is the reason the answer key exists.

### 2.5 Harmonized categories: rules are data

**Plain.** The brand files its products however its website needs: wallets under "leather goods", keyrings
under "small leather goods", sneakers mixed with boots. The client needs one stable taxonomy that does not
move when the brand reorganizes its site.

**Term.** A small **rule engine**. `ly_category_rules` (a seed) lists regex rules on the product name, the
brand's sub-tag or its top-level tag, each with a priority. Every matching rule is a candidate and the lowest
priority wins (a `ROW_NUMBER()` over the matches). `ly_category_tree` holds the taxonomy and which
`macro_category` each code reports under.

| Priority | Matches on | Why first |
|---|---|---|
| 10–35 | product name (wallet, charm, bag, sneaker, ring, belt …) | the name is the most reliable signal |
| 40–50 | brand sub-tag (`bal_super_micro_*`) | next best, but the brand mixes things |
| 90–96 | brand top-level tag | fallback only |

Examples:

| Product | Brand files it under | Harmonized | Rule |
|---|---|---|---|
| hourglass handbag small (HERO-03) | sub-tag `small_leather_goods` | **LG_BAGS** | R012 – a handbag is a bag |
| cash long coin and card holder (HERO-08) | `leather_goods` | **LG_SLG** | R010 – a wallet is a wallet |
| bag charm / keychain | `slg` | **AC_OTHER** | R011 – a charm is an accessory |

0 products uncategorized (a `warn` test watches for new brand tags falling through).

*Seed hygiene:* seeds are loaded through SQL `INSERT` statements, so they contain no apostrophes and no
backslashes. Word boundaries are written `(^|[^a-z])…([^a-z]|$)` rather than `\b`. (The first run failed
on "brand's".)

### 2.6 Price history (SCD2) without snapshots

`int_prices__historized`: one row per product-market per *price period* (`valid_from`, `valid_to`,
`is_current_period`). It is built with *gaps and islands*: `LAG` spots a price change, and a running `SUM`
numbers each island of equal prices.

**Why not a dbt snapshot?** A snapshot records what a *mutable* source looks like each time dbt runs. Miss a
run and that history is gone forever, and it can never be rebuilt. Our bronze is append-only, so the full
history is already stored and periods can be **rebuilt from scratch, deterministically**. Snapshots are the
right tool when the source overwrites itself, which is exactly the situation we designed away.

### 2.7 The point-in-time catalogue: the fix

**Plain.** To know what a bag cost on 15 September, read the newspaper that was on sale on 15 September. If
someone re-shelves an old edition on the 15th, that does not change what was printed that day.

**Term.** `int_catalogue__as_of` has one row per (reporting date, product), and is a **pure function of the
immutable history and the date**:

1. **Presence:** for each market, take the latest **eligible** crawl by **crawl date** ≤ D that was
   **delivered before the end of D**. Its products are on sale at D.
2. **Price:** the latest **accepted** reading of that product delivered before the end of D. If the presence
   crawl's reading was quarantined, the last trustworthy price is carried forward and flagged
   (`is_price_carried_forward`).

`int_as_of_dates` lists the reporting dates. **Micro:** the day after every crawl (crawl Monday, delivery
Tuesday). **Macro:** every month-end. `knowledge_cutoff` (end of that day) prevents **look-ahead bias**: a
backfill can never use a file that had not yet arrived.

Micro and Macro read the same model at different dates. They share history, never a mutable table.

### 2.8 The incident, replayed and measured

`int_legacy__catalogue_replayed` applies the **old** rule ("whatever was imported last") to the same dates and
the same row-level rules. Only batch selection differs. `qa_incident__legacy_vs_point_in_time` compares them:

| Reporting date | What the old design served | Damage | Point-in-time |
|---|---|---|---|
| 2026-08-18 (Tue) | the half-finished KOR / HKG crawls of 08-17 | **1,802 products missing** | the complete 08-10 crawls |
| 2026-09-15 (Tue) | the 08-31 crawl, re-exported that morning, in **all 8 weekly markets** (JPN too) | **3,305 prices wrong (~26% per market): the September increase rolled back** | 09-14 crawl (JPN: 09-07, since JPN was missing on 09-14) |
| every other date | same crawl | none | same |

The 09-15 row is the production incident: the weekly Micro delivery that Tuesday would have reported
**pre-increase prices**, because someone re-imported the August crawl to finish the August Macro delivery.

---

## 3. New tests

| Test | Proves |
|---|---|
| `equal_rowcount(classified, staging)` + `fate` not null / accepted values | every line has exactly one fate |
| `unique_combination(market_batch_id, object_id)` on accepted | one reading per product per crawl |
| `assert_point_in_time_uses_latest_eligible_crawl` | recomputed independently with a plain `MAX`: the model always picks the latest eligible crawl |
| `assert_point_in_time_never_sees_blocked_or_future_data` | no blocked delivery, no partial batch, no crawl after D, no file delivered after D |
| `assert_price_periods_do_not_overlap` | SCD2 integrity: ordered, non-overlapping, one current period |
| `warn_uncategorized_products` (severity warn) | a new brand tag falling through the rules gets noticed |
| `assert_answer_key_fully_caught` | now covers **all** codes, including the two price-scale ones |
| seed tests | rule ids and priorities unique, every rule points to a real category |

---

## 4. Step by step

### Step 1 – branch, commit, push (Terminal)

```bash
cd ~/Documents/LY_data_pipeline_CV_project/balenciaga-pricing-pipeline
git checkout main && git pull
git checkout -b phase-3/intermediate-point-in-time
git add dbt/ docs/
git status
git commit -m "feat(dbt): intermediate layer - delivery trust, fates, categorization, SCD2, point-in-time catalogue, incident replay"
git push -u origin phase-3/intermediate-point-in-time
```

(In Studio, first commit the pending `dbt/package-lock.yml` on `main`, or include it here. It pins the exact
dbt_utils version, so jobs and CI install the same one you tested with.)

### Step 2 – build in Studio

Switch to the branch, then:

```bash
dbt build
```

`dbt build` loads the seeds first, then models and tests in dependency order. The first run of
`int_observations__classified` and `int_catalogue__as_of` takes a few minutes on the 2X-Small warehouse.

### Step 3 – look at the results (SQL Editor)

```sql
-- the incident, replayed
SELECT as_of_date, market, point_in_time_crawl_date, legacy_crawl_date,
       n_missing_in_legacy, n_price_differences, share_prices_different
FROM workspace.dbt_rwang_quality.qa_incident__legacy_vs_point_in_time
WHERE legacy_would_be_wrong
ORDER BY as_of_date, market;

-- one hero bag through time: point in time vs the old design
SELECT c.as_of_date, c.market, c.price_local AS point_in_time_price, l.price_local AS legacy_price
FROM workspace.dbt_rwang_intermediate.int_catalogue__as_of c
LEFT JOIN workspace.dbt_rwang_intermediate.int_legacy__catalogue_replayed l USING (as_of_date, object_id)
WHERE c.sku = '543321TT8F11000' AND c.market = 'USA'
ORDER BY c.as_of_date;

-- how products were categorized
SELECT ly_category_code, categorized_by_rule, count(*) AS n_products
FROM workspace.dbt_rwang_intermediate.int_products__categorized
GROUP BY 1, 2 ORDER BY 1, 2;
```

The second query is the clearest single picture of the project. The Le City bag in the USA goes from $3,090
to $3,310 after 09-07 in both columns, with two exceptions:

| Date | Point in time | Old design | Why |
|---|---:|---:|---|
| 2026-08-18 | $3,090 (carried forward) | *no price* | that week's USA reading came back in EUR (geo-redirect) and was quarantined |
| 2026-09-15 | $3,310 | **$3,090** | the re-exported August crawl overwrote the catalogue: pre-increase price |

### Step 4 – merge

```bash
gh pr create --fill && gh pr merge --merge --delete-branch
git checkout main && git pull
```

**Checkpoint – Phase 3 is done when:**
- [ ] `dbt build` = 97 PASS in Studio
- [ ] `qa_answer_key__recall`: recall = 1.0 for every code
- [ ] `qa_incident__legacy_vs_point_in_time`: wrong only on 2026-08-18 (2 markets) and 2026-09-15 (8 markets)
- [ ] PR merged

---

## 5. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| seed fails with a syntax error | an apostrophe or backslash crept into a CSV | remove it (see seed hygiene) |
| `percentile_approx` result differs slightly from the reference run | it is approximate by design | fine: the outlier rule needs a whole power of ten |
| `int_catalogue__as_of` is slow | joins ~16 dates × ~200k readings | normal on 2X-Small; it is a table, built once per run |

---

## 6. Interview lines

> "The fix is a point-in-time model: for any date, each market's catalogue is the latest *eligible* crawl by
> crawl date that had been delivered by that date. It's a pure function of an append-only history and a date,
> so Micro and Macro can read different dates without ever sharing a mutable table, and re-delivering an old
> file can't change anything."

> "I didn't just claim the old design was broken: I replayed it. Same rows, same rules, only the
> batch-selection rule swapped. On the Tuesday of the incident it would have served the August crawl in all
> eight weekly markets: 3,305 prices wrong, the whole September increase rolled back. Every other date
> matches, which is the point: the old design only fails when something goes wrong upstream."

> "Every delivered line gets exactly one fate – accepted, blocked delivery, duplicate, quarantined, or price
> outlier – and a row-count test proves the books close. Nothing disappears silently."

> "Price-scale errors are invisible row by row. I check each reading against the product's own history, and
> where history is too short – monthly-only markets – against the same SKU in France scaled by a price ladder
> measured from the data. 296 planted, 296 caught, zero false positives."

> "I derive SCD2 price history from the immutable log instead of using dbt snapshots. Snapshots are for
> sources that overwrite themselves; when the history is append-only, you can rebuild every period
> deterministically, and you lose nothing if a run is missed."
