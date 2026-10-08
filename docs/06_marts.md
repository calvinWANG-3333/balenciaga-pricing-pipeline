# 06 · Phase 4 – Marts: the published interface (core, Micro, Macro)

**Goal of this phase:** turn the point-in-time catalogue into the tables people actually use: a small star
schema (`dim_` + `fct_`) for any question, plus the two client deliverables, **Micro** (weekly hero-product
prices) and **Macro** (monthly category metrics). Every mart has an **enforced contract**, and the Phase 3
"killer test" becomes a reusable **generic test** run on both the new and the old design.

**Result of the reference run (local Spark, seed 42):** `dbt build --full-refresh` **144 PASS, 0 WARN, 0 ERROR**
(+ 4 exposures). The planted September price increase comes out as **Bags +5.24%, Small Leather Goods +4.91%**
(market-weighted like-for-like), Shoes flat. The killer test finds **0 violations** on the new design and
**10 (date × market) violations** on the old one: exactly the two incidents.

---

## 1. The picture first

```
                       intermediate (Phase 3)                         marts (this phase)
                       ──────────────────────                         ──────────────────
int_products__categorized ─────────────────────────────────────► dim_product            core/
seed: markets ─────────────────────────────────────────────────► dim_market             "star schema"
int_observations__accepted ────────────────────────────────────► fct_price_observations (incremental)
int_prices__historized ────────────────────────────────────────► fct_price_changes
int_catalogue__as_of ──────────────────────────────────────────► fct_catalogue_as_of
        │
        ├── at weekly dates  × micro_pointers × weekly markets ─► mart_micro__hero_prices_weekly   micro/
        │
        └── at month-ends × macro_category ─────────────────────► mart_macro__category_monthly     macro/
                                                                         │
                                                                         ▼
                                                                  mart_macro__category_monthly_global
                                                                         │
                                       exposures (_exposures.yml) ◄──────┘
                           Micro dashboard · Macro dashboard · Incident report · Metrics agent
```

| Model | Grain | Rows (seed 42) | Materialization |
|---|---|---:|---|
| `dim_product` | 1 / SKU | 2,001 | table |
| `dim_market` | 1 / market | 16 | table |
| `fct_price_observations` | 1 / accepted reading | 198,653 | **incremental** (MERGE) |
| `fct_price_changes` | 1 / price change event | 6,681 | table |
| `fct_catalogue_as_of` | 1 / (date, product-market) | 360,700 | table |
| `mart_micro__hero_prices_weekly` | 1 / (Tuesday, hero, weekly market) | 832 = 13 × 8 × 8 | table |
| `mart_macro__category_monthly` | 1 / (month, market, macro category) | 192 = 3 × 16 × 4 | table |
| `mart_macro__category_monthly_global` | 1 / (month, macro category) | 8 | table |

New seed: `markets` (market, name, region, currency, crawl cadence). New folders: `models/marts/{core,micro,macro}`,
`tests/generic/`, `tests/marts/`.

---

## 2. Concepts, one at a time

### 2.1 Why `dim_` and `fct_` tables, and then *also* marts?

**Plain.** A supermarket has a stock room organised by product and by aisle (anyone can find anything), and
it also has ready-made gift baskets for specific customers. The stock room is the star schema; the baskets
are the deliverables.

**Term.** `core/` is a **star schema**: *facts* (events you count or sum: a price reading, a price change)
surrounded by *dimensions* (things you filter and group by: product, market). `micro/` and `macro/` are
**purpose-built marts**: one table per deliverable, already at the grain the client receives, so a BI page
is a plain `SELECT` with no business logic in it.

**Deeper.** The deliverable marts read the point-in-time catalogue, never the facts directly. That is
deliberate: the *selection rule* (which crawl represents a market on a date) lives in one place, and a test
proves the marts are pure projections of it (§2.6).

### 2.2 Model contracts: the shape is a promise

**Plain.** A contract is the label on the box: "contains these 15 columns, with these types". If the box
doesn't match the label, the factory stops instead of shipping it.

**Term.** `contract: {enforced: true}` in `_marts__models.yml`. Before creating the table, dbt compares the
model's columns and data types with the YAML and **fails the build** on any difference: a missing column,
an extra one, `decimal(18,2)` that became `double`. This is why every mart ends with explicit `cast(...)`:
the SQL states the types the contract promises.

**Why it matters here.** Evidence dashboards and the metrics agent (Phase 5) read these tables. A silent
type change (e.g. a price turning into a float) would break them without any error in dbt. With a
contract, the break happens in dbt, before anything is published.

### 2.3 Incremental models: process only what is new

**Plain.** You don't re-read the whole diary every evening to add today's page. You open it at the last page,
and to be safe you re-read the last few pages in case you corrected something.

**Term.** `fct_price_observations` is `materialized='incremental'` with `incremental_strategy='merge'` and
`unique_key='observation_id'`. On each run it only takes deliveries newer than *(latest already loaded −
35 days)* and **MERGEs** them: insert the new rows, update the existing ones. The **lookback window**
handles late corrections (a reading re-classified as an outlier once more history arrived).

**Deeper – how we know it doesn't drift.** Two safety nets:
- `dbt_utils.equal_rowcount` against `int_observations__accepted`: after every run, the incremental table
  has exactly as many rows as the full-rebuild logic would produce.
- `dbt build --full-refresh` rebuilds it from scratch. Because bronze is append-only, the result is always
  identical. Incremental is an optimisation, never a different answer.

Only one model is incremental on purpose: the others are small, and a table rebuild is simpler and cheaper
than incremental logic to maintain. (Locally, Spark has no Delta, so the model falls back to a full
overwrite; on Databricks it is a real MERGE.)

### 2.4 Micro: a complete grid, with explicit statuses

**Plain.** The weekly report has a fixed shape: 8 hero products × 8 markets, every Tuesday. An empty cell
must say *why* it is empty.

**Term.** The mart starts from a **grid** (`dates × pointers × weekly markets`, a cross join) and
**left-joins** the catalogue, so a hero that could not be found still has its row. Each row gets one
`price_status`:

| Status | Meaning | Rows (seed 42) |
|---|---|---:|
| `first_delivery` | first week with a price | 64 |
| `unchanged` | same as the last valid price | 703 |
| `price_increase` / `price_decrease` | changed vs the last valid price | 56 / 8 |
| `no_valid_price` | product on the page, but its reading was quarantined and there is no earlier price | 0 |
| `page_error` | the product page could not be read (HTTP error, captcha) | 1 |
| `not_found` | the product is not in that week's crawl at all | 0 |

**`page_error` vs `not_found`.** On 2026-08-11 the Le City bag's French page returned an error page. In the
old spreadsheet it simply "disappeared", and an analyst could report a delisting that never happened. Here
the mart checks whether the crawl it was served from contains an unreadable page for that SKU, and says so.

**"Previous price" skips gaps.** `last_value(price_local, true) over (... rows between unbounded preceding
and 1 preceding)` returns the last **non-null** price before this week (`true` = ignore nulls). A week
without a valid price doesn't reset the comparison. A unit test pins this.

Flags that analysts used to check by hand:
- `is_stale_crawl`: the crawl used is more than 7 days old (JPN on 09-15 because JPN was missing from the
  09-14 crawl; KOR/HKG on 08-18 because their 08-17 crawls were partial). 24 rows.
- `is_price_carried_forward`: the product was in this week's crawl but its reading was quarantined, so the
  last trustworthy price is shown (all 8 heroes in USA on 08-18: the EUR geo-redirect). 11 rows.

### 2.5 Macro: like-for-like, and two honest ways to average

**Plain.** "Did bags get more expensive this month?" If you compare the average price of *all* bags this
month with last month, a new €15,000 bag makes the average jump even if no price changed. So you compare
only the bags that were on sale **both** months: *like for like*.

**Term.** **LFL** pairs = same product, same market, priced at this month-end and the previous one. Then
two definitions, both published:

| Column | Formula | Question it answers |
|---|---|---|
| `lfl_mean_change` (**headline**) | mean of each product's own % change | how much did a typical product move? |
| `lfl_ratio_of_means` | Σ new prices / Σ old prices − 1 | how much did the basket move? (expensive items weigh more) |

Example (the unit test): A 100 → 110 (+10%), B 1,000 → 1,000 (0%). Mean of changes **+5.00%**, ratio of
means **+0.91%**. Same data, very different headline: the choice has to be explicit, and it is.

Real example, FRA Accessories, September: `lfl_mean_change` +0.42% but `lfl_ratio_of_means` +0.92%. Only a
few accessories increased (6.8%), but they are the expensive leather ones, so the basket moved twice as
much as the typical product.

**Global (all markets).** Prices can't be averaged across 16 currencies, but % changes can:
- `market_weighted_lfl_change` (headline): mean of the markets' changes, every market counts once.
- `product_weighted_lfl_change`: pool all product-market pairs; markets with more products weigh more.

Reference run, September vs August:

| Category | Market-weighted | Product-weighted | Lowest market | Highest market |
|---|---:|---:|---:|---:|
| Bags | **+5.24%** | +5.26% | +4.34% | +6.96% (JPN) |
| Small Leather Goods | **+4.91%** | +4.94% | +3.95% | +6.55% (JPN) |
| Accessories | +0.43% | +0.43% | +0.35% | +0.56% (JPN) |
| Shoes | −0.04% | −0.04% | −0.07% | 0.00% |

That is the planted signal (+5–8% on bags and leather goods on 2026-09-07) recovered end to end, through
all the dirty data. August is flat in every category (|change| < 0.1%).

### 2.6 The killer test becomes a generic test

**Plain.** In Phase 3 the check "each market is served from its latest eligible crawl" was a one-off script.
Now it is a reusable stamp you can put on any table.

**Term.** A **generic test** is a test with parameters, defined once with `{% test name(model, ...) %}` in
`tests/generic/`, then applied in YAML like `unique` or `not_null`.
`serves_latest_eligible_crawl(model, crawl_date_column)` recomputes the expected crawl per (date, market)
with a plain `MAX` and returns every (date, market) where the model served anything else.

It is applied twice in `_intermediate__models.yml`:

| Applied to | Thresholds | Result | Meaning |
|---|---|---|---|
| `int_catalogue__as_of` | normal (error if > 0 rows) | **0 rows** | the fix holds |
| `int_legacy__catalogue_replayed` (named `killer_test_would_have_caught_the_legacy_incident`) | **inverted**: `error_if: "= 0"` | **10 rows** (08-18 × 2 markets, 09-15 × 8 markets) | the same check would have caught the incident |

Inverted thresholds are a small trick with a big message: the build fails if the test ever **stops**
detecting the old bug, so the evidence can't silently rot.

### 2.7 Testing the marts

| Test | What it proves |
|---|---|
| contracts on all 8 marts | names and types are exactly as published |
| `unique` + `not_null` on every key, `unique_combination_of_columns` on every grain | one row per declared grain |
| `relationships` fct → dim | no orphan product or market |
| `accepted_values` on `price_status`, `macro_category`, `change_direction` | no unexpected category sneaks in |
| `equal_rowcount(fct_price_observations, int_observations__accepted)` | the incremental model never drifts |
| `assert_marts_are_projections_of_point_in_time` | every Micro price equals the catalogue price; every Macro count / min / max equals a recomputation from `fct_catalogue_as_of` × `dim_product` |
| unit test `macro_lfl_mean_of_changes_differs_from_ratio_of_means` | the LFL definitions, the new-product exclusion, Micro dates ignored by Macro |
| unit test `micro_previous_price_skips_weeks_without_a_valid_price` | previous price skips gaps; `page_error` vs `not_found`; out-of-scope markets excluded |

### 2.8 Exposures: who reads the marts

**Plain.** A list of "who uses this table", stored next to the code.

**Term.** `_exposures.yml` declares 4 downstream consumers (Micro dashboard, Macro dashboard, incident
report, metrics agent) with their owner and the marts they depend on. They appear as the last nodes in the
lineage graph, and `dbt ls -s +exposure:macro_category_monitor` lists everything a dashboard depends on:
the answer to "if I change this model, what breaks?".

---

## 3. Step by step

### Step 1 – branch and remove the old singular test (Terminal)

The singular test `assert_point_in_time_uses_latest_eligible_crawl.sql` is replaced by the generic test, so
it must be deleted from git (otherwise both would run).

```bash
cd ~/Documents/LY_data_pipeline_CV_project/balenciaga-pricing-pipeline
git checkout main && git pull
git checkout -b phase-4/marts
git rm dbt/tests/intermediate/assert_point_in_time_uses_latest_eligible_crawl.sql
git add dbt/ docs/
git status          # check: new marts/, tests/generic/, tests/marts/, seeds/markets.csv; one deleted test
git commit -m "feat(dbt): marts - star schema, Micro and Macro deliverables, contracts, generic killer test, exposures"
git push -u origin phase-4/marts
```

If `dbt/package-lock.yml` is still uncommitted, add it in this commit.

### Step 2 – build in Studio

Switch Studio to the `phase-4/marts` branch, then:

```bash
dbt build
```

Expect **144 PASS** + 4 exposures (shown as NO-OP / skipped: exposures are documentation, not tables).
The first build of `fct_price_observations` is a full load. Run `dbt build -s fct_price_observations` a
second time: the log now shows a **MERGE**, and the row count stays at 198,653.

### Step 3 – look at the deliverables (SQL Editor)

```sql
-- Micro: the Le City bag, every Tuesday, every weekly market
SELECT delivery_date, market, price_local, previous_price_local, change_vs_previous_pct,
       price_status, crawl_date_used, is_stale_crawl, is_price_carried_forward
FROM workspace.dbt_rwang_marts.mart_micro__hero_prices_weekly
WHERE pointer_id = 'HERO-01'
ORDER BY market, delivery_date;

-- Macro: the September headline
SELECT report_month, macro_category, market_weighted_lfl_change, product_weighted_lfl_change,
       min_market_lfl_change, max_market_lfl_change, market_with_highest_change
FROM workspace.dbt_rwang_marts.mart_macro__category_monthly_global
ORDER BY report_month, macro_category;

-- Macro detail: one market, mean of changes vs ratio of means
SELECT macro_category, n_products, median_price, lfl_n_products,
       lfl_mean_change, lfl_ratio_of_means, lfl_share_increased
FROM workspace.dbt_rwang_marts.mart_macro__category_monthly
WHERE report_month = '2026-09-01' AND market = 'FRA';
```

### Step 4 – see the lineage and the exposures

In Studio, open `mart_macro__category_monthly_global` and the **Lineage** tab: the exposures appear as the
final nodes. Then:

```bash
dbt ls -s +exposure:micro_hero_price_tracker
```

### Step 5 – merge

```bash
gh pr create --fill && gh pr merge --merge --delete-branch
git checkout main && git pull
```

**Checkpoint – Phase 4 is done when:**
- [ ] `dbt build` = 144 PASS in Studio, 0 errors
- [ ] `mart_micro__hero_prices_weekly` has 832 rows; HERO-01 USA goes $3,090 → $3,310 on 2026-09-08
- [ ] `mart_macro__category_monthly_global`: September Bags ≈ +5.2%, SLG ≈ +4.9%, Shoes ≈ 0
- [ ] second run of `fct_price_observations` uses MERGE and keeps 198,653 rows
- [ ] PR merged

---

## 4. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `This model has an enforced contract that failed` | a column type in SQL differs from the YAML | read the "expected / actual" table in the error; fix the `cast` or the YAML |
| unit test: `UNION can only be performed on inputs with the same number of columns` | the expected rows don't all list the same columns | give every `expect` row the same keys (use `null` where needed) |
| both `assert_point_in_time_uses_latest_eligible_crawl` and the generic test run | the old file is still in git | `git rm` it (Step 1) |
| `equal_rowcount` fails after an incremental run | a change in upstream logic touched rows older than the lookback | `dbt build -s fct_price_observations --full-refresh` |
| `macro_category` has a value `None` (local Spark only) | dbt-spark *session* mode sends empty seed cells as the text `'None'` | not an issue on Databricks; the local harness is patched |
| Macro LFL slightly different from the reference | `percentile_approx` is approximate (median only) | fine: LFL uses exact means |

---

## 5. Interview lines

> "The marts are a small star schema, `dim_product`, `dim_market` and three facts, plus one table per
> client deliverable at exactly the grain the client receives. The deliverables only read the point-in-time
> catalogue, and a test proves they are pure projections of it, so the selection logic exists in one place."

> "Every mart has an enforced contract. If someone turns a decimal price into a float or drops a column, the
> build fails in dbt, not in the dashboard or the agent that reads it."

> "For Macro I publish two like-for-like measures side by side: the mean of product changes and the ratio of
> means. On one test case they say +5% and +0.9%. In the data, French accessories show +0.4% vs +0.9%:
> few items moved, but they were the expensive ones. Choosing the headline metric is a business decision,
> so I made it explicit and pinned it with a unit test."

> "The planted +5–8% September increase on leather goods comes out at +5.2% for bags and +4.9% for SLG,
> market-weighted, after going through duplicated files, stale re-deliveries, partial crawls and
> currency errors. Shoes stay flat, as generated."

> "I turned the incident check into a generic test and run it on both designs. On the new one it must find
> nothing; on the replay of the old one I inverted the thresholds, so the build fails if it ever stops
> finding the incident. The evidence that the fix matters is part of CI."

> "The weekly report distinguishes 'not found' from 'page error'. An unreadable page isn't evidence that a
> product was delisted, and that difference used to be checked by hand."
