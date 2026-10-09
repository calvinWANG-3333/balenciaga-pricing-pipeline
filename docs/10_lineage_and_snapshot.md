# 10 – Lineage pictures and the BI snapshot (Phase 6b)

> Two small tools that turn the project into material for the portfolio site, both built on artifacts
> dbt already produces: the **lineage pictures** come from dbt's manifest, the **BI data** from the
> published layer.

---

## 0. The big picture

```
dbt parse ──► manifest.json ──► tools/lineage/extract.py ──► graphs/*.json ──► tools/lineage/render.py ──► site/assets/lineage/*.svg
                  ▲                                             ▲
   git archive <phase commit>                       one graph per phase (committed)
   (tools/lineage/collect.py)                       + current.json (today)

production warehouse ──► public models only ──► tools/snapshot/export.py ──► bi/src/data/*.csv + bi/src/data/snapshot_manifest.json
```

| Tool | Reads | Writes | Run |
|---|---|---|---|
| `tools/lineage/collect.py` | the dbt project at a git commit (or today's `dbt/target/manifest.json`) | `tools/lineage/graphs/<phase>.json` | once per phase; `--current` on every site build |
| `tools/lineage/render.py` | the graphs + `phases.yml` | `site/assets/lineage/lineage_full.svg`, `lineage_<phase>.svg` | every site build |
| `tools/snapshot/export.py` | the warehouse's **public** models | 10 CSV files + a manifest | when the data changes |

---

## 1. Lineage pictures: the DAG as it really was, phase by phase

**Plain.** A time-lapse of a building site, taken from the same tripod. Every photo has the same frame,
so you see each floor appear where it will stay. Floors not built yet are drawn as faint outlines, so you
always know where the building is going.

**Term.** dbt's **manifest** (`target/manifest.json`, written by `dbt parse`) is the compiled graph of
the project: every model, source, seed, semantic model and exposure, and their `depends_on` edges. The
lineage tab of dbt docs is drawn from it. Here we draw our own pictures from it, for three reasons:

1. **History.** dbt docs only shows today. Each phase's picture is compiled from the commit that closed
   that phase (`git archive <ref> dbt` → `dbt deps` → `dbt parse`). It is not today's graph with parts
   greyed out. For example, in Phase 4 the exposures read the marts directly; in Phase 5a they were
   repointed to the published views. Both pictures show that truthfully.
2. **One layout for every picture.** The layout is computed once, on the union of all phases, so a node
   never moves between pictures.
3. **Code, not screenshots.** The pictures are regenerated from the manifest, so they cannot drift from
   the code. The renderer is pure Python and deterministic: a changed SVG in a pull request always
   means a changed DAG.

### How to read a picture

| Mark | Meaning |
|---|---|
| black box | added in this phase |
| outlined box | built in an earlier phase |
| faint dashed box | still to come |
| black arrow | a dependency touching a node added in this phase |
| pill | exposure (a consumer: a dashboard, the agent) |
| dashed outline | semantic model |
| notch on the left | seed |
| band at the bottom | the quality lane: it reads the pipeline, the pipeline never reads it |

### The layout, in four rules

1. **Columns follow the layers**, left to right: sources · seeds, staging, intermediate, marts,
   published, semantic layer, exposures.
2. **A model sits one column right of its right-most parent.** So a layer whose models build on each
   other (intermediate: deliveries → observations → prices → catalogue) spreads over several columns, and
   every arrow points right. A test asserts it.
3. **The quality lane is its own band**, under the main flow. No main-flow model reads it (checked on
   the graph), which is the design rule of the QA lane.
4. **Barycenter ordering**: inside a column, each node is placed near the average height of its parents,
   which keeps most arrows short and straight. This is the classic heuristic of layered graph drawing
   (the Sugiyama method used by Graphviz).

### Phases

`tools/lineage/phases.yml` pins each phase to the merge commit that closed it:

| Phase | Commit | Nodes | Added |
|---|---|---:|---|
| 2 – sources, staging, raw QA | `714bb7f` (PR #3) | 11 | crawl source, base + staging, raw QA lane, answer-key grading |
| 3 – intermediate | `88fb885` (PR #4) | 25 | delivery trust, fates, categorization seeds, SCD2, point-in-time catalogue, legacy replay |
| 4 – marts | `f38aefe` (PR #5) | 38 | star schema, Micro and Macro marts, `markets` seed, exposures |
| 5a – delivery gate | `b06a051` (PR #6) | 50 | ops source, published views, data-health mart; exposures repointed |
| 5b – semantic layer | `8368103` (PR #7) | 54 | semantic models, time spine |
| 6a – production and CI | `7f85f4d` (PR #9) | 56 | `stg_ops__*` (marts no longer read sources) |

Phase 1 (bronze ingestion) happens outside dbt and has no picture of its own; its tables appear as
sources in Phase 2. Today's graph (`current.json`) adds `mart_data_health__check_results`, built in this
phase.

---

## 2. The BI snapshot: the public interface, frozen in files

**Plain.** The site is a printed magazine, not a live TV feed. Before printing, someone photographs the
shop window. They do not go into the warehouse: only what is on display, which the gate has already
approved.

**Term.** `tools/snapshot/export.py` runs the queries listed in `tools/snapshot/snapshot.yml`, writes one
CSV per table and a manifest with row counts, sha256 checksums and where the data came from (backend,
schemas, git commit). It reuses the delivery gate's connection settings (`QA_BACKEND`,
`QA_SCHEMA_PREFIX`, `DATABRICKS_*`).

Three guarantees, checked **before** anything is written:

| Check | Why |
|---|---|
| every exported model has `access: public` in the dbt manifest | BI depends only on the governed interface (contracts, documented columns), never on an internal model |
| at least one delivery is released | an empty published layer means the gate has not run |
| every Micro / Macro delivery date is a released delivery | the dashboards can never show a delivery the gate did not release |

The columns come from the models' contracts (also read from the manifest), so the CSV headers are the
contract.

| File | Model | Rows (reference run) |
|---|---|---:|
| `hero_prices_weekly.csv` | `pub_micro__hero_prices_weekly` | 832 |
| `category_monthly.csv` | `pub_macro__category_monthly` | 192 |
| `category_monthly_global.csv` | `pub_macro__category_monthly_global` | 8 |
| `price_changes.csv` | `pub_fct_price_changes` | 6,681 |
| `products.csv` | `pub_dim_product` | 2,001 |
| `markets.csv` | `pub_dim_market` | 16 |
| `released_deliveries.csv` | `pub_released_deliveries` | 16 |
| `gate_deliveries.csv` | `mart_data_health__deliveries` | 32 |
| `gate_check_results.csv` | `mart_data_health__check_results` (**new**) | 1,264 |
| `incident_replay.csv` | `qa_incident__legacy_vs_point_in_time` | 232 |

About 1.8 MB in total. The 360,000-row point-in-time catalogue is deliberately not exported: no page needs
it row by row.

### New public model: `mart_data_health__check_results`

The data-health page needs each check's result per delivery, to draw a grid of deliveries × checks. That
detail lived only in `stg_ops__qa_check_results`, a staging model BI must not read. So the gate's latest
run per delivery is now exposed as a public mart: a view (the gate writes after dbt runs), with an
enforced contract, every column documented (doc blocks added to `models/docs/public_columns.md`), a
primary-key test on (dataset, scope, as_of_date, check_id, subject), and `accepted_values` on `status`.
The `data_health_page` exposure now depends on it.

dbt-project-evaluator caught one thing on the first run: an exposure whose parent is a view. It is the same
deliberate choice as for `mart_data_health__deliveries`, so the documented exception now covers the
`mart_data_health__%` family instead of one model. Back to 77 / 77.

---

## 3. Your steps

### Step 0 – repair the git state I broke

While collecting the history I ran `git checkout main` and `git pull` on your machine. That was a
mistake: the remote shell cannot finish git writes, the checkout aborted half-way and left your local
`main` pointing at an old commit. **No file was lost.** I checked every file of `origin/main` against
your working tree: all 151 identical. I moved the two lock files aside. One duplicate file was
re-created; it is removed below.

```bash
cd ~/Documents/LY_data_pipeline_CV_project/balenciaga-pricing-pipeline
git status                                   # should work (no "index.lock exists" error)
git reset origin/main                        # moves main to 7f85f4d; keeps every file on disk as it is
rm dbt/models/quality/intermediate/qa_int__price_scale_outliers.sql
rmdir dbt/models/quality/intermediate
rm -f .git/stale-index-lock-from-claude .git/stale-ORIG_HEAD-lock-from-claude
git status                                   # only the Phase 6b files listed below
```

From now on I only run **read-only** git commands on your machine.

### Step 1 – the code (first PR)

The 6b files are already in your working tree: `git reset origin/main` (without `--hard`) moves the branch and keeps every file on disk.

```bash
git checkout -b phase-6b/lineage-snapshot
mv ci/ci.yml.next .github/workflows/ci.yml     # adds tools/tests to the CI test run
git add -A
git commit -m "feat: lineage pictures from dbt manifests (per phase, from git), BI snapshot of the public interface, check-results mart"
git push -u origin phase-6b/lineage-snapshot
```

Open the PR. Slim CI builds the new mart and the exposure's parents; the evaluator checks the new
public model (contract, docs, PK test). Merge. **Deploy production** then builds the new view in
production.

### Step 2 – the snapshot, from production (second PR)

```bash
git checkout main && git pull
git checkout -b phase-6b/bi-snapshot
cd dbt && dbt parse && cd ..                   # the export reads access + contracts from the manifest
QA_SCHEMA_PREFIX="" python -m tools.snapshot.export
cat bi/src/data/snapshot_manifest.json | head -12       # "schema_prefix": "(production)", 16 released deliveries
git add bi/ && git commit -m "data: BI snapshot from production" && git push -u origin phase-6b/bi-snapshot
```

> Phase 6c moved the snapshot from `bi/sources/pricing/` to `bi/src/data/`, where the BI site reads it
> (see [11_bi_pages.md](11_bi_pages.md)); `snapshot.yml` holds the path, so the command is unchanged.

This PR changes only CSV files. Slim CI finds no modified dbt node, so it builds nothing, and the
evaluator still runs. That is the right behaviour.

### Step 3 – look at the pictures

Open `site/assets/lineage/lineage_full.svg` and `lineage_p2.svg` … `lineage_p6a.svg` in your browser
(drag the file onto a tab). Scroll from p2 to p6a: the pipeline grows in place.

**Checkpoint – Phase 6b is done when:**
- [ ] after step 0, `git log -1` on `main` shows 7f85f4d and `git status` lists only the 6b files
- [ ] PR 1 merged, deploy green, `workspace.marts.mart_data_health__check_results` exists
- [ ] PR 2 merged, `bi/src/data/snapshot_manifest.json` says production, 10 tables
- [ ] `python -m pytest tools/tests agent/tests qa/tests` = 83 passed

---

## 4. Regenerating

| When | Command |
|---|---|
| the DAG changed (any model PR) | `cd dbt && dbt parse && cd .. && python -m tools.lineage.collect --current && python -m tools.lineage.render` (the site build will do this automatically, Phase 6d) |
| a new phase is closed | add it to `phases.yml` with its merge commit, `python -m tools.lineage.collect --phase <id>`, render |
| the data changed | step 2 again |
| check the committed snapshot against the warehouse | `QA_SCHEMA_PREFIX="" python -m tools.snapshot.export --check` |

---

## 5. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `dbt/target/manifest.json not found` | `dbt parse` not run | `cd dbt && dbt parse` |
| `Refusing to export non-public models` | a model in `snapshot.yml` is not `access: public` | make it public (with contract + docs), or export a public model instead |
| `No released delivery` | the gate has not run on that environment | `python -m qa.gate audit` (with the same `QA_SCHEMA_PREFIX`) |
| `collect --phase` fails at `dbt deps` | no network to hub.getdbt.com | run it where `dbt deps` works; the committed graphs do not need it |
| a picture looks crowded | the DAG grew | expected: the layout widens; the site shows pictures in a scrollable frame |

---

## 6. Interview lines

> "My lineage diagrams are generated from dbt's manifest, not drawn by hand. For each phase, a script
> extracts the project at the commit that closed the phase, runs dbt parse and keeps the graph. All the
> pictures share one layout, so you watch the DAG grow, including changes like exposures moving from the
> marts to the published layer when I added the delivery gate."

> "The BI site is built from a snapshot of the public interface only. The export reads dbt's manifest and
> refuses any model that isn't access: public. It also checks that every delivery in the data was released
> by the gate. The CSV headers are the model contracts."

> "When the data-health page needed per-check results, I didn't point BI at a staging model. I added a
> public mart with a contract, documented columns and a primary-key test, so the dashboard depends on a
> governed interface."
