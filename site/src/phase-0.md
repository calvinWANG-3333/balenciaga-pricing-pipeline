---
title: Phase 0 · Environment
---

```js
import {chapterHead, lineageSection, pager} from "./components/chapter.js";
display(chapterHead("p0", "Before any data work, I set up the three places this project lives: a cloud database that stores data and runs queries, a tool where the data transformations are written as code, and GitHub, which keeps every version of that code. This phase only proves they can talk to each other. I type one command in the editor, and a new view (a saved query that behaves like a table) appears in the database."));
```

<section class="block"><div class="label">01 Problem</div><div class="content">

The project needs three things. A place to store data and run queries on it. A place to write the transformations as
code. A history of every version of that code, so each change can be reviewed before it goes live.

These are three separate tools, and nothing else can start until they are connected. Each connection also settles who
can touch what: which tool loads raw files, which one builds tables, and where a developer's half-finished work lands.

That last question matters here. The incident this project fixes started with one shared table that anyone could
overwrite. A shared development area has the same weakness, so the setup has to rule it out from day one.

</div></section>

<section class="block"><div class="label">02 Decision</div><div class="content">

Three tools, one job each. **Databricks** stores and computes. **dbt** describes the transformations as code.
**GitHub** versions that code. In a company the warehouse is shared and code is reviewed through pull requests; dbt is
the contract between them.

Loading raw files stays outside dbt. I create the `raw` schema and its landing volume by hand in SQL, because loading
is the EL of ELT and dbt only does the T.

| Piece | Name | Why |
|---|---|---|
| Catalog | `workspace` | Unity Catalog names every table `catalog.schema.table` |
| Bronze schema | `workspace.raw` | Raw data exactly as delivered, filled in Phase 1 |
| Landing volume | `workspace.raw.landing` | The folder where crawl files are dropped |
| dbt project | `balenciaga_pricing`, in `dbt/` | The repo also holds the generator, the agent and the BI site |
| Dev schema | `dbt_rwang` | My work in progress never overwrites anyone else's |
| Compute | Serverless SQL warehouse | Starts in seconds and stops when idle |

</div></section>

<section class="block"><div class="label">03 Rejected<span>The alternatives I considered, and why not.</span></div><div class="content">

| Alternative | Why not |
|---|---|
| One tool for everything | Separation of concerns is the point. A company runs exactly this split: a shared warehouse, reviewed code, and dbt between them. Learning it is why the project exists. |
| Let dbt load the raw files | Loading is EL, and dbt only does the T. Bronze is filled by an idempotent `COPY INTO` in Phase 1, and dbt reads it as a declared source. |
| One shared development schema | Half-finished models would overwrite each other. That is the disease this project cures, applied to developers. |
| OAuth or a service principal | The right choice in a company. For a single-developer free workspace a personal access token is pragmatic. It lives in a password manager, never in the repo. |
| A public repo from day one | The price calibration comes from a former employer's exports, as aggregates only. Keeping the data was approved; publishing it is a separate question, asked before the repo goes public. |

</div></section>

<section class="block"><div class="label">04 Tools and features<span>What each one does in this phase.</span></div><div class="content">

| Feature | What it does here |
|---|---|
| Unity Catalog | Three-level names, like building, room and shelf: `workspace.raw.crawl_lines`. |
| Volume | A folder for raw files inside Unity Catalog: `/Volumes/workspace/raw/landing/`. |
| Serverless SQL warehouse | Compute that runs SQL. Free Edition allows one, size 2X-Small, plenty for about 240k rows. |
| Personal access token | A password for programs, so dbt can reach Databricks. Lifetime 90 days, shown only once. |
| dbt development credentials | My own token and my own schema, `dbt_rwang`, used only when I work in the IDE. |
| Studio IDE and branches | Work happens on `phase-0/init-dbt`. `main` stays clean until the pull request is merged. |

```pgsql
-- docs/01_environment_setup.md, step 0.3
-- bronze layer: raw data exactly as delivered (filled in Phase 1, not by dbt)
CREATE SCHEMA IF NOT EXISTS workspace.raw
  COMMENT 'Bronze: raw crawl lines exactly as delivered, append-only';

-- landing zone: the folder where crawl files are dropped
CREATE VOLUME IF NOT EXISTS workspace.raw.landing
  COMMENT 'Landing zone for crawler NDJSON files';
```

</div></section>

```js
display(lineageSection("p0", null));
```

<section class="block"><div class="label">06 Proof<span>The checkpoints that close the phase.</span></div><div class="content">

| Checkpoint | Result |
|---|---|
| `dbt debug` | Every connection check says OK |
| `dbt run` | The 2 example models build in `workspace.dbt_rwang` |
| `my_first_dbt_model` | A table, visible in the Databricks catalog |
| `my_second_dbt_model` | A view, visible in the Databricks catalog |
| GitHub repo | Private; `main` holds `dbt/dbt_project.yml` and no `data/` folder |
| Landing volume | `workspace.raw.landing` exists |

<p class="cap">About 1.5 hours of setup, at a cost of €0: Databricks Free Edition and the dbt Developer plan, which allows 3,000 successful model builds per month.</p>

</div></section>

```js
display(pager("p0"));
```
