---
title: One shared table
---

```js
import {html} from "htl";
import {phases, MAX_NODES} from "./data/phases.js";
const full = await FileAttachment("lineage/lineage_full.svg").text();
```

<section class="hero" aria-labelledby="hero-title">
  <p class="kicker">Analytics engineering · dbt on Databricks · Ruihang Wang</p>
  <h1 id="hero-title"><span>One shared table.</span><span>Two deliveries.</span><span>Wrong prices.</span></h1>
  <p class="lede">A luxury price monitor sends clients a <b>weekly Micro</b> report on their hero products and a
  <b>monthly Macro</b> report on whole categories. Both read one staging table that every file import overwrote,
  so whoever imported last decided which crawl the other report saw. I rebuilt the pipeline in dbt so that cannot
  happen, and proved it on the same files.</p>
  <div class="meta micro"><span>Phases 0 – 6d</span><span>58 dbt nodes</span><span>CI + production on GitHub Actions</span><span>Synthetic data</span></div>
  <div class="mech" role="group" aria-label="Old design and new design compared">
    <div>
      <p class="kicker">Before</p>
      <h3>A mutable catalogue</h3>
      <div class="flow" aria-hidden="true">
        <div class="row"><span class="chip">crawl 31 Aug</span><span class="chip">crawl 14 Sep</span><span class="chip">ALT_15 Sep<small>still the 31 Aug crawl</small></span></div>
        <span class="arrow">↓ each import overwrites ↓</span>
        <span class="chip wide dark">shared catalogue<small>one state: the last file wins</small></span>
        <span class="arrow">↓          ↓</span>
        <div class="row"><span class="chip">Micro · weekly</span><span class="chip">Macro · monthly</span></div>
      </div>
      <p class="verdict">On 15 Sep, 8 countries would have received prices from two weeks earlier, about a quarter of
      them different. Nothing in the old process could see it.</p>
    </div>
    <div>
      <p class="kicker">After</p>
      <h3>One history, read at a date</h3>
      <div class="flow" aria-hidden="true">
        <div class="row"><span class="chip">crawl 31 Aug</span><span class="chip">crawl 14 Sep</span><span class="chip">ALT_15 Sep</span></div>
        <span class="arrow">↓ appended, never overwritten ↓</span>
        <span class="chip wide">bronze · append-only<small>one row per delivered line</small></span>
        <span class="arrow">↓</span>
        <span class="chip wide dark">point-in-time catalogue<small>latest eligible crawl on or before the date</small></span>
        <span class="arrow">↓          ↓</span>
        <div class="row"><span class="chip">Micro @ each Tuesday</span><span class="chip">Macro @ month-end</span></div>
      </div>
      <p class="verdict">A dbt test, <code>serves_latest_eligible_crawl</code>, runs on both designs on every build:
      0 violations on this one, 10 on the replay of the old one.</p>
    </div>
  </div>
</section>

<section class="band" id="numbers" aria-labelledby="numbers-title">
  <div class="numbers">
    <div><p class="kicker">In numbers</p><h2 id="numbers-title" class="display" style="font-size:clamp(1.8rem,4.4vw,3.6rem);margin-top:0.6rem">What it does, in plain words</h2></div>
    <div class="group">
      <h2>The data<span>What goes in. Synthetic, but shaped like a real luxury price feed, mess included.</span></h2>
      <div class="figs">
        <div class="fig"><b>238,707</b><p>price readings: one product, in one country, on one crawl day.</p><small>NDJSON lines in 15 files → COPY INTO an append-only Delta table</small></div>
        <div class="fig"><b>16</b><p>countries, each priced in its own currency. 8 are checked every week, 8 once a month.</p><small>16 markets · weekly vs monthly crawl cadence</small></div>
        <div class="fig"><b>2,001</b><p>products: bags, shoes, small leather goods and accessories.</p><small>dim_product · one row per SKU</small></div>
        <div class="fig"><b>13</b><p>weekly reports, July to September 2026, plus 3 monthly ones.</p><small>13 Micro + 3 Macro deliveries</small></div>
      </div>
    </div>
    <div class="group">
      <h2>The problem, measured<span>The old process, replayed on the same files, next to the new one.</span></h2>
      <div class="figs">
        <div class="fig"><b>10 / 232</b><p>country reports the old process would have sent with wrong prices, without anyone noticing.</p><small>date × market cells · qa_incident__legacy_vs_point_in_time</small></div>
        <div class="fig"><b>~26 %</b><p>of the prices wrong in each of those reports on 15 Sep: a two-week-old file had been re-sent under a new name.</p><small>share_prices_different, 8 markets</small></div>
        <div class="fig"><b>0</b><p>wrong reports with the new design, checked again on every build.</p><small>serves_latest_eligible_crawl → 0 rows</small></div>
      </div>
    </div>
    <div class="group">
      <h2>The safety net<span>What stands between messy data and a client.</span></h2>
      <div class="figs">
        <div class="fig"><b>36</b><p>kinds of messy data caught automatically: wrong currency, missing price, duplicate file, broken page…</p><small>planted defect codes · 100 % recall against the answer key</small></div>
        <div class="fig"><b>17</b><p>automatic checks every report must pass before a client can see it.</p><small>delivery gate · checks-as-code · write-audit-publish</small></div>
        <div class="fig"><b>2</b><p>bad reports stopped: exactly the two that went wrong in real life, and nothing else.</p><small>BLOCK on 2026-08-18 and 2026-09-15</small></div>
        <div class="fig"><b>146</b><p>automatic tests run every time the data is rebuilt.</p><small>142 dbt data tests + 4 unit tests · 83 Python tests</small></div>
      </div>
    </div>
    <div class="group">
      <h2>The engineering<span>How it is built so it keeps working when it changes.</span></h2>
      <div class="figs">
        <div class="fig"><b>58</b><p>building blocks in the pipeline, from raw source to dashboard, every one documented.</p><small>models, seeds, sources, semantic models, exposures</small></div>
        <div class="fig"><b>19</b><p>tables with a written contract: if their shape changes, the build stops before anything downstream breaks.</p><small>contract: enforced</small></div>
        <div class="fig"><b>44 s</b><p>to test a change instead of about 6 minutes, by rebuilding only what the change touches.</p><small>Slim CI · state:modified+ --defer · 48 of 191 nodes</small></div>
        <div class="fig"><b>77 / 77</b><p>best-practice rules passing, checked on every proposed change.</p><small>dbt-project-evaluator · error severity</small></div>
      </div>
    </div>
  </div>
</section>

<section id="story" class="block" style="margin-top:3.5rem">
  <div class="label">The evidence chain<span>How the project is argued, from the problem to the people who read the data.</span></div>
  <div class="content">
    <ol class="chain">
      <li><span class="micro">01</span><h3>Incident</h3><p>Two cadences, one mutable table. The order of imports decided the prices clients received.</p><span class="micro"><a href="./phase-1">Phase 1</a> · <a href="./phase-2">2</a></span>
        <div class="tags"><span class="tag">sources</span><span class="tag">freshness</span><span class="tag">quarantine</span></div></li>
      <li><span class="micro">02</span><h3>Design</h3><p>Append-only raw data, SCD2 price history and an as-of date. Micro and Macro become two reads of one history.</p><span class="micro"><a href="./phase-3">Phase 3</a> · <a href="./phase-4">4</a></span>
        <div class="tags"><span class="tag">SCD2</span><span class="tag">incremental merge</span><span class="tag">contracts</span></div></li>
      <li><span class="micro">03</span><h3>Proof</h3><p>The old design is replayed beside the new one. One generic test catches the incident on the replay and nothing on the fix.</p><span class="micro"><a href="./phase-4">Phase 4</a> · <a href="./phase-5a">5a</a></span>
        <div class="tags"><span class="tag">generic tests</span><span class="tag">unit tests</span><span class="tag">write-audit-publish</span></div></li>
      <li><span class="micro">04</span><h3>Production</h3><p>Every pull request runs Slim CI and the project evaluator. Every merge builds production, audits it, then publishes.</p><span class="micro"><a href="./phase-6a">Phase 6a</a></span>
        <div class="tags"><span class="tag">state:modified+</span><span class="tag">--defer</span><span class="tag">model access</span></div></li>
      <li><span class="micro">05</span><h3>Consumption</h3><p>BI pages and an LLM agent read only public, contract-enforced models and governed metrics.</p><span class="micro"><a href="./phase-5b">Phase 5b</a> · <a href="./phase-6c">6c</a></span>
        <div class="tags"><span class="tag">semantic layer</span><span class="tag">exposures</span><span class="tag">manifest.json</span></div></li>
    </ol>
  </div>
</section>

<section id="phases" class="block">
  <div class="label">Phases<span>Eleven chapters, one question each. Every chapter follows the same template: problem, decision, rejected alternatives, dbt features, lineage, proof.</span></div>
  <div class="content">

```js
display(html`<div class="grid">${phases.map((p) => html`<a class="item" href="./${p.slug}">
  <div class="plate"><span class="n">${p.plate}</span>
    <div><div class="nodes"><span>${p.nodes[1] ? "DAG" : "No models yet"}</span><span>${p.nodes[1] ? `${p.nodes[1]} nodes` : ""}</span></div>
    <div class="bar"><i style="width:${(100 * p.nodes[1]) / MAX_NODES}%"></i></div></div></div>
  <span class="micro">${p.label}</span><span class="t">${p.title}</span><span class="q">${p.question}</span></a>`)}
  <a class="item result" href="./bi/"><div class="plate"><span class="n">BI</span><div class="nodes"><span>The result</span><span>6 pages</span></div></div>
  <span class="micro">Open</span><span class="t">The BI pages</span><span class="q">What clients receive, read from the released deliveries only.</span></a></div>`);
```

  </div>
</section>

<section id="lineage" class="block">
  <div class="label">The DAG, today<span>Generated from dbt's manifest on every site build. Nothing here is drawn by hand.</span></div>
  <div class="content">

```js
const grown = phases.filter((p) => p.lineage);
display(html`<div class="growth" aria-label="Number of dbt nodes after each phase">${grown.map((p) => html`<div class="g">
  <span>${p.label}</span><div class="track"><div class="fill" style="width:${(100 * p.nodes[1]) / MAX_NODES}%"></div></div><span class="v">${p.nodes[1]}</span></div>`)}</div>`);
const frame = document.createElement("div");
frame.className = "lineage"; frame.tabIndex = 0;
frame.setAttribute("role", "img"); frame.setAttribute("aria-label", "Full lineage graph, scroll sideways");
frame.innerHTML = full.replace(/<\?xml[^>]*>/, "").replace(/ id="/g, ' id="full-');
display(frame);
```

  <p class="cap">Nodes (models, seeds, sources, semantic models, exposures) after the merge that closed each phase,
  compiled from git history. In the graph, lanes run left to right: sources and seeds, staging, intermediate, marts,
  published, semantic layer, exposures. The band at the bottom is the quality lane: models that watch the pipeline
  instead of feeding it. Scroll sideways →</p>
  </div>
</section>

<section class="block">
  <div class="label">Walk in<span>The same project, three ways in.</span></div>
  <div class="content">
    <nav class="doors" aria-label="Project areas">
      <a href="./bi/"><b>BI pages</b><span>Micro, Macro, price changes, the incident and data health, with a model card on every page.</span></a>
      <a href="./dbt-docs/"><b>dbt docs</b><span>Every model, column and test, as built in production.</span></a>
      <a href="https://github.com/calvinWANG-3333/balenciaga-pricing-pipeline"><b>Source ↗</b><span>The repository, with one teaching chapter per phase in docs/.</span></a>
    </nav>
  </div>
</section>
