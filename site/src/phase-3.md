---
title: Phase 3 · Point in time
---

```js
import {chapterHead, lineageSection, pager} from "./components/chapter.js";
display(chapterHead("p3", "Phase 2 tagged every line. This phase decides which deliveries to trust, then rebuilds the price list of each country as it was known on any given date, using only files that had arrived by that date. Sending an old file again can no longer change a report, and a replay of the old method shows exactly what it got wrong."));
```

<section class="block"><div class="label">01 Problem</div><div class="content">

The old design kept one shared catalogue that held whatever file was imported last. In production, someone
re-imported the August crawl to finish the August Macro delivery. On Tuesday 15 September, the weekly Micro
delivery would have reported pre-increase prices.

Two other traps sit in the same history. The 08-17 crawls of KOR and HKG stopped at 45 %: read as a full
catalogue, 55 % of products would look delisted. And a price ×100 looks like a normal number until you
compare it with the same product in other crawls.

So the question is simple: for a given date, which crawl represents each market?

</div></section>

<section class="block"><div class="label">02 Decision</div><div class="content">

Trust is decided **per delivery**, using the crawl date found in the data, never the date in the file name.
A market batch is **eligible** only if its delivery is trusted and the market is complete in it. Every line
gets **exactly one fate**.

Then `int_catalogue__as_of` is a **pure function of the history and the date**. For each market it takes the
latest eligible crawl by crawl date ≤ D, delivered before the end of D. The price is the latest accepted
reading delivered by then. If the reading in that crawl was quarantined, the last trusted price is carried
forward and flagged. The end-of-day cut-off blocks look-ahead: a backfill never uses a file that had not yet
arrived.

| Model | Grain: one row per | Role |
|---|---|---|
| `int_deliveries__profiled` | file | trusted? not a copy, not stale |
| `int_market_batches__assessed` | file × market | eligible? trusted and complete |
| `int_observations__classified` | line | one fate |
| `int_observations__accepted` | market batch × product | clean history |
| `int_prices__historized` | product-market × price period | SCD2 price history |
| `int_products__categorized` | SKU | harmonized category |
| **`int_catalogue__as_of`** | date × product-market | the fix |
| `int_legacy__catalogue_replayed` | date × product-market | the old rule, for comparison |

</div></section>

<section class="block"><div class="label">03 Rejected<span>The alternatives I considered, and why not.</span></div><div class="content">

| Alternative | Why not |
|---|---|
| Keep one catalogue holding the last import | In the replay, re-importing one old file rolled back the September increase in all 8 weekly markets. |
| Trust the date in the file name | The stale file claims 2026-09-15 and contains 2026-08-31. Everything downstream uses the content date. |
| Let a partial crawl define what is on sale | 45 % of a catalogue makes 55 % look delisted. Its prices stay valid readings; it just cannot define presence. |
| dbt snapshots for price history | A snapshot needs every run. Miss one and that history is gone. Bronze is append-only, so periods can be rebuilt from scratch. |
| Outlier check on history only | The first version missed 5, all in monthly-only markets. A price-ladder reference from France fixed them. |

</div></section>

<section class="block"><div class="label">04 dbt features<span>What each one does in this phase.</span></div><div class="content">

| Feature | What it does here |
|---|---|
| Seeds | `ly_category_rules`, `ly_category_tree`, `micro_pointers`. Category rules are data: one CSV line in a pull request. Seed tests keep rule ids and priorities unique. |
| Window functions | `ROW_NUMBER()` picks the latest eligible crawl and the winning category rule. `LAG` + a running `SUM` build price periods (gaps and islands). |
| SCD2 without snapshots | `int_prices__historized` derives `valid_from`, `valid_to`, `is_current_period` from the immutable history. |
| `dbt_utils` generic tests | `equal_rowcount` proves the books close; `unique_combination_of_columns` proves one reading per product per crawl. |
| Singular tests | Recompute the latest eligible crawl with a plain `MAX`; prove no blocked, partial or future data is used; prove price periods never overlap. |
| `warn` severity | `warn_uncategorized_products` flags a new brand tag without failing the build. |

```pgsql
-- models/intermediate/prices/int_catalogue__as_of.sql
-- 1. for every date and market: the latest eligible crawl known at that date
chosen_batches as (

    select *
    from (
        select
            d.as_of_date,
            d.is_micro_date,
            d.is_macro_date,
            b.market,
            b.market_batch_id                                            as presence_batch_id,
            b.crawl_date                                                 as presence_crawl_date,
            b.crawl_scope                                                as presence_crawl_scope,
            row_number() over (
                partition by d.as_of_date, b.market
                order by b.crawl_date desc, b.delivered_at desc
            )                                                            as recency_rank
        from as_of_dates d
        inner join batches b
            on  b.crawl_date <= d.as_of_date
            and b.delivered_at < d.knowledge_cutoff
    )
    where recency_rank = 1

),
```

</div></section>

```js
display(lineageSection("p3", await FileAttachment("lineage/lineage_p3.svg").text()));
```

<section class="block"><div class="label">06 Proof<span>Reference run, local Spark, seed 42.</span></div><div class="content">

<div class="versus">
  <div><span class="micro">New design</span><b>0</b><p>wrong prices or missing products on either date</p></div>
  <div><span class="micro">Old design, replayed</span><b>3,305</b><p>wrong prices on 2026-09-15, plus 1,802 missing products on 2026-08-18</p></div>
</div>

| Fate | Lines |
|---|--:|
| accepted | 198,653 |
| blocked_delivery | 37,968 |
| quarantined_in_staging | 1,185 |
| exact_duplicate | 605 |
| price_scale_outlier | 296 |

<p class="cap"><code>dbt build</code>: 97 / 97 PASS. Recall is 100 % on all 36 planted defect codes, including the two price-scale codes Phase 2 could not catch. Price-scale outliers: 296 flagged, 296 planted, 0 false positives. On every other date, the old and new designs serve the same crawl.</p>

</div></section>

```js
display(pager("p3"));
```
