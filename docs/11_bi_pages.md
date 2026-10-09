# 11 – The BI pages (Phase 6c)

> Six static pages built with **Observable Framework** on the snapshot of the public interface (Phase 6b).
> The pages are not the interesting part. The interesting part is the method: every page is decomposed the
> same way, **question → decision → grain → model → guarantees → chart**. The chart is decided last, and
> every page ends with a *model card* that shows this chain to the reader.

---

## 0. The big picture

```
 dbt (production)                         Phase 6b                    Phase 6c (this chapter)
 ───────────────────────────────          ──────────────────          ───────────────────────────────────────────
 pub_* views + public health marts  ──►   tools/snapshot/export.py ──► bi/src/data/*.csv  ──►  Observable Framework
 (access: public, enforced contracts)     public models only           + snapshot_manifest     markdown + JS pages
 released deliveries only                 released deliveries only                             ──► bi/dist/ (static HTML)
                                                                                                ──► /bi on the site (6d)
```

| Page | The question it answers | Main model | Chart |
|---|---|---|---|
| Overview | Can a client trust what this site shows? | `pub_released_deliveries` | none: stat tiles + provenance |
| Micro | Did a tracked hero change price this week, where, by how much? | `pub_micro__hero_prices_weekly` | status grid hero × market, words in the cells |
| Macro | How did each category move this month, like-for-like? | `pub_macro__category_monthly(_global)` | faceted bars from zero, same market order in every panel |
| Price changes | What moved, where, when, by how much? | `pub_fct_price_changes` | mirrored bars per crawl + strip of ticks with a median |
| The incident | How often would the old design have served the wrong data? | `qa_incident__legacy_vs_point_in_time` | date × market heatmap + two-row gate timeline |
| Data health | Was every delivery audited, what was flagged, what was released? | `mart_data_health__deliveries`, `__check_results` | verdict strip + checks × deliveries grid |

**What the BI layer is allowed to do:** filter, sort, count, take a median for a caption, index a series to
100 for display, pick the worst status of a cell for colour. **What it is not allowed to do:** compute a number
a client would quote. A like-for-like change, a price status, a gate verdict, a change percentage are all
computed in dbt, tested there, and only *drawn* here. The test I use: *if two pages, or the BI and the
metrics agent, would need the same calculation, it belongs in a dbt model.*

---

## 1. The method: how one page is decomposed

**Plain.** A tailor does not start with the fabric. He asks what the suit is for (a wedding, the office),
takes measurements, then picks the cloth, and only at the end cuts. If you cut first, you can't add cloth
back. A dashboard that starts with "let's make a bar chart" is cutting first.

**Professional.** Six steps, always in this order. Each step narrows the next, and each one can send me back
to dbt instead of forward to the chart.

| # | Step | What I ask | What it decides | What it rules out |
|---|---|---|---|---|
| 01 | **Question** | What does the reader want to know, in one sentence, in their words? | the scope of the page | pages that are "everything about X" |
| 02 | **Decision** | What will they *do* with the answer? | which numbers must be exact and which are context | numbers nobody acts on |
| 03 | **Grain** | What is one row of the answer? | the key the page joins and filters on | a chart that silently mixes two grains |
| 04 | **Model** | Which **public** dbt model has exactly that grain? If none: add one in dbt. | the dependency, visible in the lineage as an exposure | BI reading staging or intermediate models |
| 05 | **Guarantees** | Which tests, contracts and gate checks make that model trustworthy? | what the page may promise | promises the pipeline doesn't check |
| 06 | **Chart** | Given the question and the grain, what is the simplest form that answers it? | the chart, or no chart | dual axes, colour-only encoding, decoration |

Two consequences matter in an interview:

1. **Step 04 can create work in dbt, not in BI.** The data-health page needed one result per check, per
   delivery, per subject. No public model had that grain. I didn't point the page at the gate's raw audit
   log. I added `mart_data_health__check_results` in Phase 6b, a public view with a contract, documented
   columns, a primary-key test and the `data_health_page` exposure. The BI layer stays thin because the
   grain was fixed upstream.
2. **Step 05 is printed on the page.** The model card at the bottom of each page lists the tests and gate
   checks that stand behind the numbers. Each model links to its dbt docs page (`../dbt-docs/…`, live once the
   site is deployed in 6d). A reviewer can go from a chart to the SQL in one click.

The model card is a component (`bi/src/components/modelCard.js`), so every page has the same six rows in the
same order. The structure is enforced by code, not by discipline.

---

## 2. Page by page: how each one was decomposed

Each page below follows the six steps, then lists the alternatives I rejected and why. The rejected
alternatives are the part that shows judgement.

### 2.1 Overview: trust before charts

| Step | Decision |
|---|---|
| Question | *Can a client trust what this site shows?* |
| Decision | Whether to use these numbers at all, so the answer must come before any chart. |
| Grain | One row per released delivery (scope, as_of_date), plus one manifest per snapshot. |
| Model | `pub_released_deliveries` (the publish switch), `mart_data_health__deliveries` (every verdict). |
| Guarantees | Export reads public models only; refuses to run if a delivery date is not released; `assert_no_blocked_delivery_is_published`. |
| Chart | None. Five stat tiles and a provenance sentence (exported when, from which environment, at which commit). |

**Rejected:** a hero chart on the landing page. It would be the first thing a reader sees, and it would
answer a question they haven't asked yet. **What it shows:** 13 Micro and 3 Macro deliveries released, 8
heroes in 8 weekly markets, 6,681 price changes, 2 old-design deliveries blocked by the gate on the replay.

### 2.2 Micro: which cell moved

| Step | Decision |
|---|---|
| Question | *Did any hero product a client tracks change price this week, in which market, by how much, and can I trust each cell?* |
| Decision | The weekly pricing alert a client acts on (match a competitor's increase, check a markdown). |
| Grain | (delivery date, hero, weekly market): 8 × 8 = **64 cells per delivery, always**. A missing hero keeps its row with `not_found` or `page_error`. |
| Model | `pub_micro__hero_prices_weekly` → `mart_micro__hero_prices_weekly` (point-in-time catalogue at each Tuesday) + `pub_dim_market`. |
| Guarantees | PK on (delivery_date, pointer_id, market); enforced contract; the killer test (same SKU, same date ⇒ same price in Micro and Macro); gate checks `hero_grid_complete`, `hero_price_coverage`, `hero_stale_share`, `hero_carried_forward`, `hero_large_moves`. |
| Chart | A hero × market grid with the status written in each cell (`+6.0 %`, `=`, `new`, `n/f`, `err`, `*` for stale). Above it, cells moved per delivery; below it, the chosen hero indexed to 100 in small multiples. |

How I broke it down:

1. The client's mental model is already a grid: their heroes down the side, their markets across the top.
   So the grain *is* the chart. A complete grid is also a promise: if a cell is empty, something is wrong.
2. A grid answers "this week". "Which week should I open?" is a second question, answered by a small bar
   chart of cells moved per delivery, with the selected delivery dashed.
3. "How did this hero move over time?" is a third question. Eight currencies cannot share one axis, so each
   market is indexed to its first delivery (= 100), one small multiple per market, same scale.

**Rejected:**
- *Converting prices to EUR* to put them on one axis: the data has no exchange rate, and inventing one would
  put an assumption into a client deliverable.
- *Dropping not-found rows*: it would make a missing price look like no change.
- *Colour-only cells*: the status is written in the cell, colour only reinforces it.

**What it shows:** 13 deliveries, 832 cells: 703 unchanged, 64 first deliveries, 56 increases, 8 decreases,
1 page error. Most weeks nothing moves, which is what a quiet luxury price list looks like.

### 2.3 Macro: one honest number per category, and its alternative

| Step | Decision |
|---|---|
| Question | *How did each category's prices move this month, like-for-like, in every market and overall?* |
| Decision | The monthly category review: which categories and markets carried the increases. |
| Grain | (report month, market, macro category); and (report month, macro category) for the global view. |
| Model | `pub_macro__category_monthly`, `pub_macro__category_monthly_global`, `pub_dim_market`. |
| Guarantees | Like-for-like basket = products priced at both month-ends (`lfl_n_products` is published); a dbt unit test pins the headline definition; gate checks `macro_grid_complete`, `lfl_match_rate`, `lfl_change_bounds`, `median_price_drift`, `cross_market_dispersion`, `global_reconciles_with_markets`. |
| Chart | Tiles per category (market-weighted headline, product-weighted beside it); faceted horizontal bars from zero, one panel per category, markets in the same order in every panel; tables for the mean-of-means choice and for price levels. |

How I broke it down:

1. "How much did Bags move globally?" has two defensible answers. **Market-weighted** (each market counts
   once) answers "how did the brand move its price list". **Product-weighted** (each product-market pair
   counts once) answers "how did the average listed product move". The decision was made in dbt in Phase 4:
   publish both, name the headline, pin it with a unit test. The page's job is to show both, side by side.
2. Then the per-market detail. The reader compares a market across categories (read across) and a category
   across markets (read down), so the panels share the market order and the x scale.
3. Price levels last: sixteen currencies cannot share an axis, so levels are a table in local currency.

**Rejected:**
- *A diverging-colour heatmap* for LFL: the sign would be carried by colour alone. Bars carry it by direction.
- *Only the global number*: it hides the mean-of-means choice, which is the interesting part.
- *A July bar of zero*: July is the first month-end, with no previous month there is no like-for-like basket,
  so July does not appear in the month list. That's stated in the caption, not hidden.

### 2.4 Price changes: the events behind every number

| Step | Decision |
|---|---|
| Question | *What moved, where, when, and by how much?* |
| Decision | Explaining a Micro or Macro number: which individual products produced it. |
| Grain | One row per price change event: a product-market and the crawl where its new price first appeared. |
| Model | `pub_fct_price_changes`, `pub_dim_product`, `pub_dim_market`. |
| Guarantees | Built from SCD2 price periods (`int_prices__historized`, non-overlap tested); only accepted observations (quarantined lines, blocked deliveries and outliers never create a change); gate checks `price_decrease_share`, `price_reversion_share`. |
| Chart | Increases above and decreases below one zero line, per crawl; a strip of ticks per category with a median dot; the latest 200 events as a table. |

How I broke it down:

1. The fact is an event, so the first view is *when*: events per crawl. Increases and decreases are
   mirrored around zero on one axis, so both are read from the same baseline.
2. Two tall bars appear, 3,306 increases on 7 Sep and 3,061 on 28 Sep. Same price increase (about +6 %)
   twice? The caption explains it: 7 Sep is when the 8 weekly-crawled markets see it, 28 Sep is when the
   monthly crawl reaches the other 8. **Crawl cadence decides when a change becomes visible**, which is the
   whole reason Micro and Macro must read one point-in-time history.
3. Then *how big*: luxury prices move in steps, so the shape of the distribution is the point. Ticks show
   every event, the dot shows the median.

**Rejected:**
- *Stacked bars*: decreases would sit on top of increases and could not be read from zero.
- *A mean*: 141 markdowns at about −10 % would pull it, and the tight clusters would disappear.

### 2.5 The incident: measured, not argued

| Step | Decision |
|---|---|
| Question | *How often would the old shared catalogue have delivered the wrong crawl, product list or prices, and would anything have caught it?* |
| Decision | Whether the redesign was worth it. |
| Grain | (reporting date, market): which crawl each design serves, and how many products and prices disagree. |
| Model | `qa_incident__legacy_vs_point_in_time` (public, contract enforced), built from `int_legacy__catalogue_replayed` (old design, imports applied in file order) and `int_catalogue__as_of` (new design); `mart_data_health__deliveries` for the gate's verdict on both. |
| Guarantees | The killer test `serves_latest_eligible_crawl` runs on both designs: it passes on point-in-time and is *expected* to fail on the replay; bronze is append-only, so the replay sees exactly the files the old pipeline saw; the legacy dataset is audit-only in the gate. |
| Chart | A date × market heatmap (black = old design wrong, with a ×), the evidence table, then the gate timeline with both designs on two rows. |

How I broke it down:

1. An incident has a *when* and a *where*. A date × market heatmap shows both at once: 232 cells replayed,
   10 wrong.
2. The table names the evidence: on 15 Sep, 8 markets served `ALT_2026-09-15_…`, a file re-exported under
   a later date that still contained the 31 Aug crawl (about 26 % of prices different). On 18 Aug, HKG and
   KOR got the partial 17 Aug file (about 900 products missing each).
3. Then the second half of the question, *would anything have caught it?* The same gate with the same 17
   checks on both designs, on two rows of one timeline: the old design is **BLOCKed on 18 Aug and 15 Sep**,
   the point-in-time design passes or warns on the same dates.

**Rejected:** a narrative-only page. A story of the incident is an opinion; the replay makes it a measurement.

### 2.6 Data health: the audit trail

| Step | Decision |
|---|---|
| Question | *Was every delivery audited before release, what did the audit flag, and what reached clients?* |
| Decision | Release or hold a delivery; write the client note that explains a WARN. |
| Grain | One row per delivery (dataset, scope, as_of_date); behind it one row per (delivery, check, subject) from the latest gate run. |
| Model | `mart_data_health__deliveries`, `mart_data_health__check_results` (added in 6b for this page), `stg_ops__qa_check_results` (the gate's append-only log). |
| Guarantees | The gate's tables are append-only Delta tables; 17 checks as code (`qa/checks.yml`) with dimension, severity and rules; baselines are the last *accepted* delivery; `assert_no_blocked_delivery_is_published`. |
| Chart | A verdict strip per delivery, then a checks × deliveries grid grouped by data-quality dimension, then the table of everything that did not pass. |

How I broke it down:

1. An auditor reads the grid two ways: down a column (*what went wrong with this delivery*) and along a
   row (*is this check noisy over time*). That's why it's a grid and not a list.
2. A cell can cover several subjects (markets, categories, heroes), so it shows the worst one. The table
   below gives every subject, with the observed value and the warn/fail rule next to it.
3. Red is spent once on the whole site: a failed blocking check. WARN is grey with a `!`; it is released
   with a note.

**What it shows:** published design 11 PASS, 5 WARN, 0 BLOCK. Old design, replayed: 2 BLOCK, 1 WARN.

### 2.7 The dbt side of the pages: one exposure per page

A page is not finished when it renders. It is finished when dbt knows it exists. Each analytical page has an
exposure in `dbt/models/marts/_exposures.yml` with its URL, and `depends_on` lists **exactly** the models
the page reads through the snapshot, no more:

| Exposure | Page | depends_on |
|---|---|---|
| `micro_hero_price_tracker` | `/micro` | `pub_micro__hero_prices_weekly`, `pub_dim_market` |
| `macro_category_monitor` | `/macro` | `pub_macro__category_monthly`, `pub_macro__category_monthly_global`, `pub_dim_market` |
| `price_change_explorer` (new) | `/price-changes` | `pub_fct_price_changes`, `pub_dim_product`, `pub_dim_market` |
| `incident_replay_report` | `/incident` | `qa_incident__legacy_vs_point_in_time`, `mart_data_health__deliveries`, `pub_dim_market` |
| `data_health_page` | `/data-health` | `mart_data_health__deliveries`, `mart_data_health__check_results` |

Building the pages corrected the declarations written in Phase 4 and 5a: the Micro page doesn't read
`pub_dim_product` (the grid already carries the product label), the incident page doesn't read
`pub_fct_catalogue_as_of`, and the data-health page doesn't read `pub_released_deliveries` (the deliveries
mart already says whether a delivery is released). An exposure that lists too much is as wrong as one that
lists too little: it makes the blast radius look bigger than it is.

Why it matters: impact analysis becomes a dbt command.

```bash
dbt ls -s int_prices__historized+ --resource-type exposure
```

answers *which pages break if I change the SCD2 price history?* → `price_change_explorer` and
`metrics_agent`, nothing else. In the other direction, `dbt ls -s +exposure:price_change_explorer` lists
the 16 models the price-changes page depends on. The exposures are also nodes in the lineage pictures, so
the new page shows up there (58 nodes, from 57).

The overview page has no exposure of its own: it summarises models the other five already declare.

---

## 3. The design system

Balenciaga-*inspired*, not Balenciaga: no logo, no wordmark, and the footer on every page says it is an
independent portfolio project on synthetic data, not affiliated with the brand.

| Token | Value | Rule |
|---|---|---|
| background | `#E4E4E1` cool concrete grey | every page |
| ink | `#0B0B0B` | text, increases, the main series |
| muted | `#6E6E68` | decreases, secondary text |
| red | `#C8102E` | **only** a blocking failure / BLOCK |
| display type | Inter Tight 900, uppercase, tight tracking | h1 and section titles |
| figures | JetBrains Mono, tabular numbers | tables, legends, filters |

Data-visualisation rules applied on every chart: one y axis (never two); identity never by colour alone
(words in cells, symbols in the check grid, direction for sign); tooltips on the marks a reader would point at; a
table view or a table next to every chart; filters in one row above what they scope. On a phone, charts keep a 720 px minimum width
and scroll inside their own block, so the page never scrolls sideways.

---

## 4. Why Observable Framework, not Evidence

The roadmap said Evidence.dev. When I started this phase, Evidence's getting-started flow led to Evidence
Studio, a hosted product with a sign-in. I wanted a site that anyone can build from the repository with no
account, and that GitHub Pages can host.

| | Observable Framework |
|---|---|
| Output | static HTML + JS in `bi/dist/`, deployable anywhere |
| Authoring | one markdown file per page, with JavaScript cells |
| Charts | Observable Plot: grammar of graphics, tooltips, facets |
| Reproducible | versions pinned in `package.json` + `package-lock.json`; libraries imported from `node_modules`, no CDN at build time |
| Trade-off | no SQL inside the page; I write JavaScript to filter and draw |

The trade-off is acceptable *because* the BI layer does no business logic: the SQL lives in dbt.

---

## 5. Files

```
bi/
├── package.json, package-lock.json      pinned: framework 1.13.4, plot 0.6.17, inputs 0.12.0, d3 7.9.0, htl 0.3.1
├── observablehq.config.js               pages, top navigation, fonts, footer disclaimer
└── src/
    ├── style.css                        the design system above
    ├── index.md  micro.md  macro.md  price-changes.md  incident.md  data-health.md
    ├── components/
    │   ├── modelCard.js                 model card, stat tile, collapsible table view
    │   ├── theme.js                     colours, status palettes and their labels/symbols, Plot defaults
    │   ├── format.js                    dates, signed percentages, local-currency money
    │   └── load.js                      CSV → typed rows (dates, timestamps, numbers; ids stay text)
    └── data/                            the snapshot (written by tools/snapshot/export.py)
        ├── *.csv                        10 tables, headers = the dbt contracts
        └── snapshot_manifest.json       row counts, checksums, environment, git sha
```

`bi/node_modules/`, `bi/dist/` and `bi/src/.observablehq/cache/` are git-ignored.

---

## 6. Your steps

> Commands are written for zsh: one command per line, no `#` comments. Run them from the repository root
> unless a step says `cd bi`.

### Step 0 – merge the snapshot PR

On GitHub, open the PR from `phase-6b/bi-snapshot` and merge it (CI builds nothing, the evaluator passes).
Not required for the next steps, but the 6c PR will then show only the 6c changes.

### Step 1 – a branch for 6c

The 6c files are already in your folder (Claude wrote them). Create the branch from where you are; your
uncommitted changes come with you:

```bash
git switch -c phase-6c/bi-pages
git status
```

Expected: the snapshot moved from `bi/sources/pricing/` and `bi/snapshot_manifest.json` to `bi/src/data/`;
new `bi/package.json`, `bi/observablehq.config.js`, `bi/src/…`; changes to `.gitignore`, `README.md`,
`docs/00_roadmap.md`, `docs/06_marts.md`, `docs/10_lineage_and_snapshot.md`, `tools/snapshot/snapshot.yml`; new
`docs/11_bi_pages.md`; `dbt/models/marts/_exposures.yml` (one exposure per page);
`tools/lineage/graphs/current.json` and `site/assets/lineage/*.svg` (regenerated: the new exposure is a node).

### Step 2 – preview the site

Node 20 or later is needed (`node -v`; if missing: `brew install node`).

```bash
cd bi
npm ci
npm run dev
```

Open the address it prints (usually http://127.0.0.1:3000). Change a filter, hover a cell, open a
*Table view*. Stop with `Ctrl+C`, then build once:

```bash
npm run build
cd ..
```

Expected: `built 6 pages`. The model-card links to dbt docs only work after Phase 6d puts the dbt docs next to
the site.

### Step 3 – tests, commit, PR

```bash
python -m pytest tools/tests agent/tests qa/tests
git add -A bi dbt/models/marts/_exposures.yml tools site docs .gitignore README.md
git status
git commit -m "feat(bi): six Observable Framework pages on the public snapshot, with model cards"
git push -u origin phase-6c/bi-pages
```

`git add -A bi` records the moved CSVs as renames. Open the PR into `main`. The only dbt change is the
exposures file: Slim CI selects `state:modified+`, an exposure has nothing to build, so the run is
quick; the evaluator checks the new exposure (public parents, documented) and passes. After the merge, the
deploy publishes dbt docs with the new exposure. A BI build check in CI arrives with the site deploy in 6d.

**Checkpoint – Phase 6c is done when:**
- [ ] `npm run build` in `bi/` says `built 6 pages`
- [ ] every page shows its model card, and the Overview says the snapshot comes from production
- [ ] `git status` is clean after the commit (no `node_modules`, no `dist`)
- [ ] the PR is merged

### Refreshing the data later

```bash
cd dbt
dbt parse
cd ..
QA_SCHEMA_PREFIX="" python -m tools.snapshot.export
cd bi
npm run build
```

The export now writes straight into `bi/src/data/`.

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `npm ci` complains about the lock file | `package.json` edited without `npm install` | `npm install`, commit both files |
| a page is blank | a JavaScript error in a cell | the dev server shows the error in the page; or open the browser console |
| `Port 3000 is in use` | another dev server | `npm run dev -- --port 3001` |
| headings in a fallback font | offline: Google Fonts not reachable | cosmetic; the layout uses Helvetica/Arial until online |
| `git status` shows `bi/dist/` | old `.gitignore` | make sure the `.gitignore` from this phase is in place |

---

## 8. Interview lines

> "Every page is decomposed the same way: the question in the reader's words, the decision it supports, the
> grain of the answer, the public dbt model with exactly that grain, the tests that make it trustworthy, and
> only then the chart. I print that chain at the bottom of each page as a model card, linked to the dbt docs."

> "The BI layer does no business logic. Like-for-like changes, price statuses and gate verdicts are computed
> in dbt, tested and contract-enforced; the dashboards filter and draw. When the data-health page needed a
> grain that no public model had, I added a mart in dbt instead of computing it in the dashboard."

> "The price-changes page shows the same September increase twice, on 7 Sep for the weekly markets and on
> 28 Sep for the monthly ones. That's crawl cadence, and it's exactly why Micro and Macro have to read one
> point-in-time history instead of a shared catalogue."

> "The incident page doesn't argue that the redesign was right, it measures it: I replay the old design on
> the same raw files, 10 of 232 date-market cells come out wrong, and the same delivery gate blocks the old
> design on both incident dates while the new design passes."

> "Every page has a dbt exposure that lists exactly the models it reads. So 'what breaks if I change the
> price history?' is `dbt ls -s int_prices__historized+ --resource-type exposure`, and the answer is one page
> and the agent. Building the pages actually let me correct three exposures that over-declared."

> "I chose Observable Framework because the result is a static site that anyone can rebuild from the repo,
> with pinned versions and no account. The trade-off is no SQL in the pages, which suits a BI layer that
> shouldn't contain SQL logic anyway."
