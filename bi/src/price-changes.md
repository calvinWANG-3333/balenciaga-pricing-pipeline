---
title: Price changes
---

```js
import * as Plot from "@observablehq/plot";
import * as Inputs from "@observablehq/inputs";
import {html} from "htl";
import {median} from "d3";
import {load} from "./components/load.js";
import {INK, MUTED, RULE, plotStyle} from "./components/theme.js";
import {pct, money, fmtDate, fmtDay, int} from "./components/format.js";
import {modelCard, tile, tableView} from "./components/modelCard.js";

const changes = await load(FileAttachment("data/price_changes.csv").text());
const products = await load(FileAttachment("data/products.csv").text());
const markets = await load(FileAttachment("data/markets.csv").text());
const marketOrder = markets.sort((a, b) => a.display_order - b.display_order).map((m) => m.market);
const productName = new Map(products.map((p) => [p.sku, p.product_name]));
const categories = ["Bags", "Small Leather Goods", "Shoes", "Accessories"];
```

<p class="kicker">Events · every crawl</p>

# Price changes

<p class="lede">Every time a product's price differs from its previous price in the same market, that is one event.
Events come from the SCD2 price history: each new price period after the first one is a change.</p>

```js
const marketInput = Inputs.select(["All markets", ...marketOrder], {label: "Market"});
const categoryInput = Inputs.select(["All categories", ...categories, "Out of Macro scope"], {label: "Category"});
const market = Generators.input(marketInput);
const category = Generators.input(categoryInput);
display(html`<div class="filters">${marketInput}${categoryInput}</div>`);
```

```js
const f = changes.filter((d) =>
  (market === "All markets" || d.market === market) &&
  (category === "All categories" || (category === "Out of Macro scope" ? d.macro_category == null : d.macro_category === category)));
const up = f.filter((d) => d.change_direction === "increase");
const down = f.filter((d) => d.change_direction === "decrease");
display(html`<div class="tiles">
  ${tile("Price changes", int(f.length), `${market.toLowerCase()} · ${category.toLowerCase()}`)}
  ${tile("Increases", int(up.length), up.length ? `median ${pct(median(up, (d) => d.change_pct), 1)}` : "")}
  ${tile("Decreases", int(down.length), down.length ? `median ${pct(median(down, (d) => d.change_pct), 1)}` : "")}
  ${tile("Products affected", int(new Set(f.map((d) => d.object_id)).size), "product-market pairs")}
</div>`);
```

## Changes per crawl

```js
const crawls = [...new Set(changes.map((d) => +d.changed_on_crawl_date))].sort((a, b) => a - b).map((t) => new Date(t));
const counts = crawls.flatMap((date) => {
  const day = f.filter((d) => +d.changed_on_crawl_date === +date);
  return [{date, kind: "increases", n: day.filter((d) => d.change_direction === "increase").length},
          {date, kind: "decreases", n: -day.filter((d) => d.change_direction === "decrease").length}];
});
display(Plot.plot({
  ...plotStyle, width: Math.max(width, 720), height: 240, marginLeft: 50,
  x: {type: "band", domain: crawls, tickFormat: fmtDay, label: null, padding: 0.35},
  y: {label: "events", grid: true, tickFormat: (n) => int(Math.abs(n))},
  color: {domain: ["increases", "decreases"], range: [INK, MUTED]},
  marks: [
    Plot.barY(counts, {x: "date", y: "n", fill: "kind", rx: 2, tip: true, title: (d) => `crawl of ${fmtDate(d.date)}\n${int(Math.abs(d.n))} ${d.kind}`}),
    Plot.ruleY([0], {stroke: INK}),
    Plot.text(counts.filter((d) => d.n > 500), {x: "date", y: "n", text: (d) => int(d.n), dy: -8, fill: INK, fontSize: 11})
  ]
}));
display(html`<div class="legend"><span><i style="background:${INK}"></i>increases (up)</span><span><i style="background:${MUTED}"></i>decreases (down)</span></div>`);
display(tableView(Inputs.table(counts.map((d) => ({crawl: d.date, kind: d.kind, events: Math.abs(d.n)})), {select: false, format: {crawl: fmtDate}, layout: "auto"})));
```

<figcaption>One bar per crawl, increases above the line and decreases below it, on a single axis. The two tall bars are
<b>one</b> September price increase (about +6 %, mostly bags and small leather goods) seen twice: on 7 Sep in the 8
weekly-crawled markets, and on 28 Sep when the monthly crawl reaches the other 8 markets. Crawl cadence decides
<i>when</i> a change becomes visible, which is why Micro (weekly markets) and Macro (all markets) can only agree when
they read the same point-in-time history. The first crawl has no change by construction.</figcaption>

## How big are the moves?

```js
const sized = f.map((d) => ({...d, cat: d.macro_category ?? "Out of Macro scope"}));
const catDomain = [...categories, "Out of Macro scope"].filter((c) => sized.some((d) => d.cat === c));
display(Plot.plot({
  ...plotStyle, width: Math.max(width, 720), height: catDomain.length * 46 + 50, marginLeft: 150,
  y: {domain: catDomain, label: null, tickSize: 0},
  x: {label: "change", tickFormat: (x) => pct(x, 0), grid: true},
  marks: [
    Plot.ruleX([0], {stroke: INK}),
    Plot.tickX(sized, {x: "change_pct", y: "cat", stroke: (d) => (d.change_pct < 0 ? MUTED : INK), strokeOpacity: 0.18}),
    Plot.dot(sized, Plot.groupY({x: "median"}, {x: "change_pct", y: "cat", r: 5, fill: INK, stroke: "#E4E4E1", strokeWidth: 2,
      tip: true, title: (d) => `median change`})),
  ]
}));
```

<figcaption>Each tick is one event; the dot is the median. Luxury price lists move in steps (a few percent up, rare
markdowns), so the ticks cluster instead of spreading.</figcaption>

## The latest changes

```js
const latest = [...f].sort((a, b) => b.changed_on_crawl_date - a.changed_on_crawl_date || Math.abs(b.change_pct) - Math.abs(a.change_pct))
  .slice(0, 200).map((d) => ({crawl: d.changed_on_crawl_date, market: d.market, product: productName.get(d.sku) ?? d.sku,
    category: d.macro_category ?? "—", before: money(d.price_before, d.currency_code), after: money(d.price_after, d.currency_code), change: d.change_pct}));
display(Inputs.table(latest, {select: false, format: {crawl: fmtDate, change: (x) => pct(x, 1)}, rows: 15, layout: "auto"}));
```

```js
display(modelCard({
  question: "What moved, where, when, and by how much?",
  decision: "Explaining a Micro or Macro number: which individual products produced it.",
  grain: "One row per price change event: a product-market and the crawl where its new price first appeared.",
  models: [
    {name: "pub_fct_price_changes", role: "change events up to the latest released delivery"},
    {name: "pub_dim_product", role: "product names (the fact keeps only the SKU)"},
    {name: "pub_dim_market", role: "market names and order"}
  ],
  guarantees: [
    "Built from SCD2 price periods (int_prices__historized): periods never overlap, tested.",
    "Only accepted observations: quarantined lines, blocked deliveries and price-scale outliers never create a change.",
    "macro_category is denormalized from the product dimension, so the semantic layer and this page slice by category without a join.",
    "Gate checks before release: price_decrease_share, price_reversion_share (an A→B→A pattern is the fingerprint of an old crawl being served)."
  ],
  chart: "Increases and decreases are mirrored around one zero line instead of stacked, so both can be read from the same baseline. Sizes are a strip of ticks with a median dot, because the shape of the distribution (tight steps, rare markdowns) is the point, and a mean would hide it."
}));
```
