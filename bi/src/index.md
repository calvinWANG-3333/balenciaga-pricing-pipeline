---
title: Overview
---

```js
import {html} from "htl";
import {load} from "./components/load.js";
import {fmtDate, int} from "./components/format.js";
import {modelCard, tile} from "./components/modelCard.js";

const manifest = await FileAttachment("data/snapshot_manifest.json").json();
const released = await load(FileAttachment("data/released_deliveries.csv").text());
const deliveries = await load(FileAttachment("data/gate_deliveries.csv").text());
const hero = await load(FileAttachment("data/hero_prices_weekly.csv").text());
const changes = await load(FileAttachment("data/price_changes.csv").text());
```

<p class="kicker">Balenciaga pricing pipeline · BI layer</p>

# What the clients receive, and why it can be trusted

<p class="lede">Six pages on the deliverables of a luxury price monitor: the weekly <b>Micro</b> grid of hero products,
the monthly <b>Macro</b> category statistics, the price changes behind them, the <b>incident</b> the project was built
to fix, and the <b>delivery gate</b> that decides what is released. Every number here was computed upstream, in dbt.
This site only filters and draws.</p>

```js
const micro = released.filter((d) => d.scope === "micro").length;
const macro = released.filter((d) => d.scope === "macro").length;
const blockedLegacy = deliveries.filter((d) => d.dataset === "legacy_replay" && d.gate_decision === "BLOCK").length;
const heroes = new Set(hero.map((d) => d.pointer_id)).size;
const heroMarkets = new Set(hero.map((d) => d.market)).size;
display(html`<div class="tiles">
  ${tile("Micro deliveries released", micro, "weekly, every Tuesday")}
  ${tile("Macro deliveries released", macro, "monthly, at month-end")}
  ${tile("Hero products tracked", heroes, `in ${heroMarkets} weekly markets`)}
  ${tile("Price changes observed", int(changes.length), "events, all markets")}
  ${tile("Old-design deliveries blocked", blockedLegacy, "by the gate, on the replay", "alert")}
</div>`);
```

## Where this data comes from

```js
const src = manifest.source;
display(html`<p>Snapshot exported on <b>${fmtDate(new Date(manifest.exported_at))}</b> from
<b>${src.schema_prefix === "(production)" ? "production" : src.schema_prefix}</b> (${src.backend}),
at commit <code>${src.git_sha}</code>: ${Object.keys(manifest.tables).length} tables,
${manifest.released_deliveries} released deliveries. The export reads <b>only public dbt models</b> and refuses to run
if the published layer contains a delivery the gate has not released.</p>`);
```

<div class="aside">

**Why a snapshot and not a live connection.** The site is static (GitHub Pages): it is rebuilt from files in the
repository, so it builds the same way for anyone, costs nothing, and never depends on a warehouse being awake.
The manifest above ties every number to a dbt run.

</div>

## The pages

<div class="pages">
  <a href="./micro"><b>Micro</b><span>Did any tracked hero change price this week, where, and by how much?</span></a>
  <a href="./macro"><b>Macro</b><span>How did each category move this month, like-for-like, by market and overall?</span></a>
  <a href="./price-changes"><b>Price changes</b><span>What moved, where, when, and by how much?</span></a>
  <a href="./incident"><b>The incident</b><span>How often would the old shared catalogue have served the wrong prices?</span></a>
  <a href="./data-health"><b>Data health</b><span>Was every delivery audited, what was flagged, and what was released?</span></a>
</div>

```js
display(modelCard({
  question: "Can a client trust what this site shows?",
  decision: "Whether to use these numbers at all. The answer must be visible before any chart.",
  grain: "One row per released delivery (scope, as_of_date), plus one manifest per snapshot.",
  models: [
    {name: "pub_released_deliveries", role: "the publish switch: a delivery exists here only once the gate released it"},
    {name: "mart_data_health__deliveries", role: "the gate's latest verdict on every delivery, released or not"}
  ],
  guarantees: [
    "The BI snapshot is exported from public models only (access: public, enforced contracts, documented columns).",
    "The export refuses to run if a Micro or Macro delivery date is not in pub_released_deliveries.",
    "dbt test assert_no_blocked_delivery_is_published: a BLOCKed delivery can never appear in the published layer."
  ],
  chart: "No chart: the overview leads with five stat tiles and the provenance of the data, because the first question is whether to trust it."
}));
```
