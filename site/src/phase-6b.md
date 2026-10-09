---
title: Phase 6b · Lineage + snapshot
---

```js
import {chapterHead, lineageSection, pager} from "./components/chapter.js";
display(chapterHead("p6b", "Project diagrams are usually drawn once by hand and then go out of date. Here a script redraws the map of which table feeds which straight from the project's history, one picture per phase, so the diagrams can never disagree with the code. The data behind the dashboards is copied into plain files, and only from the part of the database that has passed every quality check."));
```

<section class="block"><div class="label">01 Problem</div><div class="content">

This site needs two things from the project: pictures of the DAG, and data for the BI pages. Both are easy to make by hand, and hand-made copies drift away from the code.

dbt docs only shows today's graph. A portfolio needs the graph as it was when each phase closed. In Phase 4 the exposures read the marts directly; in Phase 5a they were repointed to the published views. A screenshot of today cannot show that change.

The site is static, so its data must be exported to files. If the export could read any table, a dashboard could show a delivery the gate never released, or depend on an internal model that changes without warning. The data-health page also needed each check's result per delivery, and that detail lived only in a staging model.

</div></section>

<section class="block"><div class="label">02 Decision</div><div class="content">

**Two small tools, both built on artifacts dbt already produces.** The pictures come from dbt's manifest. The BI data comes from the published layer.

| Tool | Reads | Writes |
|---|---|---|
| `tools/lineage/collect.py` | the dbt project at a git commit, or today's manifest | `tools/lineage/graphs/<phase>.json` |
| `tools/lineage/render.py` | the graphs + `phases.yml` | `site/src/lineage/lineage_full.svg`, `lineage_<phase>.svg` |
| `tools/snapshot/export.py` | the warehouse's public models | 10 CSV files + `snapshot_manifest.json` in `bi/src/data/` |

Each picture is compiled from the merge commit that closed its phase: `git archive`, `dbt deps`, `dbt parse`. The layout is computed once, on the union of all phases, so a model never moves between pictures. A model sits one column right of its right-most parent, so every arrow points right, and a test asserts it.

The export checks three things before it writes anything: every model is `access: public`, at least one delivery is released, and every Micro and Macro date is a released delivery. For the per-check detail I added a public mart, `mart_data_health__check_results`.

</div></section>

<section class="block"><div class="label">03 Rejected<span>The alternatives I considered, and why not.</span></div><div class="content">

| Alternative | Why not |
|---|---|
| Hand-drawn diagrams or screenshots | They drift from the code. The renderer is deterministic, so a changed SVG in a pull request always means a changed DAG. |
| The lineage tab of dbt docs | It only shows today. The history of the project is the point of the site. |
| Today's graph with later parts greyed out | It would not be true. The Phase 4 exposures read the marts; Phase 5a repointed them. Only a graph compiled from that commit shows it. |
| Point BI at `stg_ops__qa_check_results` | BI must not read a staging model. A public mart with a contract gives the page a governed interface. |
| Export the point-in-time catalogue | 360,000 rows, and no page needs it row by row. |

</div></section>

<section class="block"><div class="label">04 dbt features<span>What each one does in this phase.</span></div><div class="content">

| Feature | What it does here |
|---|---|
| `manifest.json` from `dbt parse` | The compiled graph: every node and its `depends_on` edges. Both tools read it. |
| `access: public` in the manifest | The export refuses any model that is not public. |
| Enforced contracts | The CSV columns are read from the contracts, so the file headers are the contract. |
| Doc blocks | Every column of the new mart is documented in `models/docs/public_columns.md`. |
| `unique_combination_of_columns` + `accepted_values` | Primary key on (dataset, scope, as_of_date, check_id, subject); `status` limited to known values. |
| Exposure `depends_on` | `data_health_page` now depends on the new mart. |
| Evaluator exception | Widened from one model to the `mart_data_health__%` family: these views read a log the gate writes after dbt runs. |

```yaml
# dbt/models/marts/_marts__models.yml
  - name: mart_data_health__check_results
    description: >
      Grain: one row per (dataset, scope, delivery date, check, subject), from the latest gate run on each
      delivery. The detail behind mart_data_health__deliveries: what each check measured and against which rule.
    config:
      access: public          # read by the data-health page and the triage agent
      contract: {enforced: true}
```

</div></section>

```js
display(lineageSection("p6b", await FileAttachment("lineage/lineage_p6b.svg").text()));
```

<section class="block"><div class="label">06 Proof<span>The production snapshot at commit f348323, and the local test run.</span></div><div class="content">

<div class="versus">
  <div><span class="micro">Lineage pictures</span><b>9</b><p>the full graph plus one per phase, p2 to p6c, each compiled from git</p></div>
  <div><span class="micro">Snapshot tables</span><b>10</b><p>public models only, about 1.8 MB, exported from production</p></div>
</div>

| File | Model | Rows |
|---|---|--:|
| `hero_prices_weekly.csv` | `pub_micro__hero_prices_weekly` | 832 |
| `category_monthly.csv` | `pub_macro__category_monthly` | 192 |
| `price_changes.csv` | `pub_fct_price_changes` | 6,681 |
| `released_deliveries.csv` | `pub_released_deliveries` | 16 |
| `gate_check_results.csv` | `mart_data_health__check_results` (new) | 1,264 |

<p class="cap">Five of the ten tables. The evaluator flagged the new view once, the exception was widened, and it went back to 77 / 77. The tests of the tools, the agent and the gate: 83 passed.</p>

</div></section>

```js
display(pager("p6b"));
```
