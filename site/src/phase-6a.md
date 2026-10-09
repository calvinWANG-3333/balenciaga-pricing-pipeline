---
title: Phase 6a · Production + CI
---

```js
import {chapterHead, lineageSection, pager} from "./components/chapter.js";
display(chapterHead("p6a", "Until now everything ran in my own test space, so whatever I tried out was also what the client saw. This phase splits it in three: my workspace, a throw-away copy for every proposed change, and production, the version clients and dashboards read, which only changes after automatic checks pass. A second set of checks inspects the project itself against the official best-practice rules of the tool I build it with."));
```

<section class="block"><div class="label">01 Problem</div><div class="content">

Phases 0 to 5 built the whole pipeline in one development schema, `dbt_rwang_*`. There was one kitchen: what I tasted was what the client got. Nothing stopped a broken change from reaching a dashboard.

Testing a change properly meant rebuilding the whole project: 191 nodes, about 6 minutes, on a Free Edition warehouse with a daily compute quota. That is too slow and too costly to do on every change.

Two more gaps. No rule said which models BI and the agent may rely on, so renaming a column could break a dashboard a week later. And nothing checked the structure of the project itself, for example a mart that reads a raw source directly.

</div></section>

<section class="block"><div class="label">02 Decision</div><div class="content">

**One project, three environments, one source of truth: GitHub `main`.** The schema rule from Phase 0 (`generate_schema_name`) already maps each dbt target to its own schemas.

| Target | Schema of a model with `+schema: marts` | Who uses it |
|---|---|---|
| `dev` (Studio) | `dbt_rwang_marts` | me |
| `ci` | `ci_pr_12_marts` | one pull request |
| `prod` | `marts` | BI, the agent, the site |

Three GitHub Actions workflows run it. `ci.yml` runs on every pull request: lint, 70 unit tests, `dbt parse`, then **Slim CI** on Databricks and **dbt-project-evaluator** in strict mode. `deploy.yml` runs on every merge: build production, then the delivery gate audits and publishes, then docs, then it saves the production manifest for the next pull request. `ci-cleanup.yml` drops a closed PR's schemas. A branch ruleset requires both CI checks, so production only changes through a tested pull request.

The models BI reads become a **public interface**: 10 models with `access: public` and enforced contracts.

</div></section>

<section class="block"><div class="label">03 Rejected<span>The alternatives I considered, and why not.</span></div><div class="content">

| Alternative | Why not |
|---|---|
| A dbt platform job for production | The pipeline is more than dbt. The Python delivery gate must run between the dbt build and the release. One orchestrator, written and reviewed as code, runs both. |
| A full build on every pull request | 191 nodes in about 6 minutes, against 48 nodes in 44 s with Slim CI. The Free Edition quota punishes full builds. |
| Run the evaluator everywhere | It is enabled only in CI, so it never costs a model build in Studio or production. |
| Turn every finding into a fix | Some findings are design. The published views stay views because they are the write-audit-publish switch. Each exception is a row with a written reason. |

</div></section>

<section class="block"><div class="label">04 dbt features<span>What each one does in this phase.</span></div><div class="content">

| Feature | What it does here |
|---|---|
| Targets + `generate_schema_name` | One project writes to `dbt_rwang_*`, `ci_pr_<n>_*` or bare names, depending on the target. |
| `state:modified+` | Compares the PR to the production `manifest.json` and selects changed nodes plus everything downstream. |
| `--defer` | A `ref()` to a node that is not rebuilt reads the production relation instead. |
| dbt-project-evaluator | Loads the project's own DAG into tables and tests it against about 30 rules. `SEVERITY=error` makes a new violation fail the PR. |
| `access: public` + enforced contracts | The 10 public models declare every column's name and type. A type change fails the build before a dashboard sees it. |
| Doc blocks | 99 column descriptions written once in `models/docs/public_columns.md`, so a column never gets two explanations. |
| Source freshness | The gate's `ops` tables warn after 8 days without a gate run. |

```bash
# .github/workflows/ci.yml, step "Build changed models + downstream"
if [ "${HAS_PROD_STATE:-false}" = "true" ]; then
  dbt build --target ci --select state:modified+ --defer --state "$GITHUB_WORKSPACE/prod-state"
else
  dbt build --target ci
fi
```

</div></section>

```js
display(lineageSection("p6a", await FileAttachment("lineage/lineage_p6a.svg").text()));
```

<section class="block"><div class="label">06 Proof<span>Slim CI measured in the local lab; the gate numbers come from the first production deploy.</span></div><div class="content">

<div class="versus">
  <div><span class="micro">Slim CI</span><b>48</b><p>nodes built in 44 s for a one-line change to one mart</p></div>
  <div><span class="micro">Full build</span><b>191</b><p>nodes built in about 6 minutes for the same change</p></div>
</div>

| Check | Result |
|---|--:|
| dbt-project-evaluator, first run | 15 findings |
| dbt-project-evaluator, after fixes and exceptions | 77 / 77 pass, strict mode |
| First deploy: deliveries audited by the gate | 16 |
| First deploy: released | 11 PASS, 5 WARN |
| `market` declared as `int` in the `pub_dim_market` contract | build fails: `data type mismatch` |

<p class="cap">The 48 nodes: the changed mart, its 3 downstream models, their tests, and the <code>ops</code> staging views. Those views are rebuilt in every PR on purpose, because their source points at an environment-specific schema. They are views, so this costs nothing.</p>

</div></section>

```js
display(pager("p6a"));
```
