---
title: Phase 6c · BI pages
---

```js
import {chapterHead, lineageSection, pager} from "./components/chapter.js";
display(chapterHead("p6c", "This is the part a client actually sees: six web pages with the weekly prices, the monthly trends, every price change, the old mistake replayed, and the checks run before each release. The pages only draw. Every number is calculated and tested before it reaches them, and each page ends with a card that says where its numbers come from and which checks stand behind them."));
```

<section class="block"><div class="label">01 Problem</div><div class="content">

A client reads one number on a dashboard, quotes it in a meeting, and it has to be right. A dashboard is where
trust is won or lost.

The quick way to build one is to start with a chart and write whatever calculation it needs inside the BI tool.
Then the like-for-like rule lives in dbt and again in the page, and the metrics agent needs a third copy. Copies of
one rule drift apart. That is how the original incident happened.

The reader also has no way to check a chart. A number with no visible source is a number you have to take on
faith.

</div></section>

<section class="block"><div class="label">02 Decision</div><div class="content">

Every page is decomposed with the same **six steps**, always in this order. Each step narrows the next, and each
one can send me back to dbt instead of forward to the chart.

| # | Step | What I ask | What it rules out |
|---|---|---|---|
| 01 | **Question** | What does the reader want to know, in one sentence, in their words? | pages that are "everything about X" |
| 02 | **Decision** | What will they *do* with the answer? | numbers nobody acts on |
| 03 | **Grain** | What is one row of the answer? | a chart that silently mixes two grains |
| 04 | **Model** | Which public dbt model has exactly that grain? If none, add one in dbt. | BI reading staging or intermediate models |
| 05 | **Guarantees** | Which tests, contracts and gate checks make that model trustworthy? | promises the pipeline doesn't check |
| 06 | **Chart** | Given the question and the grain, what is the simplest form that answers it? | dual axes, colour-only encoding, decoration |

<p class="cap">The chart comes last for the same reason a tailor cuts last: once the cloth is cut, you can't add it back. A page that starts with "let's make a bar chart" bends the data to fit the chart. On Micro the grain is 8 heroes × 8 markets, the grid the client already has in mind, so the grain is the chart.</p>

The BI layer may filter, sort, count, take a median for a caption, index a series to 100 for display, and pick the
worst status of a cell for colour. It may not compute a number a client would quote. My test: if two pages, or a
page and the metrics agent, need the same calculation, it belongs in a dbt model.

**Worked example: the data-health page.**

| Step | Data health |
|---|---|
| Question | Was every delivery audited before release, what did the audit flag, and what reached clients? |
| Decision | Release or hold a delivery; write the client note that explains a WARN. |
| Grain | One row per delivery; behind it, one row per (delivery, check, subject) from the latest gate run. |
| Model | No public model had the second grain. The detail lived in `stg_ops__qa_check_results`, a staging model BI must not read. So I added **`mart_data_health__check_results`** in dbt (Phase 6b): a public view with an enforced contract, documented columns, a primary-key test and the `data_health_page` exposure. |
| Guarantees | Append-only gate tables, 17 checks as code in `qa/checks.yml`, baselines from the last accepted delivery, `assert_no_blocked_delivery_is_published`. |
| Chart | A verdict strip per delivery, then a checks × deliveries grid grouped by data-quality dimension. Red is used once on the whole site: a failed blocking check. |

Step 05 is printed on every page. A **model card** at the bottom lists the question, the decision, the grain, the
models, the guarantees and the chart choice, and links each model to its dbt docs page. It is a component
(`bi/src/components/modelCard.js`), so every page has the same six rows in the same order.

</div></section>

<section class="block"><div class="label">03 Rejected<span>The alternatives I considered, and why not.</span></div><div class="content">

| Alternative | Why not |
|---|---|
| Evidence.dev, as the roadmap said | Its getting-started flow led to Evidence Studio, a hosted product with a sign-in. I wanted a site anyone can build from the repository with no account, hosted on GitHub Pages. |
| Let the BI compute like-for-like, statuses or verdicts | A second copy of a rule dbt already tests. The pages and the agent would drift apart. |
| Point the data-health page at the gate's raw audit log | That is a staging model. The right grain belongs upstream, as a public mart with a contract. |
| Convert prices to EUR to share one axis | The data has no exchange rate. Inventing one puts an assumption into a client deliverable. Each market is indexed to 100 instead. |
| Stacked bars for price changes | Decreases would sit on top of increases and could not be read from zero. Increases and decreases are mirrored around one zero line. |

</div></section>

<section class="block"><div class="label">04 dbt features<span>What each one does in this phase.</span></div><div class="content">

| Feature | What it does here |
|---|---|
| Exposures with `url` and `depends_on` | One per analytical page, five in all, plus the agent. `depends_on` lists exactly the models the page reads through the snapshot, no more. |
| `dbt ls -s int_prices__historized+ --resource-type exposure` | Answers "which pages break if I change the price history?": `price_change_explorer` and `metrics_agent`, nothing else. |
| `dbt ls -s +exposure:price_change_explorer` | Lists the 16 models the price-changes page depends on: its real blast radius. |
| `access: public` + enforced contracts | The interface the BI reads. The snapshot exports public models only, and each CSV header is the dbt contract. |
| dbt docs | Every model on a model card links to its dbt docs page, so a reviewer goes from a chart to the SQL in one click. |
| dbt-project-evaluator | Checks the new exposure in CI: public parents, documented. |

```yaml
# models/marts/_exposures.yml
  - name: data_health_page
    label: Data health - delivery gate verdicts
    type: dashboard
    maturity: medium
    url: https://calvinwang-3333.github.io/balenciaga-pricing-pipeline/bi/data-health
    description: >
      Every delivery's gate verdict (PASS / WARN / BLOCK) and whether it was released, every check's result
      behind it (observed value, rules, message), on the published design and on the replay of the old
      design. BI page bi/src/data-health.md.
    owner: {name: Calvin Wang}
    depends_on:
      - ref('mart_data_health__deliveries')
      - ref('mart_data_health__check_results')
```

</div></section>

```js
display(lineageSection("p6c", await FileAttachment("lineage/lineage_p6c.svg").text()));
```

<section class="block"><div class="label">06 Proof<span>The production snapshot, as the pages show it.</span></div><div class="content">

<div class="versus">
  <div><span class="micro">Published design</span><b>0</b><p>deliveries blocked by the gate: 11 PASS, 5 WARN</p></div>
  <div><span class="micro">Old design, replayed</span><b>2</b><p>deliveries blocked, on 18 Aug and 15 Sep, plus 1 WARN</p></div>
</div>

| Check | Result |
|---|---|
| `npm run build` in `bi/` | built 6 pages |
| Exposures | 5 pages, each with its URL; 6 exposures in total with the agent |
| Exposures corrected by building the pages | 3: Micro, incident and data health had each declared a model they don't read |
| `dbt ls -s int_prices__historized+ --resource-type exposure` | 2 exposures: `price_change_explorer`, `metrics_agent` |
| `dbt ls -s +exposure:price_change_explorer` | 16 models |
| DAG | 57 → 58 nodes: the new exposure is a node |
| dbt-project-evaluator | passes with the new exposure; 77 / 77 since Phase 6b |
| Incident page | 10 of 232 date × market cells wrong on the replay |
| Micro page | 832 cells over 13 deliveries: 703 unchanged, 64 first deliveries, 56 increases, 8 decreases, 1 page error |

<p class="cap">An exposure that lists too much is as wrong as one that lists too little: it makes the blast radius look bigger than it is. The overview page has no exposure of its own, because it summarises models the other five already declare.</p>

</div></section>

```js
display(pager("p6c"));
```
