---
title: Micro · hero prices
---

```js
import * as Plot from "@observablehq/plot";
import * as Inputs from "@observablehq/inputs";
import {html} from "htl";
import {load} from "./components/load.js";
import {INK, MUTED, PAPER, RULE, PRICE_STATUS, plotStyle} from "./components/theme.js";
import {pct, money, fmtDate, fmtDay, int} from "./components/format.js";
import {modelCard, tile, tableView} from "./components/modelCard.js";

const hero = await load(FileAttachment("data/hero_prices_weekly.csv").text());
const markets = await load(FileAttachment("data/markets.csv").text());
const marketOrder = markets.filter((m) => m.is_in_micro_scope).sort((a, b) => a.display_order - b.display_order).map((m) => m.market);
const heroes = [...new Set(hero.map((d) => d.product_label))].sort();
const dates = [...new Set(hero.map((d) => +d.delivery_date))].sort((a, b) => b - a).map((t) => new Date(t));
```

<p class="kicker">Deliverable · weekly · every Tuesday</p>

# Micro: hero prices

<p class="lede">Eight hero products a client tracks, in the eight weekly markets. Each Tuesday's delivery is a
<b>complete grid</b>: a hero that could not be found still has its cell, so a missing price is visible instead of
silently absent.</p>

```js
const deliveryInput = Inputs.select(dates, {label: "Delivery", format: fmtDate, value: dates[0]});
const heroInput = Inputs.select(heroes, {label: "Hero (trend below)", value: heroes[0]});
const delivery = Generators.input(deliveryInput);
const heroPick = Generators.input(heroInput);
display(html`<div class="filters">${deliveryInput}${heroInput}</div>`);
```

```js
const week = hero.filter((d) => +d.delivery_date === +delivery);
const count = (s) => week.filter((d) => d.price_status === s).length;
display(html`<div class="tiles">
  ${tile("Cells in the grid", week.length, `${new Set(week.map((d) => d.pointer_id)).size} heroes × ${new Set(week.map((d) => d.market)).size} markets`)}
  ${tile("Price increases", count("price_increase"))}
  ${tile("Price decreases", count("price_decrease"))}
  ${tile("Not found or page error", count("not_found") + count("page_error"), "a page error is not a delisting")}
  ${tile("Stale or carried forward", week.filter((d) => d.is_stale_crawl || d.is_price_carried_forward).length, "older crawl, or last valid price reused")}
</div>`);
```

## Movement by delivery

```js
const byDate = dates.map((date) => {
  const rows = hero.filter((d) => +d.delivery_date === +date);
  return {date, up: rows.filter((d) => d.price_status === "price_increase").length,
          down: rows.filter((d) => d.price_status === "price_decrease").length};
}).sort((a, b) => a.date - b.date);
const bars = byDate.flatMap((d) => [{date: d.date, n: d.up, kind: "increases"}, {date: d.date, n: -d.down, kind: "decreases"}]);
display(Plot.plot({
  ...plotStyle, width: Math.max(width, 720), height: 170, marginLeft: 40,
  x: {type: "band", label: null, tickFormat: fmtDay, padding: 0.35},
  y: {label: "cells", grid: true, tickFormat: (n) => Math.abs(n)},
  color: {domain: ["increases", "decreases"], range: [INK, MUTED]},
  marks: [
    Plot.barY(bars, {x: "date", y: "n", fill: "kind", rx: 2, tip: true,
      title: (d) => `${fmtDate(d.date)}\n${Math.abs(d.n)} ${d.kind}`}),
    Plot.ruleY([0], {stroke: INK}),
    Plot.ruleX([delivery], {stroke: INK, strokeWidth: 1, strokeDasharray: "2 3", x: (d) => d})
  ]
}));
display(html`<div class="legend"><span><i style="background:${INK}"></i>price increases (up)</span>
  <span><i style="background:${MUTED}"></i>price decreases (down)</span><span>dashed: the selected delivery</span></div>`);
```

<figcaption>Number of hero × market cells whose price moved at each delivery. Most weeks nothing moves, which is what a
quiet luxury price list looks like; the weeks with bars are the ones worth opening.</figcaption>

## The grid, ${fmtDate(delivery)}

```js
function cellText(d) {
  const flag = d.is_stale_crawl || d.is_price_carried_forward ? "*" : "";
  switch (d.price_status) {
    case "price_increase":
    case "price_decrease": return pct(d.change_vs_previous_pct) + flag;
    case "unchanged": return "=" + flag;
    case "first_delivery": return "new" + flag;
    case "not_found": return "n/f";
    case "page_error": return "err";
    default: return "—";
  }
}
const dark = new Set(["price_increase", "price_decrease"]);
display(Plot.plot({
  ...plotStyle, width: Math.max(width, 720), height: heroes.length * 40 + 40, marginLeft: 250, marginTop: 30, padding: 0.08,
  x: {domain: marketOrder, axis: "top", label: null, tickSize: 0},
  y: {domain: heroes, label: null, tickSize: 0},
  color: {domain: PRICE_STATUS.domain, range: PRICE_STATUS.range},
  marks: [
    Plot.cell(week, {x: "market", y: "product_label", fill: "price_status", stroke: RULE, strokeWidth: 0.5,
      tip: true, title: (d) => [
        `${d.product_label} · ${d.market}`,
        `${PRICE_STATUS.label[d.price_status]}`,
        `price ${money(d.price_local, d.currency_code)} (previous ${money(d.previous_price_local, d.currency_code)})`,
        `change ${pct(d.change_vs_previous_pct, 2)}`,
        `crawl used ${d.crawl_date_used ? fmtDate(d.crawl_date_used) : "—"}${d.is_stale_crawl ? " · stale" : ""}${d.is_price_carried_forward ? " · price carried forward" : ""}`
      ].join("\n")}),
    Plot.text(week, {x: "market", y: "product_label", text: cellText, fill: (d) => (dark.has(d.price_status) ? PAPER : INK), fontSize: 11})
  ]
}));
display(html`<div class="legend">${PRICE_STATUS.domain.map((s, i) => html`<span><i style="background:${PRICE_STATUS.range[i]}"></i>${PRICE_STATUS.label[s]}</span>`)}
  <span>* stale crawl or carried-forward price</span></div>`);
display(tableView(Inputs.table(week, {select: false, 
  columns: ["product_label", "market", "price_status", "price_local", "currency_code", "previous_price_local", "change_vs_previous_pct", "crawl_date_used", "is_stale_crawl", "is_price_carried_forward"],
  header: {product_label: "hero", price_local: "price", currency_code: "ccy", previous_price_local: "previous", change_vs_previous_pct: "change", crawl_date_used: "crawl used", is_stale_crawl: "stale", is_price_carried_forward: "carried fwd"},
  format: {change_vs_previous_pct: (x) => pct(x, 2), crawl_date_used: (x) => (x ? fmtDate(x) : "—"), price_local: int, previous_price_local: int},
  rows: 20, layout: "auto"
})));
```

## ${heroPick}: twelve weeks, market by market

<p>Prices are in eight currencies, so they cannot share an axis. Each market is indexed to its first delivery
(= 100): the shape of the line is comparable, the level is not converted.</p>

```js
const series = hero.filter((d) => d.product_label === heroPick && d.price_local != null)
  .sort((a, b) => a.delivery_date - b.delivery_date);
const base = new Map();
for (const d of series) if (!base.has(d.market)) base.set(d.market, d.price_local);
const indexed = series.map((d) => ({...d, index: (100 * d.price_local) / base.get(d.market)}));
display(Plot.plot({
  ...plotStyle, width: Math.max(width, 720), height: 230, marginLeft: 40, marginBottom: 30,
  fx: {domain: marketOrder, label: null, padding: 0.12},
  x: {type: "utc", ticks: 3, tickFormat: "%b", label: null},
  y: {label: "index", grid: true, nice: true},
  marks: [
    Plot.frame({stroke: RULE}),
    Plot.ruleY([100], {stroke: MUTED}),
    Plot.ruleX([delivery], {stroke: MUTED, strokeDasharray: "2 3"}),
    Plot.lineY(indexed, {fx: "market", x: "delivery_date", y: "index", curve: "step-after", stroke: INK, strokeWidth: 2}),
    Plot.dot(indexed.filter((d) => d.price_status === "price_increase" || d.price_status === "price_decrease"),
      {fx: "market", x: "delivery_date", y: "index", r: 4, fill: INK, stroke: PAPER, strokeWidth: 2}),
    Plot.tip(indexed, Plot.pointerX({fx: "market", x: "delivery_date", y: "index",
      title: (d) => `${d.market} · ${fmtDate(d.delivery_date)}\n${money(d.price_local, d.currency_code)} · index ${d.index.toFixed(1)}\n${PRICE_STATUS.label[d.price_status]}`}))
  ]
}));
```

<figcaption>Dots mark the deliveries where the price moved. The dashed line is the delivery selected above.</figcaption>

```js
display(modelCard({
  question: "Did any hero product a client tracks change price this week, in which market, by how much, and can I trust each cell?",
  decision: "The weekly pricing alert a client acts on (match a competitor's increase, check a markdown).",
  grain: "One row per (delivery date, hero, weekly market): a complete grid of 8 × 8 = 64 cells per delivery. A hero that is missing keeps its row, with status not_found or page_error.",
  models: [
    {name: "pub_micro__hero_prices_weekly", role: "the released Micro grid: mart_micro__hero_prices_weekly filtered to gate-released deliveries"},
    {name: "mart_micro__hero_prices_weekly", role: "built from the point-in-time catalogue at each Tuesday, never from a shared mutable table"},
    {name: "pub_dim_market", role: "market names, currencies and display order"}
  ],
  guarantees: [
    "Primary key tested on (delivery_date, pointer_id, market); enforced contract on every column.",
    "Killer test: Micro and Macro are projections of the same point-in-time catalogue, so the same SKU on the same date has the same price in both.",
    "Gate checks before release: hero_grid_complete, hero_price_coverage, hero_stale_share, hero_carried_forward, hero_large_moves.",
    "not_found and page_error are separate statuses, so an unreadable page is never reported as a delisting."
  ],
  chart: "A status grid, because the question is 'which cell moved': rows and columns are the client's own mental model (hero × market). The words inside the cells carry the status, so it never depends on colour. The trend uses an index to 100 because eight currencies cannot share one axis, and converting them would add an FX assumption the data does not contain."
}));
```
