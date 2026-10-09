---
title: Phase 5b · Semantic layer + agent
---

```js
import {chapterHead, lineageSection, pager} from "./components/chapter.js";
display(chapterHead("p5b", "This phase lets anyone ask the price data a question in plain English, such as how much a bag costs in Japan. Every business number is written down once, in a shared dictionary, and the AI assistant can only pick a number from that dictionary and fill in a short form. It never writes its own database code, so it cannot invent a figure, and when a question has no honest answer it says no and explains why."));
```

<section class="block"><div class="label">01 Problem</div><div class="content">

If three dashboards each write their own SQL for bag price increase, sooner or later they disagree. One
divides by markets, another by products, a third forgets to exclude new products. Phase 4 chose which
like-for-like number is the headline. Nothing yet stopped the next reader from writing it again, differently.

An AI agent makes this worse. An LLM that writes SQL from a question is flexible and ungovernable. It can
invent a column, average euros with yen, or read a delivery the gate has not released.

The goal: questions in plain English, answers that match the official definitions, and no way to make the
agent invent a number. And when the gate does not pass a delivery, someone should explain why.

</div></section>

<section class="block"><div class="label">02 Decision</div><div class="content">

**One definition per number, and an agent that can only fill a form.** Every metric is defined once in dbt
(MetricFlow spec): 10 governed metrics plus 2 hidden building blocks, on 3 semantic models. `dbt parse`
compiles them into `semantic_manifest.json`, and the agent reads its catalogue from that file. Change a
metric in dbt, re-parse, and the agent follows. There is nothing to keep in sync.

| Semantic model | Published view | Metrics |
|---|---|---|
| `hero_prices` | `pub_micro__hero_prices_weekly` | `hero_price`, `hero_price_change`, `hero_price_increases` |
| `category_monthly` | `pub_macro__category_monthly` | `category_lfl_change`, `category_lfl_change_product_weighted`, `category_product_count`, `category_median_price`, `category_share_increased` |
| `price_changes` | `pub_fct_price_changes` | `price_change_count`, `average_price_change` |

A translator turns the question into an **Intent**: metric, filters, group by, period. Guardrails check it,
and a template compiler writes the SQL on one published view. The semantic models sit on the published
views, so every answer only sees deliveries the gate released.

<p class="cap">A separate triage agent reads the gate's results. For each delivery that did not pass, it runs drill-down queries and writes a likely cause, an action and a draft client note.</p>

</div></section>

<section class="block"><div class="label">03 Rejected<span>The alternatives I considered, and why not.</span></div><div class="content">

| Alternative | Why not |
|---|---|
| The LLM writes the SQL | Flexible and ungovernable: it can invent a column, average currencies, or read a table nobody released. Here its only output is a form whose `metric` and `group_by` fields are enums from the manifest. |
| The agent keeps its own list of metrics | Two lists drift. The agent reads the dictionary dbt compiled, and a test fails if the committed copy drifts from the dbt YAML. |
| dbt's hosted Semantic Layer API | It needs a paid dbt plan. The definitions use dbt's standard format, and a small compiler turns them into SQL. With the paid API, only the executor would change. |
| A better prompt for Claude | Claude's first live run scored 14/25. It read every question correctly and filled the form literally. The business rules moved into one shared policy, `apply_policy`, that both translators go through. |
| Averaging prices across markets | EUR 2,280 averaged with JPY 430,100 looks precise and means nothing. Every currency metric requires a market, and the agent refuses otherwise. |

</div></section>

<section class="block"><div class="label">04 dbt features<span>What each one does in this phase.</span></div><div class="content">

| Feature | What it does here |
|---|---|
| Semantic models | 3, each on one published view. Each declares entities (keys), dimensions (what you can group or filter by) and measures (aggregations such as `sum` or `average`). |
| Metrics, `simple` and `ratio` | Product-weighted LFL is a ratio: Σ(market LFL × LFL products) ÷ Σ LFL products. Its two halves are hidden metrics, because a ratio divides metrics. The Phase 4 decision is written once, here. |
| `config.meta.agent` | Synonyms, unit, `requires`, default grouping, default period, `point_in_time`, `hidden`. The agent's rules live next to the metric they govern. |
| Time spine | `metricflow_time_spine`: one row per day, the calendar the semantic layer needs. |
| `dbt parse` | Validates the whole layer and writes `target/semantic_manifest.json`. It reads the project only and runs nothing on the warehouse. |
| Model contract change | `fct_price_changes` now carries `macro_category`, so price changes can be cut by category. |

```yaml
# dbt/models/semantic/_metrics.yml
- name: hero_price
  label: Hero product price
  description: Price of a hero product in a market's local currency, as delivered every Tuesday.
  type: simple
  type_params: {measure: hero_price_local}
  config:
    meta:
      agent:
        synonyms: [hero price, price of, how much is, how much does, cost, costs]
        unit: currency
        requires: [market]
        default_group_by: [product_label, market]
        default_time: latest
        point_in_time: true
```

</div></section>

```js
display(lineageSection("p5b", await FileAttachment("lineage/lineage_p5b.svg").text()));
```

<section class="block"><div class="label">06 Proof<span>Reference run, local Spark, seed 42.</span></div><div class="content">

<div class="versus">
  <div><span class="micro">Rule translator</span><b>25 / 25</b><p>on the evaluation set, including the 4 questions that must be refused</p></div>
  <div><span class="micro">Claude, first live run</span><b>14 / 25</b><p>every question read correctly, the form filled literally: a date as a filter, no period when none was named</p></div>
</div>

| Check | Result |
|---|---|
| Governed metrics | 10, plus 2 hidden building blocks, on 3 semantic models |
| Unit tests, offline | **70 passed**: 55 for the agent (12 of them replay real Claude forms) and 15 for the gate |
| `dbt build` | 165 pass |
| Triage, new design | the 5 WARN deliveries explained with their upstream cause |
| Triage, old design | the 15 Sep BLOCK traced to the re-exported file `ALT_2026-09-15_…`: August content under a September name |

<p class="cap">The same 25 questions grade both translators. Refusals count as answers: <em>LFL change for shoes in Germany</em> must be refused, because Germany is not monitored, and the reply lists the 16 markets that are.</p>

</div></section>

```js
display(pager("p5b"));
```
