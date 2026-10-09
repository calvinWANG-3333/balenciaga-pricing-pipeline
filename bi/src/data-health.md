---
title: Data health
---

```js
import * as Plot from "@observablehq/plot";
import * as Inputs from "@observablehq/inputs";
import {html} from "htl";
import {load} from "./components/load.js";
import {INK, PAPER, RULE, DECISION, CHECK_STATUS, plotStyle} from "./components/theme.js";
import {fmtDate, fmtDay, int} from "./components/format.js";
import {modelCard, tile, tableView} from "./components/modelCard.js";

const deliveries = await load(FileAttachment("data/gate_deliveries.csv").text());
const checks = await load(FileAttachment("data/gate_check_results.csv").text());
```

<p class="kicker">Write · audit · publish</p>

# Data health

<p class="lede">dbt builds every delivery; a delivery gate then measures it against 17 checks and decides: <b>PASS</b>
and <b>WARN</b> are released, <b>BLOCK</b> is not. This page is that audit trail: one row per delivery, and behind it
one result per check.</p>

```js
const datasetInput = Inputs.radio(new Map([["Published design (marts)", "marts"], ["Old design, replayed", "legacy_replay"]]),
  {label: "Dataset", value: "marts"});
const scopeInput = Inputs.radio(new Map([["Micro · weekly", "micro"], ["Macro · month-end", "macro"]]), {label: "Scope", value: "micro"});
const dataset = Generators.input(datasetInput);
const scope = Generators.input(scopeInput);
display(html`<div class="filters">${datasetInput}${scopeInput}</div>`);
```

```js
const ds = deliveries.filter((d) => d.dataset === dataset && d.scope === scope).sort((a, b) => a.as_of_date - b.as_of_date);
const n = (x) => ds.filter((d) => d.gate_decision === x).length;
display(html`<div class="tiles">
  ${tile("Deliveries audited", ds.length)}
  ${tile("PASS", n("PASS"))}
  ${tile("WARN", n("WARN"), "released, with a note")}
  ${tile("BLOCK", n("BLOCK"), "never released", n("BLOCK") ? "alert" : "")}
  ${tile("Released", dataset === "marts" ? ds.filter((d) => d.is_published).length : "—", dataset === "marts" ? "visible to clients" : "the replay is audit-only")}
</div>`);
```

## Verdict per delivery

```js
const dates = ds.map((d) => d.as_of_date);
display(Plot.plot({
  ...plotStyle, width: Math.max(width, 720), height: 110, marginLeft: 20, marginBottom: 30,
  x: {type: "band", domain: dates, tickFormat: fmtDay, label: null, padding: 0.08},
  y: {domain: ["verdict"], axis: null},
  color: DECISION,
  marks: [
    Plot.cell(ds, {x: "as_of_date", y: () => "verdict", fill: "gate_decision", tip: true,
      title: (d) => `${fmtDate(d.as_of_date)}: ${d.gate_decision}${d.is_published ? " · released" : ""}\n${d.n_pass} pass · ${d.n_warn} warn · ${d.n_fail} fail · ${d.n_skip} skip\n${d.checks_not_passing ?? "all checks passed"}`}),
    Plot.text(ds, {x: "as_of_date", y: () => "verdict", text: "gate_decision", fill: (d) => (d.gate_decision === "PASS" ? INK : PAPER), fontSize: 10})
  ]
}));
display(html`<div class="legend">${DECISION.domain.map((s, i) => html`<span><i style="background:${DECISION.range[i]}"></i>${s}</span>`)}</div>`);
```

## Every check, every delivery

```js
const rank = {skip: 0, pass: 1, warn: 2, fail: 3, block: 4};
const sel = checks.filter((d) => d.dataset === dataset && d.scope === scope);
const worst = new Map();
for (const d of sel) {
  const s = d.status === "fail" && d.severity === "block" ? "block" : d.status;
  const k = `${d.check_id}|${+d.as_of_date}`;
  const cur = worst.get(k);
  if (!cur || rank[s] > rank[cur.s]) worst.set(k, {check_id: d.check_id, dimension: d.dimension, as_of_date: d.as_of_date, s, n: 0});
  worst.get(k).n += d.status === "pass" || d.status === "skip" ? 0 : 1;
}
const cells = [...worst.values()];
const order = ["timeliness", "completeness", "validity", "plausibility", "consistency"];
const checkIds = [...new Map(cells.map((d) => [d.check_id, d.dimension])).entries()]
  .sort((a, b) => order.indexOf(a[1]) - order.indexOf(b[1]) || a[0].localeCompare(b[0])).map(([id]) => id);
const dimOf = new Map(cells.map((d) => [d.check_id, d.dimension]));
display(Plot.plot({
  ...plotStyle, width: Math.max(width, 720), height: checkIds.length * 26 + 60, marginLeft: 330, marginBottom: 30,
  x: {type: "band", domain: dates, tickFormat: fmtDay, label: null, padding: 0.06},
  y: {domain: checkIds, label: null, tickSize: 0, padding: 0.06, tickFormat: (id) => `${dimOf.get(id)} · ${id}`},
  color: {domain: CHECK_STATUS.domain, range: CHECK_STATUS.range},
  marks: [
    Plot.cell(cells, {x: "as_of_date", y: "check_id", fill: "s", stroke: RULE, strokeWidth: 0.5, tip: true,
      title: (d) => `${d.check_id} (${d.dimension})\n${fmtDate(d.as_of_date)}: ${d.s === "block" ? "FAIL, blocking" : d.s}${d.n ? ` · ${d.n} subject(s)` : ""}`}),
    Plot.text(cells, {x: "as_of_date", y: "check_id", text: (d) => CHECK_STATUS.label[d.s],
      fill: (d) => (d.s === "fail" || d.s === "block" ? PAPER : INK), fontSize: 11})
  ]
}));
display(html`<div class="legend">
  <span><i style="background:${CHECK_STATUS.range[0]}"></i>· skip (not enough history)</span>
  <span><i style="background:${CHECK_STATUS.range[1]}"></i>✓ pass</span>
  <span><i style="background:${CHECK_STATUS.range[2]}"></i>! warn</span>
  <span><i style="background:${CHECK_STATUS.range[3]}"></i>× fail, non-blocking</span>
  <span><i style="background:${CHECK_STATUS.range[4]}"></i>× fail of a blocking check</span></div>`);
```

<figcaption>Rows are grouped by data-quality dimension: timeliness, completeness, validity, plausibility, consistency. A
cell shows the worst result across the check's subjects (a market, a category, a hero). The only red on this site is a
blocking failure.</figcaption>

## What did not pass, and why

```js
const issues = sel.filter((d) => d.status === "warn" || d.status === "fail")
  .sort((a, b) => a.as_of_date - b.as_of_date || a.check_id.localeCompare(b.check_id))
  .map((d) => ({delivery: d.as_of_date, check: d.check_id, severity: d.severity, status: d.status, subject: d.subject,
                observed: d.observed, warn_if: d.warn_rule ?? "", fail_if: d.fail_rule ?? "", message: d.message}));
display(issues.length ? Inputs.table(issues, {select: false, format: {delivery: fmtDate, observed: (x) => (x == null ? "—" : +x.toFixed(4))}, layout: "auto", rows: 14})
  : html`<p>Every check passed or was skipped for this selection.</p>`);
```

```js
display(modelCard({
  question: "Was every delivery audited before release, what did the audit flag, and what reached clients?",
  decision: "Release or hold a delivery; write the client note that explains a WARN.",
  grain: "One row per delivery (dataset, scope, as_of_date); behind it one row per (delivery, check, subject) from the latest gate run.",
  models: [
    {name: "mart_data_health__deliveries", role: "the latest verdict per delivery and whether it is released"},
    {name: "mart_data_health__check_results", role: "each check's result behind the verdict: observed value, rule, message"},
    {name: "stg_ops__qa_check_results", role: "the gate's append-only audit log (written by Python, read by dbt)"}
  ],
  guarantees: [
    "The gate's tables are append-only Delta tables (delta.appendOnly): the audit trail cannot be rewritten.",
    "Checks are code (qa/checks.yml): 17 checks, each with a dimension, a severity and its rules, reviewed in pull requests.",
    "The baseline of every comparison is the last ACCEPTED delivery, so one bad delivery cannot poison the next comparison.",
    "dbt test assert_no_blocked_delivery_is_published; both marts are public, contract-enforced views (always current after a gate run)."
  ],
  chart: "A checks × deliveries grid, because an auditor reads it two ways: down a column (what went wrong with this delivery) and along a row (is this check noisy over time). Each state has a symbol as well as a shade, and red is spent only on the one state that stops a release."
}));
```
