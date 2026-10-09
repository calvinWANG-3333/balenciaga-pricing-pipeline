---
title: Macro · categories
---

```js
import * as Plot from "@observablehq/plot";
import * as Inputs from "@observablehq/inputs";
import {html} from "htl";
import {load} from "./components/load.js";
import {INK, MUTED, RULE, plotStyle} from "./components/theme.js";
import {pct, money, fmtMonth, fmtDate, int} from "./components/format.js";
import {modelCard, tile, tableView} from "./components/modelCard.js";

const monthly = await load(FileAttachment("data/category_monthly.csv").text());
const globalRows = await load(FileAttachment("data/category_monthly_global.csv").text());
const markets = await load(FileAttachment("data/markets.csv").text());
const marketOrder = markets.sort((a, b) => a.display_order - b.display_order).map((m) => m.market);
const marketName = new Map(markets.map((m) => [m.market, m.market_name]));
const categories = ["Bags", "Small Leather Goods", "Shoes", "Accessories"];
const months = [...new Set(globalRows.map((d) => +d.report_month))].sort((a, b) => b - a).map((t) => new Date(t));
```

<p class="kicker">Deliverable · monthly · at month-end</p>

# Macro: categories

<p class="lede">The broad picture: per category and market, how many products are listed, the price range, and the
<b>like-for-like</b> change against the previous month-end. Like-for-like compares only products priced at both
month-ends, so a launch or a discontinued product never moves the number.</p>

```js
const monthInput = Inputs.select(months, {label: "Month", format: fmtMonth, value: months[0]});
const categoryInput = Inputs.select(categories, {label: "Category (price levels)", value: "Bags"});
const month = Generators.input(monthInput);
const category = Generators.input(categoryInput);
display(html`<div class="filters">${monthInput}${categoryInput}</div>`);
```

```js
const g = globalRows.filter((d) => +d.report_month === +month);
const byCat = new Map(g.map((d) => [d.macro_category, d]));
display(html`<div class="tiles">${categories.map((c) => {
  const d = byCat.get(c);
  return d ? tile(c, pct(d.market_weighted_lfl_change, 2), `product-weighted ${pct(d.product_weighted_lfl_change, 2)} · ${d.n_markets} markets`)
           : tile(c, "—", "no like-for-like basket");
})}</div>`);
```

<figcaption>The headline per category is the <b>market-weighted</b> like-for-like change: the mean of the 16 markets'
own changes, every market counting once. July is the first month-end in the data: with no previous month there is no
like-for-like basket, so it does not appear in the month list.</figcaption>

## Like-for-like change by market, ${fmtMonth(month)}

```js
const m = monthly.filter((d) => +d.report_month === +month && d.lfl_n_products > 0);
display(Plot.plot({
  ...plotStyle, width: Math.max(width, 720), height: 16 * 22 + 70, marginLeft: 46, marginRight: 12,
  fx: {domain: categories, label: null, padding: 0.1},
  y: {domain: marketOrder, label: null, tickSize: 0},
  x: {label: "like-for-like change", tickFormat: (x) => pct(x, 1), ticks: 3, grid: true, nice: true},
  marks: [
    Plot.frame({stroke: RULE}),
    Plot.ruleX([0], {stroke: INK}),
    Plot.barX(m, {fx: "macro_category", y: "market", x: "lfl_mean_change",
      fill: (d) => (d.lfl_mean_change < 0 ? MUTED : INK), insetTop: 3, insetBottom: 3, tip: true,
      title: (d) => `${marketName.get(d.market)} · ${d.macro_category}\nLFL ${pct(d.lfl_mean_change, 2)} over ${d.lfl_n_products} products\nbasket ratio ${pct(d.lfl_ratio_of_means, 2)} · ${pct(d.lfl_share_increased, 0)} of products increased`})
  ]
}));
display(html`<div class="legend"><span><i style="background:${INK}"></i>increase</span><span><i style="background:${MUTED}"></i>decrease</span></div>`);
display(tableView(Inputs.table(m, {select: false, 
  columns: ["macro_category", "market", "lfl_n_products", "lfl_mean_change", "lfl_ratio_of_means", "lfl_share_increased"],
  header: {macro_category: "category", lfl_n_products: "LFL products", lfl_mean_change: "LFL (mean)", lfl_ratio_of_means: "LFL (basket)", lfl_share_increased: "share up"},
  format: {lfl_mean_change: (x) => pct(x, 2), lfl_ratio_of_means: (x) => pct(x, 2), lfl_share_increased: (x) => pct(x, 0)},
  rows: 16, layout: "auto"
})));
```

## The mean-of-means question

<p>"How much did Bags move globally?" has more than one honest answer, and the model publishes both instead of
hiding the choice:</p>

```js
const rows = categories.map((c) => byCat.get(c)).filter(Boolean).map((d) => ({
  category: d.macro_category, market_weighted: d.market_weighted_lfl_change,
  product_weighted: d.product_weighted_lfl_change, gap: d.market_weighted_lfl_change - d.product_weighted_lfl_change,
  lowest: d.min_market_lfl_change, highest: d.max_market_lfl_change, top_market: d.market_with_highest_change
}));
display(Inputs.table(rows, {select: false, 
  header: {market_weighted: "market-weighted", product_weighted: "product-weighted", top_market: "highest market"},
  format: {market_weighted: (x) => pct(x, 2), product_weighted: (x) => pct(x, 2), gap: (x) => pct(x, 2), lowest: (x) => pct(x, 2), highest: (x) => pct(x, 2)},
  layout: "auto"
}));
```

<div class="aside">

**Market-weighted** = the mean of the markets' own like-for-like changes: France and Thailand count the same. It
answers "how did the brand move its price list, market by market". **Product-weighted** pools every product-market
pair: markets with a deeper assortment weigh more. It answers "how did the average listed product move". When the
two diverge, big and small markets moved differently, and that gap is itself the insight. Inside each market there
is the same choice again: `lfl_mean_change` (each product counts once, the headline) versus `lfl_ratio_of_means`
(the basket, where expensive products weigh more). A dbt unit test pins which one is the headline.

</div>

## Price levels: ${category}, ${fmtMonth(month)}

<p>Levels stay in local currency. Sixteen currencies cannot share an axis, and converting them would add an exchange
rate the data does not contain, so the levels are a table, not a chart.</p>

```js
const levels = monthly.filter((d) => +d.report_month === +month && d.macro_category === category)
  .sort((a, b) => marketOrder.indexOf(a.market) - marketOrder.indexOf(b.market))
  .map((d) => ({market: `${d.market} · ${marketName.get(d.market)}`, products: d.n_products, min: money(d.min_price, d.currency_code),
                median: money(d.median_price, d.currency_code), mean: money(d.mean_price, d.currency_code), max: money(d.max_price, d.currency_code),
                lfl: d.lfl_mean_change}));
display(Inputs.table(levels, {select: false, format: {lfl: (x) => pct(x, 2)}, header: {lfl: "LFL change"}, rows: 16, layout: "auto"}));
```

```js
display(modelCard({
  question: "How did each category's prices move this month, like-for-like, in every market and overall?",
  decision: "The monthly category review: which categories and markets carried the price increases.",
  grain: "One row per (report month, market, macro category), and one per (report month, macro category) for the global view.",
  models: [
    {name: "pub_macro__category_monthly", role: "levels and like-for-like change per market, released Macro deliveries only"},
    {name: "pub_macro__category_monthly_global", role: "the global headline: market-weighted and product-weighted, side by side"},
    {name: "pub_dim_market", role: "market names and display order"}
  ],
  guarantees: [
    "Like-for-like basket = products priced at both month-ends (lfl_n_products is published, so the basket is visible).",
    "dbt unit test pins the headline definition (mean of product changes, not the basket ratio).",
    "Gate checks before release: macro_grid_complete, lfl_match_rate, lfl_change_bounds, median_price_drift, cross_market_dispersion, global_reconciles_with_markets.",
    "Enforced contracts on both models; primary keys tested."
  ],
  chart: "Horizontal bars from a zero line, one panel per category, markets in the same order in every panel: the reader compares a market across categories by reading across, and a category across markets by reading down. Sign is carried by the bar's direction, not only its shade. The mean-of-means choice is a table, because the point is the two numbers side by side. Levels are a table because currencies cannot share an axis."
}));
```
