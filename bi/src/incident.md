---
title: The incident
---

```js
import * as Plot from "@observablehq/plot";
import * as Inputs from "@observablehq/inputs";
import {html} from "htl";
import {load} from "./components/load.js";
import {INK, MUTED, LIGHT, PAPER, RULE, RED, DECISION, plotStyle} from "./components/theme.js";
import {pct, fmtDate, fmtDay, int} from "./components/format.js";
import {modelCard, tile, tableView} from "./components/modelCard.js";

const inc = await load(FileAttachment("data/incident_replay.csv").text());
const deliveries = await load(FileAttachment("data/gate_deliveries.csv").text());
const markets = await load(FileAttachment("data/markets.csv").text());
const marketOrder = markets.sort((a, b) => a.display_order - b.display_order).map((m) => m.market);
```

<p class="kicker">Why this project exists</p>

# The incident, replayed

<p class="lede">In the old pipeline, the weekly Micro and the monthly Macro deliveries read the same <b>shared,
mutable catalogue</b>: a table that every file import overwrote. Whichever file was imported last decided which crawl
a delivery served, so the same product on the same date could get two different prices. Here the old design is
replayed on the same files, next to the point-in-time design, and the difference is measured.</p>

```js
const wrong = inc.filter((d) => d.legacy_would_be_wrong);
const legacy = deliveries.filter((d) => d.dataset === "legacy_replay");
const marts = deliveries.filter((d) => d.dataset === "marts");
display(html`<div class="tiles">
  ${tile("Date × market cells replayed", int(inc.length))}
  ${tile("Where the old design is wrong", int(wrong.length), "wrong crawl, product list or prices", "alert")}
  ${tile("Reporting dates affected", new Set(wrong.map((d) => +d.as_of_date)).size)}
  ${tile("Old-design deliveries the gate blocks", legacy.filter((d) => d.gate_decision === "BLOCK").length, "point-in-time design: " + marts.filter((d) => d.gate_decision === "BLOCK").length, "alert")}
</div>`);
```

## Where the old catalogue would have served the wrong data

```js
const dates = [...new Set(inc.map((d) => +d.as_of_date))].sort((a, b) => a - b).map((t) => new Date(t));
display(Plot.plot({
  ...plotStyle, width: Math.max(width, 720), height: marketOrder.length * 24 + 70, marginLeft: 46, marginBottom: 46,
  x: {type: "band", domain: dates, tickFormat: fmtDay, label: null, tickRotate: -40, padding: 0.06},
  y: {domain: marketOrder, label: null, tickSize: 0, padding: 0.06},
  marks: [
    Plot.cell(inc, {x: "as_of_date", y: "market", fill: (d) => (d.legacy_would_be_wrong ? INK : LIGHT), tip: true,
      title: (d) => [`${d.market} · as of ${fmtDate(d.as_of_date)}`,
        d.legacy_would_be_wrong ? "OLD DESIGN WRONG" : "same result",
        `point-in-time serves the crawl of ${fmtDate(d.point_in_time_crawl_date)}`,
        `old catalogue serves the crawl of ${fmtDate(d.legacy_crawl_date)} (${d.legacy_file})`,
        `${d.n_price_differences} prices differ (${pct(d.share_prices_different, 1)}), ${d.n_missing_in_legacy} missing, ${d.n_extra_in_legacy} extra`].join("\n")}),
    Plot.text(wrong, {x: "as_of_date", y: "market", text: () => "×", fill: PAPER, fontSize: 13})
  ]
}));
display(html`<div class="legend"><span><i style="background:${INK}"></i>× old design wrong</span><span><i style="background:${LIGHT}"></i>same result</span>
  <span>blank: market not in scope that date (weekly dates cover 8 markets, month-ends 16)</span></div>`);
```

## The evidence, cell by cell

```js
display(Inputs.table(wrong.map((d) => ({date: d.as_of_date, market: d.market,
  "point-in-time crawl": d.point_in_time_crawl_date, "old design's crawl": d.legacy_crawl_date, "file that won": d.legacy_file,
  "prices differ": d.n_price_differences, share: d.share_prices_different, missing: d.n_missing_in_legacy, extra: d.n_extra_in_legacy})),
  {select: false, format: {date: fmtDate, "point-in-time crawl": fmtDate, "old design's crawl": fmtDate, share: (x) => pct(x, 1)}, layout: "auto", rows: 12}));
```

<figcaption>The "file that won" column names the import that left the old catalogue in that state: typically a file
re-exported under a later date while it still contained an earlier crawl.</figcaption>

## Would the delivery gate have caught it?

<p>The same gate, with the same 17 checks, run on both designs. Only the point-in-time design is ever published;
the old design is audited for comparison.</p>

```js
const rows = deliveries.map((d) => ({...d, design: d.dataset === "marts" ? "point-in-time (published)" : "old shared catalogue (replay)"}));
for (const scope of ["micro", "macro"]) {
  const s = rows.filter((d) => d.scope === scope);
  const ds = [...new Set(s.map((d) => +d.as_of_date))].sort((a, b) => a - b).map((t) => new Date(t));
  display(html`<h3>${scope === "micro" ? "Micro · weekly deliveries" : "Macro · month-end deliveries"}</h3>`);
  display(Plot.plot({
    ...plotStyle, width: Math.max(width, 720), height: 2 * 34 + 50, marginLeft: 230, marginBottom: 30,
    x: {type: "band", domain: ds, tickFormat: fmtDay, label: null, padding: 0.08},
    y: {domain: ["point-in-time (published)", "old shared catalogue (replay)"], label: null, tickSize: 0, padding: 0.1},
    color: DECISION,
    marks: [
      Plot.cell(s, {x: "as_of_date", y: "design", fill: "gate_decision", tip: true,
        title: (d) => `${d.design}\n${fmtDate(d.as_of_date)}: ${d.gate_decision}\n${d.checks_not_passing ?? "all checks passed"}`}),
      Plot.text(s, {x: "as_of_date", y: "design", text: "gate_decision", fill: (d) => (d.gate_decision === "PASS" ? INK : PAPER), fontSize: 10})
    ]
  }));
}
display(html`<div class="legend">${DECISION.domain.map((s, i) => html`<span><i style="background:${DECISION.range[i]}"></i>${s}</span>`)}</div>`);
```

```js
display(modelCard({
  question: "How often would the old shared catalogue have delivered the wrong crawl, product list or prices, and would anything have caught it?",
  decision: "Whether the redesign was worth it, measured instead of argued.",
  grain: "One row per (reporting date, market): which crawl each design serves, and how many products and prices disagree.",
  models: [
    {name: "qa_incident__legacy_vs_point_in_time", role: "the comparison, cell by cell (public, contract enforced)"},
    {name: "int_legacy__catalogue_replayed", role: "the old design, replayed: imports applied in file order to one mutable catalogue"},
    {name: "int_catalogue__as_of", role: "the new design: the latest eligible crawl on or before each date, from an append-only history"},
    {name: "mart_data_health__deliveries", role: "the gate's verdict on both designs"}
  ],
  guarantees: [
    "Killer test serves_latest_eligible_crawl runs on BOTH designs: it passes on the point-in-time catalogue and is expected to fail on the replay. That failure is what the incident was.",
    "Bronze is append-only (COPY INTO, one row per delivered line), so the replay sees exactly the files the old pipeline saw.",
    "The legacy dataset is audit-only in the gate: it is measured but can never be released."
  ],
  chart: "A date × market heatmap, because an incident has a 'when' and a 'where': the black cells show both at once, and the × marks them without relying on colour. The gate comparison puts the two designs on two rows of the same timeline, so a BLOCK on one row and a PASS above it read as cause and effect."
}));
```
