---
title: Phase 5a · Delivery gate
---

```js
import {chapterHead, lineageSection, pager} from "./components/chapter.js";
display(chapterHead("p5a", "Phase 4 built the reports. This phase adds an inspector that compares each weekly or monthly delivery with the ones before it, and holds back any delivery that looks wrong before a client can see it. Tried on a copy of the old system, it stops exactly the two deliveries that went wrong in real life, and nothing else."));
```

<section class="block"><div class="label">01 Problem</div><div class="content">

dbt tests check rules that must hold in every build: unique keys, no missing values, the right types, rows
conserved. They catch the problems I could foresee.

The production incident was a different kind of problem. Every row was valid, and the batch as a whole was
wrong. In August, half-finished crawls overwrote the catalogue of two markets. In September, an August file
was served again under a September date.

A factory inspector who measures each part against the drawing would pass all of it. Someone has to compare
this batch with the previous ones before it ships. Nothing in the pipeline did that yet, and a check that
only runs after a client has the file comes too late.

</div></section>

<section class="block"><div class="label">02 Decision</div><div class="content">

**Write-audit-publish.** Write the output where nobody can see it, audit it, then publish it. A Python
**delivery gate** does the audit, with 17 checks that run as SQL inside the warehouse.

| Step | Who | What happens |
|---|---|---|
| Write | `dbt build` | Every delivery lands in the marts. BI does not read the marts. |
| Audit | `python -m qa.gate audit` | The checks in `qa/checks.yml` run on each unreleased delivery. Every result is appended to `ops.qa_check_results`. |
| Publish | the gate | If no blocking check fails, one row goes into `ops.delivery_releases`. The `pub_*` views show that delivery from that moment. |

Each check has a **severity**. `block` stops the release. `warn` lets the delivery out with a flag, because a
real price campaign looks exactly like an anomaly and the client should still get it.

Every comparison uses the **last accepted delivery** as its baseline. A blocked week never becomes the
reference, so the first correct week after an incident is not blocked for jumping back to normal.

<p class="cap">Python only orchestrates: the calendar, the baselines, the decision, the release and the record. The measurements stay in SQL, and Python receives one small number per check and subject, never the data.</p>

</div></section>

<section class="block"><div class="label">03 Rejected<span>The alternatives I considered, and why not.</span></div><div class="content">

| Alternative | Why not |
|---|---|
| More dbt tests instead of a gate | A test passes or fails a build. A release needs a delivery calendar, baselines from history, one decision over many checks, a durable record and the release itself. That is orchestration. |
| Export to Excel and run a script on the file | Checks should run where the data lives. Their results should be stored as data, and they should decide what gets published. |
| Published tables, copied from the marts | A release would need a dbt run, and a copy can drift. A view is the mart, filtered, so a release takes effect at once. |
| Compare with the previous calendar delivery | The first version did this. On the replay, the correct week of 2026-09-22 then looked wrong, because its prices jumped back. A unit test now pins the rule. |
| Block every anomaly | The September price campaign trips the anomaly rule, and it is real. So `price_change_share_anomaly` can only warn. |

</div></section>

<section class="block"><div class="label">04 dbt features<span>What each one does in this phase.</span></div><div class="content">

| Feature | What it does here |
|---|---|
| `on-run-start` hook | Runs `create_ops_tables()` before every dbt command: `CREATE TABLE IF NOT EXISTS`. dbt guarantees the two ops tables exist and never rebuilds them, which would erase the history. |
| Append-only ops tables | On Databricks, `qa_check_results` and `delivery_releases` are Delta tables with `delta.appendOnly = true`: an audit log nobody can edit after the fact. |
| Sources | dbt reads the gate's writes back as the `ops` source. |
| Published views | 8 views. `pub_released_deliveries` lists what the gate let out, and each `pub_*` view filters its mart to it. |
| Health mart as a view | `mart_data_health__deliveries`: one row per dataset, scope and delivery. A view, because the gate writes after dbt runs. |
| Singular test | `assert_no_blocked_delivery_is_published`: nothing blocked is published without a forced release and a reason. |
| Checks-as-code (Python gate) | Each check in `qa/checks.yml` has an id, one of 5 quality dimensions, a severity, rules and SQL. A new threshold is a reviewed pull request. |

```yaml
# qa/checks.yml
- id: price_reversion_share
  dimension: plausibility
  severity: block
  scopes: [micro, macro]
  datasets: [marts, legacy_replay]
  description: >
    Share of products whose price changed since the previous delivery AND went back exactly to the
    price of the delivery before that (A -> B -> A). Real prices almost never do this in a week; an
    old crawl served again does it to every product that changed. This is the signature of the
    production incident.
  rules: {warn_above: 0.01, fail_above: 0.05}
```

</div></section>

```js
display(lineageSection("p5a", await FileAttachment("lineage/lineage_p5a.svg").text()));
```

<section class="block"><div class="label">06 Proof<span>Reference run, local Spark, seed 42.</span></div><div class="content">

<div class="versus">
  <div><span class="micro">New design</span><b>0</b><p>of 16 deliveries blocked. 5 went out with a warning, each a real event.</p></div>
  <div><span class="micro">Old design, replayed</span><b>2</b><p>blocked: 18 Aug (KOR, HKG catalogues halved) and 15 Sep (8 markets served an August crawl). Nothing else.</p></div>
</div>

| | Marts (new design) | Replay of the old design |
|---|--:|--:|
| Deliveries audited | 16 (13 Micro, 3 Macro) | 16 |
| PASS / WARN / BLOCK | 11 / 5 / **0** | 13 / 1 / **2** |
| Check results stored | 690 | 574 |

<p class="cap">On the replay, <code>product_count_change</code> is −55 % in KOR and HKG on 18 Aug. On 15 Sep, <code>price_reversion_share</code> is 25 to 26 % in all eight weekly markets; on every real delivery it is 0 %. The 5 warnings on the new design include the September price campaign (25.7 % of prices changed, against a usual 0.2 %) and a −11 % markdown on one hero sneaker. <code>dbt build</code>: 162 pass, 0 errors. pytest: all 15 tests of the gate pass.</p>

</div></section>

```js
display(pager("p5a"));
```
