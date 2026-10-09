# 09 – Production, CI/CD and project governance (Phase 6a)

> Phases 0–5 built the pipeline in a development schema (`dbt_rwang_*`). This phase makes it a
> **product**: a production environment that only changes through reviewed pull requests, an automated
> check of every change, and governance rules that dbt itself enforces.

---

## 0. The big picture

**Plain.** Until now there was one kitchen, the dev kitchen: you cooked, you tasted, and what you tasted was
what the client got. A real restaurant has a **test kitchen** where every new recipe is tried before it
reaches the dining room, and a **dining room** that only serves recipes that passed. Two rules:
nobody cooks in the dining room by hand, and the test kitchen only re-cooks the dishes the recipe change
affects, not the whole menu.

**Term.** Three environments, one source of truth (GitHub `main`):

```
                 you (dbt Studio)                    GitHub Actions (dbt Core + Python)
                 ────────────────                    ──────────────────────────────────
  dev            dbt_rwang_*         ── git push ──►  pull request
                                                         │  CI: checks + Slim CI    → ci_pr_<n>_*   (throw-away)
                                                         │  branch protection: both must pass
                                                         ▼
                                                      merge to main
                                                         │  Deploy: WRITE → AUDIT → PUBLISH
                                                         ▼
  prod                                                staging, intermediate, marts, published, ops ... (bare names)
                                                         │
                                                         ▼  manifest.json saved = "production state" for the next PR
```

| Workflow | When | What |
|---|---|---|
| `.github/workflows/ci.yml` | every pull request | lint, 70 unit tests, `dbt parse`; then **Slim CI** on Databricks and **dbt-project-evaluator** in strict mode |
| `.github/workflows/deploy.yml` | every merge to `main` | `dbt build --target prod` → delivery gate (audit + publish) → `dbt docs generate` → save the production manifest |
| `.github/workflows/ci-cleanup.yml` | a pull request is closed | drops that PR's `ci_pr_<n>_*` schemas |

Why GitHub Actions and not a dbt platform job: the pipeline is not only dbt. Write-audit-publish needs the
Python delivery gate to run **between** the dbt build and the release, in the same pipeline. One
orchestrator, written as code and reviewed like code, runs both. dbt Studio stays the development IDE.

---

## 1. Environments: one project, three sets of schemas

**Plain.** The same recipes, three kitchens. Which kitchen you are in decides which shelves you put things on.

**Term.** A dbt **target** is a named connection in `profiles.yml`. The project already had the rule
(`macros/generate_schema_name.sql`, Phase 0):

| Target | Schema of a model with `+schema: marts` | Who uses it |
|---|---|---|
| `dev` (Studio) | `dbt_rwang_marts` | you |
| `ci` | `ci_pr_12_marts` (from `DBT_CI_SCHEMA`) | one pull request |
| `prod` | `marts` | everyone downstream: BI, the agent, the site |

`ci/profiles.yml` is committed, which is unusual for a profile. It holds no secret: every credential is
`{{ env_var(...) }}`, filled at run time from GitHub Secrets. `.gitignore` still ignores every other
`profiles.yml`.

The gate follows the same environments: `QA_SCHEMA_PREFIX=""` in production means bare names
(`marts`, `ops`), exactly like `generate_schema_name`.

---

## 2. Slim CI: test only what changed, read the rest from production

**Plain.** You changed one recipe. Re-cooking the whole menu to test it wastes an hour; cooking only that
dish (and the dishes made from it) takes five minutes. For the ingredients you did not touch, you borrow
them from the dining room's fridge instead of preparing them again.

**Term.** Two dbt features:

- **State comparison**: `--state <dir>` points at the production `manifest.json` (dbt's compiled map of
  the project). `--select state:modified+` selects every node whose code or config differs from production,
  **plus everything downstream** (`+`).
- **Deferral**: `--defer` makes every `ref()` to a node that is not being built resolve to its production
  relation. So the PR's new `mart_macro__category_monthly` reads production `int_catalogue__as_of`
  without rebuilding it.

```bash
dbt build --target ci --select state:modified+ --defer --state "$GITHUB_WORKSPACE/prod-state"
```

Where the production manifest comes from: the deploy workflow uploads `dbt/target/manifest.json` as an
artifact (`prod-state`, kept 90 days); the CI job downloads the one from the latest successful deploy with
the GitHub CLI. Before the very first deploy there is no state, and CI builds everything.

**Measured in the local lab** (one comment added to `mart_macro__category_monthly`):

| | Nodes | Time |
|---|---:|---:|
| Full build | 191 | ~6 min |
| Slim CI | 48 | 44 s |

The 48: the changed mart, its 3 downstream models, their tests, and the `ops` staging views. Those are
rebuilt in every PR on purpose: the `ops` source points at an environment-specific schema
(`ci_pr_12_ops` vs `ops`), so dbt sees it as modified. They are views, so this costs nothing.

**Clean-up.** When the PR closes, `dbt run-operation drop_ci_schemas --args "{prefix: ci_pr_12}"` drops
`ci_pr_12_*`. The macro refuses any prefix not starting with `ci_pr_` (tested: `dbt_rwang` is refused) and
matches the prefix exactly, so `ci_pr_1` never drops `ci_pr_12_*`.

---

## 3. dbt-project-evaluator: the project is checked against dbt Labs' best practices

**Plain.** A building inspector who does not taste the food but checks the kitchen itself: is raw meat
stored next to desserts, does every dish have a label, is there a fire exit.

**Term.** [`dbt-project-evaluator`](https://dbt-labs.github.io/dbt-project-evaluator/) is a dbt Labs
package that loads the project's own DAG into tables and tests it against ~30 rules: modeling (marts must
not read sources), testing (every model has a primary-key test), documentation, structure (folders,
naming), performance (long chains of views), governance (public models have contracts).

It is **enabled only in CI** (`DBT_PROJECT_EVALUATOR_ENABLED=true`, flags at the bottom of
`dbt_project.yml`), so it never costs a model build in Studio or production. CI runs it with
`DBT_PROJECT_EVALUATOR_SEVERITY=error`: a new violation fails the pull request.

### What the first run found, and what was done (all 15 findings)

| Rule | Finding | Decision |
|---|---|---|
| marts or intermediate read a source | `mart_data_health__deliveries` read `source('ops', ...)` | **fixed**: new `staging/ops/stg_ops__qa_check_results`, `stg_ops__delivery_releases`; marts and published views read them |
| source fan-out, multiple sources joined, source directory | same root cause | **fixed** by the same staging models; `_ops__sources.yml` moved to `staging/ops/` |
| sources without freshness | `ops.*` | **fixed**: freshness on `checked_at` / `released_at` (warn after 8 days without a gate run) |
| missing primary-key tests, test coverage 80% | the 7 `pub_*` views, `qa_raw__repaired_values` | **fixed**: PK tests on every published view; coverage 100% |
| naming conventions | `mart_*`, `pub_*`, `qa_*` | **fixed by declaring our conventions** in `vars.dbt_project_evaluator`: `mart_` = a client deliverable at report grain, next to `fct_`/`dim_`; `published` and `quality` model types |
| a model in a folder named `intermediate` under `quality/` | classified as intermediate | **fixed**: folder renamed `quality/outliers/` |
| hard-coded reference | `from "clean"` in a **comment** of `base_crawl__lines` | **false positive, reworded** |
| exposures depend on private models | exposures read protected models | **fixed: governance** (section 4) |
| exposure parents are views | `pub_*`, `mart_data_health__deliveries` | **exception**: views are the write-audit-publish switch |
| model fan-out | `pub_released_deliveries`, `stg_crawl__product_observations` | **exception**: the release filter and the QA lane, by design |
| direct join to source, unused sources, no freshness | the `answer_key` source | **exception**: grading ground truth, not pipeline input |
| test directories | tests in one properties file per layer | **rule disabled, with the reason** in `dbt_project.yml` |

Exceptions live in `seeds/dbt_project_evaluator_exceptions.csv`. Each row has the rule, the model and a
written reason, reviewed like code. **Result: 77 / 77 checks pass in strict mode.**

---

## 4. Governance: a public interface with contracts

**Plain.** The kitchen has many prep stations, but the dining room only sees the menu. Changing a prep
station is free; changing the menu needs care, because customers rely on it.

**Term.** dbt **model access** (`access: public | protected | private`) declares which models other
projects, exposures and tools may rely on. **Model contracts** (`contract: {enforced: true}`) declare every
column's name and data type, and dbt checks them **before** building: a change that would rename a column
or turn a `decimal` into a `string` fails the build where it happens, not in a dashboard a week later.

The public interface (10 models):

- `published/*`: `+access: public` and `+contract: {enforced: true}` set once for the folder in `dbt_project.yml`
- `mart_data_health__deliveries` (data-health page, triage agent)
- `qa_incident__legacy_vs_point_in_time` (incident page)

Every column of every public model is documented through **doc blocks** in `models/docs/public_columns.md`.
99 descriptions are written once and referenced with `{{ doc('col_market') }}`, so a column never gets two
different explanations.

**Verified**: declaring `market` as `int` in the `pub_dim_market` contract fails the build with
`| market | string | int | data type mismatch |`.

---

## 5. The production pipeline: write, audit, publish

```
merge to main
   │
   ├─ WRITE    dbt build --target prod              models + 140 tests into production schemas
   │            └─ a failing test stops here: nothing is audited, nothing is published
   ├─ AUDIT    python -m qa.gate audit              measures every not-yet-released delivery
   ├─ PUBLISH  (same step)                          releases PASS / WARN; a BLOCK stays unpublished
   │            └─ BLOCK → the workflow fails → GitHub notifies you; triage with python -m agent triage
   ├─        python -m qa.gate audit --dataset legacy_replay   (audit-only: the incident page)
   ├─ DOCS     dbt docs generate --target prod
   └─ STATE    upload manifest.json, catalog.json, run_results.json, semantic_manifest.json
```

The job page shows a summary: node counts, every failed node, and the gate's markdown report
(`ci/summarize_run.py` turns `run_results.json` into a table).

---

## 6. Your steps

### Step 1 – a Databricks token for GitHub Actions

Databricks → your avatar (top right) → **Settings** → **Developer** → **Access tokens** → **Generate new
token**. Comment `github-actions`, lifetime **90 days**. Copy it once, into the GitHub secret below,
nowhere else. Write the expiry date in your calendar: an expired token fails CI with an authentication
error.

Use a separate token from the one on your laptop, so you can revoke either one without breaking the other.

### Step 2 – before going public

1. GitHub → **Branches** → delete `to-delete`, `studio-clean-`, `trash/studio-cleanup`,
   `calvinWANG-3333-studio-cleanup-2`, `phase-5a/delivery-gate`, `phase-5b/semantic-layer-agent`
   (Studio on `main` first).
2. **Settings → General → Danger zone → Change visibility → Public.**

The history was scanned before this step: no token, no key, no real export in any of the 24 commits.

### Step 3 – the three secrets

**Settings → Secrets and variables → Actions → New repository secret**, three times, same values as your
local exports:

| Name | Value |
|---|---|
| `DATABRICKS_SERVER_HOSTNAME` | the host only, no `https://`, no trailing `/` |
| `DATABRICKS_HTTP_PATH` | `/sql/1.0/warehouses/...` |
| `DATABRICKS_TOKEN` | the token from step 1 |

In a public repository, secrets stay secret: they are masked in logs and never given to pull requests
from forks (the workflows skip the Databricks jobs for forks).

### Step 4 – commit on a branch, refresh the package lock

```bash
git checkout main && git pull
git checkout -b phase-6a/production-ci
cd dbt && dbt deps && cd ..           # adds dbt_project_evaluator to package-lock.yml
git add -A
git commit -m "feat: production + Slim CI on GitHub Actions, dbt-project-evaluator, public interface with contracts"
git push -u origin phase-6a/production-ci
```

Studio: switch to the branch, **Pull**, `dbt build`. Expected: 0 errors, about 190 nodes (the local lab: 186 PASS). The evaluator does not run there.

### Step 5 – the first pull request

Open the PR. In the **Checks** tab:

- `Lint, unit tests, dbt parse` (~2 min)
- `Slim CI on Databricks`: the first time, "No production state yet: this run builds the whole project"
  (~6–8 min on the 2X-Small warehouse), then the evaluator (77 checks)

Click a job → **Summary** to see the tables.

### Step 6 – merge, watch the first deployment

Merge (merge commit). **Actions → Deploy production**: build, gate (16 deliveries audited, 11 PASS /
5 WARN released; the legacy replay audited), docs, state. In Databricks the production schemas appear:
`workspace.staging`, `workspace.marts`, `workspace.published`, `workspace.ops` ...

### Step 7 – protect `main`

**Settings → Rules → Rulesets → New branch ruleset** for `main`: require a pull request, require status
checks `Lint, unit tests, dbt parse` and `Slim CI on Databricks`, block force pushes. From now on
production only changes through a reviewed, tested PR.

### Step 8 – see Slim CI do its job

A tiny PR: add one line to the header comment of `models/marts/macro/mart_macro__category_monthly.sql`.
CI now builds the mart and its downstream models only, deferring everything else to production. The
Summary shows the node count.

Why the SQL file and not the description in `_marts__models.yml`: `state:modified` compares a model's
code, config, contract and relation. A description is only compared when it is persisted to the
warehouse (`persist_docs`), which this project does not do, so a description-only change selects nothing.

**Checkpoint – Phase 6a is done when:**
- [ ] the repository is public, with the three secrets
- [ ] a PR shows both checks green, the evaluator at 77/77
- [ ] the first deploy is green and the production schemas exist
- [ ] `main` is protected by the ruleset
- [ ] a second PR shows Slim CI building only the changed models

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Env var required but not provided: 'DATABRICKS_...'` | secret missing or misnamed | names must match the table in step 3 exactly |
| `Invalid access token` / 403 | token expired or revoked | new token (step 1), update the secret |
| CI: "No production state yet" | no successful deploy on `main` yet | expected before the first merge |
| Slim CI builds almost everything | the PR changed `dbt_project.yml`, a macro or `packages.yml`: every node using them counts as modified | expected; normal PRs build a handful of nodes |
| evaluator step fails | the PR introduced a new violation | the Summary names the rule and the model: fix it, or add a row with a reason to `seeds/dbt_project_evaluator_exceptions.csv` |
| contract error `data type mismatch` | a public model's column changed type | intended change: update the contract in the same PR (consumers must be told). Otherwise a bug was caught |
| deploy fails at the gate step | a delivery was BLOCKED | read the gate report in the Summary; `python -m agent triage` explains it; release by hand only with `qa.gate release --force --reason` |
| Databricks compute shut down for the day | Free Edition daily quota reached | wait until tomorrow; avoid re-running full builds |
| `dbt deps` in CI: lock does not match `packages.yml` | `package-lock.yml` not committed after changing packages | run `dbt deps` locally, commit `package-lock.yml` |

---

## 8. Interview lines

> "Production only changes through pull requests. Every PR runs Slim CI: dbt compares the PR to the
> production manifest, builds only the modified models and their descendants into a throw-away schema,
> and defers everything else to production. On my project a one-model change builds 48 nodes in under a
> minute instead of 191."

> "Deployment is write-audit-publish as a pipeline: dbt builds production, my Python delivery gate audits
> every new delivery, and only what passes is released to BI. A blocked delivery fails the workflow, so
> someone is notified, but it never reaches a dashboard."

> "I ran dbt Labs' project evaluator on my own project. It found 15 rule violations. I fixed the real ones:
> marts reading sources directly, missing primary-key tests, an untested public layer. For the rest I
> recorded documented exceptions, like views that are deliberately views because they are the release
> switch. It now runs in CI in strict mode, so the project can't drift back."

> "The published layer is a governed public interface: access public, enforced contracts and every
> column documented with shared doc blocks. A type change in a public model fails the build, not the
> dashboard."
