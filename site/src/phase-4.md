---
title: Phase 4 · Marts
---

```js
import {chapterHead, lineageSection, pager} from "./components/chapter.js";
display(chapterHead("p4", "Phase 3 built a catalogue that can be read at any date. This phase turns it into what people actually use: a small set of clean reference tables, the weekly report on 8 hero products and the monthly report on 4 categories. Each table states its exact shape in writing, and the build stops if the shape changes."));
```

<section class="block"><div class="label">01 Problem</div><div class="content">

Two reports with different shapes read the same history. Micro is 8 heroes × 8 countries every Tuesday; Macro is
4 categories × 16 countries at each month-end. Dashboards and an AI agent will read them too.

If each report decided for itself which crawl represents a country on a date, that rule would exist twice. Two
copies of one rule, drifting apart, is exactly how the original incident happened.

</div></section>

<section class="block"><div class="label">02 Decision</div><div class="content">

A **star schema** in `core/` for any question (facts you count, dimensions you filter by), plus **one mart per
deliverable** at the grain the client receives. The deliverable marts read only the point-in-time catalogue, and a
test proves they are pure projections of it. Every mart has an **enforced contract**.

| Model | Grain: one row per | Rows | Materialized |
|---|---|--:|---|
| `dim_product` | SKU | 2,001 | table |
| `dim_market` | market | 16 | table |
| `fct_price_observations` | accepted price reading | 198,653 | incremental (merge) |
| `fct_price_changes` | price change event | 6,681 | table |
| `fct_catalogue_as_of` | date × product-market | 360,700 | table |
| **`mart_micro__hero_prices_weekly`** | Tuesday × hero × weekly market | 832 | table |
| **`mart_macro__category_monthly`** | month × market × category | 192 | table |
| `mart_macro__category_monthly_global` | month × category | 8 | table |

<p class="cap">832 = 13 Tuesdays × 8 heroes × 8 markets. The grid is complete by construction: a hero that is missing keeps its row, with the status <code>not_found</code> or <code>page_error</code>.</p>

</div></section>

<section class="block"><div class="label">03 Rejected<span>The alternatives I considered, and why not.</span></div><div class="content">

| Alternative | Why not |
|---|---|
| Each mart picks its own latest crawl | The selection rule would live in two places. That duplication is the incident. |
| Incremental models everywhere | Only the 198k-row observations fact earns it. The other marts are small, and a full rebuild is simpler and always correct. |
| One like-for-like number per category | "Mean of product changes" and "ratio of means" answer different questions (+5.00 % vs +0.91 % on the unit-test case). Both are published; a unit test pins which one is the headline. |
| Drop heroes that were not found | A missing row looks like "no change". A page that failed to load is not a delisting, so the status says which one it was. |

</div></section>

<section class="block"><div class="label">04 dbt features<span>What each one does in this phase.</span></div><div class="content">

| Feature | What it does here |
|---|---|
| `contract: {enforced: true}` | On all 8 marts. A price that turns from decimal into float fails the build in dbt, before a dashboard sees it. |
| `incremental` · `merge` · lookback | `fct_price_observations` merges on `observation_id` and re-reads the last 35 days to pick up late corrections. |
| Generic test, inverted thresholds | `serves_latest_eligible_crawl` runs on both designs. On the replay of the old one, `error_if: "= 0"`: the build fails if it ever stops finding the incident. |
| Unit tests | Pin the like-for-like definition and the rule "the previous price skips weeks without a valid price". |
| `dbt_utils.equal_rowcount` | The incremental fact always has exactly as many rows as a full rebuild would. |
| Exposures | Declare the dashboards and the agent, so `dbt ls -s +exposure:…` answers "what breaks if I change this?". |

```yaml
# models/intermediate/_intermediate__models.yml, on int_legacy__catalogue_replayed
- serves_latest_eligible_crawl:
    name: killer_test_would_have_caught_the_legacy_incident
    arguments:
      crawl_date_column: legacy_crawl_date
    config:
      warn_if: "= 0"
      error_if: "= 0"    # fails the build if the replay ever stops showing the incident
```

</div></section>

```js
display(lineageSection("p4", await FileAttachment("lineage/lineage_p4.svg").text()));
```

<section class="block"><div class="label">06 Proof<span>Reference run, synthetic data, seed 42.</span></div><div class="content">

<div class="versus">
  <div><span class="micro">New design</span><b>0</b><p>date × market cells served from the wrong crawl</p></div>
  <div><span class="micro">Old design, replayed</span><b>10</b><p>18 Aug × 2 markets, 15 Sep × 8 markets: exactly the two incidents</p></div>
</div>

| Category · Sep vs Aug | Market-weighted | Product-weighted | Highest market |
|---|--:|--:|--:|
| Bags | +5.24 % | +5.26 % | +6.96 % JPN |
| Small Leather Goods | +4.91 % | +4.94 % | +6.55 % JPN |
| Accessories | +0.43 % | +0.43 % | +0.56 % JPN |
| Shoes | −0.04 % | −0.04 % | 0.00 % |

<p class="cap">The generator planted a +5 to 8 % increase on bags and leather goods on 7 Sep. The marts recover it end to end, through duplicated files, stale re-deliveries, partial crawls and currency errors. Shoes stay flat, as generated.</p>

</div></section>

```js
display(pager("p4"));
```
