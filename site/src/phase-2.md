---
title: Phase 2 · Staging and raw QA
---

```js
import {chapterHead, lineageSection, pager} from "./components/chapter.js";
display(chapterHead("p2", "The raw files from the web crawler are messy: prices typed in many formats, files sent twice, an old file sent again with a new date. This phase reads every line, fixes what can be fixed safely, and tags the rest with the reason. No line is thrown away, and a test checks that the count at the end matches the count at the start."));
```

<section class="block"><div class="label">01 Problem</div><div class="content">

Phase 1 loaded 238,707 raw lines, exactly as delivered. Every field is text. The generator planted defects in
them on purpose, and wrote down each one in an answer key.

Some defects are inside a line. `1.250` is one thousand two hundred and fifty in Paris and one point two five in
New York. The text alone does not say which. Other defects only show at the level of a whole file: a copy of
an earlier delivery, or an old crawl sent again under a new date. That second case is the delivery that broke
the weekly and monthly reports in production.

If this layer simply deleted bad lines, nobody could count them or check them later.

</div></section>

<section class="block"><div class="label">02 Decision</div><div class="content">

**Staging never filters.** It parses, repairs and flags. Every rule that fires is added to the row's
`dq_issues` list, and `dq_status` is the most severe handling among them:
`pass < fixed < warn < quarantine`. Excluding a row is decided later, where it is counted and tested.

The price parser adds one outside fact, the currency's ISO minor units (how many decimals it has). When even
that is not enough, it returns null and quarantines the line. The rules themselves live in `vars` in
`dbt_project.yml`, so a reviewer changes one line instead of reading a 300-line model.

| Model | Answers | Materialized |
|---|---|---|
| `base_crawl__lines` | one row per line, every JSON field as text | view |
| `stg_crawl__product_observations` | one row per line: parse, repair, flag | table |
| `qa_raw__quarantined_lines` | which lines we refuse, why, and what the crawler sent | table |
| `qa_raw__repaired_values` | every automatic repair, raw value next to repaired | table |
| `qa_raw__file_profile` | which deliveries are copies, stale, or incomplete | table |
| `qa_answer_key__recall` | how much of the planted damage we caught | table |

</div></section>

<section class="block"><div class="label">03 Rejected<span>The alternatives I considered, and why not.</span></div><div class="content">

| Alternative | Why not |
|---|---|
| Drop bad rows in staging | A row dropped in staging is invisible forever. Nobody can count it or audit it. |
| Use the crawler's own number, `price.price` | It is in minor units for some markets only, and always labelled EUR. It is never used. |
| Read the separators from the text alone | `1.250` means two different numbers in two countries. For a currency with 3 decimals, like KWD, the parser refuses to guess. |
| Catch the stale file with row-level checks | Every row in it is valid data, just old. Only a file-level profile sees that its newest crawl is 15 days older than its file date. |
| Keep the staging model as a view | It regex-parses 240k JSON lines and is read by 5 models. As a view, that work would repeat on every read. |

</div></section>

<section class="block"><div class="label">04 dbt features<span>What each one does in this phase.</span></div><div class="content">

| Feature | What it does here |
|---|---|
| Sources + freshness | `crawl.crawl_lines` warns after 8 days without a load and errors after 15. The answer key is a test-only source with no staging model. |
| `base_` sub-model | Extraction and cleaning are two steps. `base_crawl__lines` only extracts. |
| `vars` + macros | Currency map, minor units, thresholds and `dq_reasons`. `{{ market_currency('market') }}` becomes a `CASE`. |
| Unit tests | 2 tests run the price-format table on hand-written inputs, before any real data. |
| `dbt_utils.equal_rowcount` | Both staging models have exactly the source's row count. |
| Singular tests | `assert_every_line_has_exactly_one_outcome`: per file, delivered = usable + quarantined. `assert_answer_key_fully_caught` grades recall. |

```yaml
# models/staging/crawl/_crawl__sources.yml
config:
  loaded_at_field: loaded_at
  freshness:
    # crawls are delivered weekly: one missed delivery warns, two missed deliveries fail
    warn_after: {count: 8, period: day}
    error_after: {count: 15, period: day}
```

</div></section>

```js
display(lineageSection("p2", await FileAttachment("lineage/lineage_p2.svg").text()));
```

<section class="block"><div class="label">06 Proof<span>Reference run, local Spark, seed 42.</span></div><div class="content">

<div class="versus">
  <div><span class="micro">Defect codes this phase owns</span><b>34 / 34</b><p>caught at 100 % recall, graded against the answer key</p></div>
  <div><span class="micro">Left for Phase 3</span><b>2</b><p><code>A09_minor_units_leak</code> and <code>G01_unit_scale_error</code>: a price ×100 or ×10 looks valid on its own</p></div>
</div>

| `dq_status` | Handling | Lines |
|---|---|--:|
| pass | no issue | 223,680 |
| fixed | repaired, raw value kept | 11,561 |
| warn | kept, surfaced | 2,046 |
| quarantine | excluded from marts | 1,420 |

<p class="cap"><code>dbt build</code>: 37 / 37 PASS (6 models, 2 unit tests, 27 data tests, 2 singular tests). The file profile blocks the <code>(1)</code> copy of 08-10 and the stale 09-15 file, and warns on 08-17 (HKG and KOR below 70 % of their usual size) and 09-14 (JPN missing).</p>

</div></section>

```js
display(pager("p2"));
```
