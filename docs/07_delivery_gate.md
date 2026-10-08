# 07 · Phase 5a – The delivery gate: mart → QA → BI, done the way data-product teams do it

**Goal of this phase:** no delivery reaches a client or a dashboard until it has been audited. dbt builds
every delivery into the marts. A Python **delivery gate** checks each delivery against a catalogue of
checks, directly in the warehouse. A **published** layer then exposes only the deliveries the gate has
released. This pattern is called **write-audit-publish**.

**Result of the reference run (local Spark, seed 42):**

| | Marts (the new design) | Replay of the old design |
|---|---|---|
| Deliveries audited | 16 (13 Micro, 3 Macro) | 16 |
| PASS / WARN / BLOCK | 11 / 5 / **0** | 13 / 1 / **2** |
| Blocked | – | **2026-08-18** (KOR, HKG catalogues halved) and **2026-09-15** (8 markets served an August crawl) |
| Check results stored | 690 | 574 |

The gate blocks exactly the two deliveries that went wrong in production, and nothing else. On the new
design it raises 5 warnings, and every one is a real event a client should hear about: stale crawls, prices
carried forward, the September price campaign, and a −11% markdown on one hero sneaker. `dbt build`:
162 PASS, 0 errors. pytest: all 15 tests of the gate pass.

---

## 1. The picture first

```
                 WRITE                          AUDIT                            PUBLISH
          ┌──────────────────┐        ┌──────────────────────────┐       ┌──────────────────────┐
crawls ──►│ dbt build        │───────►│ python -m qa.gate audit  │──────►│ published (views)    │──► BI, agent
          │ marts: EVERY     │ reads  │ 17 checks-as-code        │ PASS/ │ pub_* = marts filtered│
          │ delivery         │ the    │ (qa/checks.yml), run IN  │ WARN  │ to released deliveries│
          └──────────────────┘ ware-  │ the warehouse            │       └──────────────────────┘
                   ▲           house  └────────────┬─────────────┘
                   │                               │ appends
                   │ reads back (source: ops)      ▼
          ┌────────┴─────────────────────────────────────────────┐
          │ ops (append-only Delta tables, created by dbt)       │
          │   qa_check_results    every check of every audit     │──► mart_data_health__deliveries (view)
          │   delivery_releases   what BI may see, and why       │      → "data health" page, triage agent
          └──────────────────────────────────────────────────────┘
```

New in the repository:

```
qa/                         the delivery gate (Python 3.10+)
  checks.yml                the check catalogue - the only file to edit to add a check
  gate.py                   CLI: audit / release / status / checks
  catalog.py evaluate.py    load + validate checks / turn values into verdicts (pure, unit-tested)
  backends.py config.py     Databricks SQL warehouse (or local Spark); settings from env vars only
  report.py                 console + markdown report
  tests/                    pytest: verdict rules, catalogue validation, baseline rule
dbt/macros/ops_tables.sql   creates the two ops tables (on-run-start hook)
dbt/models/published/       pub_* views + pub_released_deliveries
dbt/models/marts/health/    ops source + mart_data_health__deliveries
```

---

## 2. Concepts, one at a time

### 2.1 "The marts are clean" is not the same as "the marts are right"

**Plain.** A factory inspector measures every part against the drawing. That is what dbt tests do. But if
this week one part in four is a different size from last week, every part still matches the drawing on
its own, and the batch is still wrong. Someone has to compare *this batch* with *the previous ones*
before it ships.

**Term.** dbt tests check **invariants**: rules that must hold in every build (unique keys, not-null,
contracts, rows conserved, Micro = catalogue). They protect against the problems you **anticipated**.
A release-time audit checks a **specific delivery against its own history**: is it complete, recent, and
does it behave like a real week? That is where the problems you did *not* anticipate show up. In the
production incident every row was valid, and the batch as a whole was wrong.

So the project uses both, and the two layers do not overlap. Anything dbt already guarantees
(uniqueness, types, row conservation) is deliberately **not** re-checked by the gate.

### 2.2 How data-product teams organise QA

There are five lines of defence, each owning one question:

| Line | When | Question | Typical tooling | Here |
|---|---|---|---|---|
| ① Build-time invariants | every `dbt build` | does the data obey the rules? | dbt tests, model contracts | Phases 2–4 |
| ② Change review | before a PR is merged | how does this code change move the data? | data diff (Datafold) | Phase 6 (CI) |
| ③ **Release gate** | before each delivery is published | may this batch go out? | write-audit-publish | **this phase** |
| ④ Observability | continuously | is anything drifting? | Monte Carlo, Elementary, Databricks data profiling | anomaly rules + health mart |
| ⑤ Certification / contracts | for critical datasets | who vouches for it, what is promised? | Airbnb's Midas, Open Data Contract Standard | contracts (Phase 4) + documented checks |

What none of them do is export to Excel and run a script on the file. Checks run where the data lives,
their results are stored as data, and the results decide whether data is published.

### 2.3 Write-audit-publish and the published layer

**Plain.** A newspaper is printed overnight, but the trucks only leave once the editor has signed off the
proof. Readers never see an unsigned edition.

**Term.** **Write-audit-publish (WAP)**: write the output somewhere consumers cannot see it, audit it,
then publish it atomically. Here:

- **Write** – `dbt build` puts every delivery in the marts. BI does not read the marts.
- **Audit** – the gate runs the check catalogue on each unreleased delivery.
- **Publish** – if no blocking check fails, the gate appends one row to `ops.delivery_releases`. The
  `pub_*` views in the **published** schema filter each mart to released deliveries, so the delivery
  becomes visible to BI the instant that row is written. No copy is made and nothing is recomputed.

Design choices worth defending:

- **The published objects are views**, not tables. A release takes effect immediately, without a dbt run.
  It also cannot drift from the mart, because the view *is* the mart, filtered.
- **The ops tables are created by dbt but written only by the gate.** dbt must not rebuild them (that
  would erase history), so an `on-run-start` hook runs `CREATE TABLE IF NOT EXISTS`. On Databricks they
  are Delta tables with `delta.appendOnly = true`: an audit log nobody can edit after the fact.
- **A blocked delivery is simply absent from `published`**, and its rows are never deleted. A human can
  override with `release --force --reason "..."`. That release is recorded as forced, with the reason, and
  a dbt test (`assert_no_blocked_delivery_is_published`) checks that nothing blocked is published without one.

### 2.4 Checks-as-code, organised by quality dimension

**Plain.** The checklist is a file under version control, not knowledge in someone's head or cells in a
spreadsheet. Changing a threshold is a reviewed pull request.

**Term.** `qa/checks.yml` declares every check: an id, a **dimension**, a **severity**, the scopes it
applies to, a description, its rules and its SQL. The dimensions follow the usual data-quality taxonomy,
reduced to the five that matter for a delivery. Each check belongs to exactly one dimension.

| Dimension | Question | Checks |
|---|---|---|
| timeliness | recent enough? | `served_crawl_age_days`, `hero_stale_share` |
| completeness | everything there? | `market_coverage`, `product_count_change`, `hero_grid_complete`, `hero_price_coverage`, `macro_grid_complete`, `lfl_match_rate` |
| validity | believable bounds? | `hero_carried_forward`, `lfl_change_bounds` |
| plausibility | behaves like a real delivery? | `price_reversion_share`, `price_decrease_share`, `price_change_share_anomaly`, `hero_large_moves`, `median_price_drift` |
| consistency | do related tables agree? | `cross_market_dispersion`, `global_reconciles_with_markets` |

**Severity.** `block` means a failure stops the release. `warn` never stops a release: the delivery goes
out flagged WARN, and the client or analyst is told. Some signals are *informative, not wrong*. A real price
campaign looks exactly like an anomaly, so `price_change_share_anomaly` can only ever warn. The catalogue
validator refuses a warn-only check that declares fail rules.

**The check that names the incident.** `price_reversion_share` is the share of products whose price
changed since the last delivery *and went back exactly to the price of the delivery before*: A → B → A.
Real prices almost never do that within a week. Serving an old crawl again does it to every product that
had changed. On the replayed 2026-09-15 it is 25–26% in all eight weekly markets; on every real delivery
it is 0%.

### 2.5 One query per check, for the whole calendar

Every check's SQL returns `scope, as_of_date, subject, observed` for **every** delivery, not only the one
being audited. Two reasons:

1. **History for free.** The anomaly rules need the same measure on past deliveries.
2. **Cost.** One query per check per run, whether one delivery is audited or sixteen.

The gate wraps each query with shared CTEs, so checks stay short and never redefine the basics:

| CTE | Content |
|---|---|
| `deliveries` | the delivery calendar: scope, as_of_date, prev_date, prev2_date (an inline `VALUES` table) |
| `catalogue` | the point-in-time catalogue of the dataset being audited |
| `scoped` | the catalogue rows of each delivery, limited to the markets of its scope |

Because `catalogue` is a parameter, the **same checks** run on the marts and on the replay of the old
design (`--dataset legacy_replay`). That is how the gate can be shown to block the incident.

### 2.6 Fixed thresholds and anomaly rules

- **Fixed thresholds** (`warn_above`, `fail_below` …) encode business knowledge: a weekly market served
  from a crawl older than 14 days is unacceptable, and a market losing a fifth of its products is a
  partial crawl.
- **Anomaly rules** (`anomaly: {window, min_history, z, min_value}`) encode "unusual for *this* measure".
  The current value is compared with the mean plus z standard deviations of the last N accepted
  deliveries. There is a floor on the standard deviation, so a perfectly flat history does not turn every
  small move into an alarm, and a minimum value, so tiny anomalies are ignored. This is what observability
  tools do at scale; here it is twenty lines of tested Python.

### 2.7 The baseline is the last accepted delivery

**Plain.** If last week's newspaper was pulped because of a misprint, you check this week's against the
one before it, not against the misprint.

**Term.** Every "vs previous" check compares the delivery with the **last accepted delivery**: one that
was released earlier, or that passed earlier in the same run. A blocked delivery is never the baseline,
and anomaly rules never learn from it.

When the baseline differs from the calendar, the gate measures that delivery again against the adjusted
baseline, and the message says so. Without this rule the first *correct* delivery after an incident is
blocked too: its prices "jump back" to normal. The first version of this gate made exactly that mistake
on the replayed 2026-09-22, and `qa/tests/test_baseline.py` now pins the rule.

### 2.8 Check results are data

Every result row (run, delivery, check, subject, value, rules, status, message) is appended to
`ops.qa_check_results`. The rules are stored as text with each result, because thresholds change over time
and an old verdict must stay explainable. dbt reads the results back into `mart_data_health__deliveries`,
one row per (dataset, scope, delivery):

- counts of pass / warn / fail
- the checks that did not pass
- the verdict, and whether the delivery is published

That mart is a **view** on purpose. The gate writes after dbt has run, and a table would show yesterday's
verdicts. Phase 6 builds the "data health" page on it, and Phase 5b's triage agent starts from it.

### 2.9 What the gate found

**On the marts:**

| Delivery | Verdict | Why | Real event |
|---|---|---|---|
| micro 2026-07-28 | WARN | 2 hero prices carried forward | readings quarantined that week |
| micro 2026-08-18 | WARN | KOR, HKG served an 8-day-old crawl; 25% of hero cells stale; 8 carried forward | partial crawls rejected; USA geo-redirect |
| micro 2026-09-08 | WARN | 25.7% of prices changed vs a usual 0.2% | **the September price campaign**, real |
| micro 2026-09-15 | WARN | JPN crawl 8 days old; 7 hero moves > 10% | JPN missing on 09-14; −11% markdown on the 3XL sneaker |
| micro 2026-09-22 | WARN | 1 hero move > 10% | the same markdown reaching JPN a week later |

**On the replay of the old design:** BLOCK on 2026-08-18. `product_count_change` is −55% in KOR and HKG,
because the half-finished crawls overwrote the catalogue. BLOCK on 2026-09-15: 24 failures, made of
`served_crawl_age_days` (15 days) plus `price_reversion_share` and `price_decrease_share` (~26%) in all
eight markets. The re-exported August crawl had overwritten the September prices. Every other replayed
delivery passes.

So even without the point-in-time redesign, this second line of defence would have kept both incidents
away from the client. That is defence in depth, with evidence.

### 2.10 Why this part is Python and not more dbt tests

dbt tests answer "is this table valid?"; they pass or fail a *build*. The gate answers "may this
*delivery* go out?". That needs several things a test cannot do:

- a delivery calendar
- baselines from history and anomaly statistics
- a decision that combines many checks
- a durable record of every verdict
- a side effect: the release
- a report to read or post

That is orchestration, and Python is the right place for it. The measurements themselves are still SQL,
run inside the warehouse. Python only receives one small number per check and subject, and never the data.

### 2.11 Testing the gate itself

A QA tool that is not tested is one more thing to QA. `qa/tests` (pytest, no warehouse needed) covers:

- the verdict ladder
- every rule type
- the anomaly floor and minimum history
- that warn-only checks never block
- the validity of the shipped catalogue: every dimension covered, every check renders to SQL with no
  placeholder left
- the baseline rule

---

## 3. Step by step

### Step 1 – branch (Terminal)

```bash
cd ~/Documents/LY_data_pipeline_CV_project/balenciaga-pricing-pipeline
git checkout main && git pull
git checkout -b phase-5a/delivery-gate
git add qa/ dbt/ docs/ README.md .gitignore
git commit -m "feat: delivery gate - write-audit-publish with checks-as-code, published layer, data health mart"
git push -u origin phase-5a/delivery-gate
```

### Step 2 – build in Studio

Switch Studio to the branch (switch to `main` first if Studio is on a deleted branch), then:

```bash
dbt build
```

The `on-run-start` hook creates the schema `dbt_rwang_ops` with its two empty tables. The `pub_*` views
are created but **empty**: nothing has been released yet. That is the point.

### Step 3 – set up the gate on your laptop (Terminal, once)

```bash
cd ~/Documents/LY_data_pipeline_CV_project/balenciaga-pricing-pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r qa/requirements.txt
```

Connection details come from Databricks → **SQL Warehouses** → your warehouse → **Connection details**:
*Server hostname* and *HTTP path*. The token is the personal access token from Phase 0 (in your password
manager). Export them in the terminal session; **never write them into a file in the repo**:

```bash
export DATABRICKS_SERVER_HOSTNAME="dbc-xxxxxxxx-xxxx.cloud.databricks.com"
export DATABRICKS_HTTP_PATH="/sql/1.0/warehouses/xxxxxxxxxxxxxxxx"
export DATABRICKS_TOKEN="dapi..."            # paste from the password manager
export QA_SCHEMA_PREFIX="dbt_rwang"          # your dev schemas
```

### Step 4 – run the gate

```bash
python -m pytest qa/tests -q                         # 15 passed - the gate's own tests
python -m qa.gate checks                             # the catalogue
python -m qa.gate audit --dry-run                    # measure + report, write nothing
python -m qa.gate audit --report gate_report.md      # record results, release what passes
python -m qa.gate audit                              # again: "Nothing to audit" (idempotent)
python -m qa.gate audit --dataset legacy_replay      # the old design: 2 BLOCKs, never released
python -m qa.gate status                             # what BI can see
```

The first `audit` takes a few minutes on the 2X-Small warehouse: 17 queries, each over the full calendar.

### Step 5 – look at it (SQL Editor)

```sql
-- every verdict, both designs side by side
SELECT dataset, scope, as_of_date, gate_decision, n_warn, n_fail, checks_not_passing, is_published
FROM workspace.dbt_rwang_marts.mart_data_health__deliveries
ORDER BY scope, as_of_date, dataset;

-- the incident, as the gate saw it
SELECT check_id, subject, observed, status, message
FROM workspace.dbt_rwang_ops.qa_check_results
WHERE dataset = 'legacy_replay' AND as_of_date = '2026-09-15' AND status = 'fail'
ORDER BY check_id, subject;

-- BI's view of the world: released deliveries only
SELECT scope, count(*) FROM workspace.dbt_rwang_published.pub_released_deliveries GROUP BY scope;
```

Then run `dbt build -s path:models/published mart_data_health__deliveries assert_no_blocked_delivery_is_published`
in Studio. Every test passes now that releases exist.

### Step 6 – merge

```bash
gh pr create --fill && gh pr merge --merge --delete-branch
git checkout main && git pull
```

(Switch Studio to `main` **before** merging, so it is not left on a deleted branch.)

**Checkpoint – Phase 5a is done when:**
- [ ] `pytest qa/tests` = 15 passed
- [ ] `audit` on the marts: 16 deliveries, 0 BLOCK, released
- [ ] `audit --dataset legacy_replay`: BLOCK on 2026-08-18 and 2026-09-15 only
- [ ] `pub_micro__hero_prices_weekly` = 832 rows after the release (0 before)
- [ ] PR merged

---

## 4. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Missing environment variable(s)` | the exports were done in another terminal | export again in this one (they last for the session) |
| `TABLE_OR_VIEW_NOT_FOUND ... dbt_rwang_ops` | dbt has not run since this branch | `dbt build` in Studio (the hook creates the tables) |
| `pub_*` views are empty | nothing released yet | `python -m qa.gate audit` |
| `Check <id> failed to run` + SQL | a typo in a check you edited | the SQL is printed; run it in the SQL Editor to debug |
| a delivery you fixed is still blocked | the gate audits only unreleased deliveries, and keeps history | `audit --as-of YYYY-MM-DD` re-audits it; it is released if it now passes |
| `CatalogueError` | checks.yml is invalid (unknown dimension, fail rule on a warn check…) | the message names the check |

---

## 5. Interview lines

> "dbt tests guard the invariants I can anticipate. A release gate guards against what I can't: each
> delivery is audited against its own history before it's published, write-audit-publish style, so BI only
> ever reads data that passed. The checks are code: a YAML catalogue by quality dimension, with SQL that
> runs inside the warehouse. Python only orchestrates: baselines, the decision, the release, the record."

> "I ran the same gate on a replay of the old design. It blocks exactly the two deliveries that went wrong
> in production and nothing else. The sharpest check is price reversion: prices going A to B and back to A
> within a week, which is the fingerprint of an old crawl being served again."

> "WARN and BLOCK are different on purpose. The September price campaign trips the anomaly rule, and it
> should. It's unusual but real, so it goes out flagged, not blocked. A broad price decrease in luxury, or
> a market served a two-week-old crawl, is blocked."

> "One mistake I fixed: comparing each delivery with the previous calendar delivery made the first correct
> week after an incident look wrong, because prices jumped back to normal. The baseline is now the last
> accepted delivery, and there's a unit test for it."

> "Every check result is stored in an append-only Delta table with the rule that produced it, so any
> verdict can be explained later. The data-health page and the triage agent both read from it."

---

## 6. References

- dbt Labs, [Testing is not enough: write-audit-publish](https://www.getdbt.com/blog/testing-is-not-enough-transforming-data-quality-with-write-audit-publish)
- Databricks, [Data profiling (Lakehouse Monitoring): profile and drift metric tables](https://docs.databricks.com/aws/en/lakehouse-monitoring/index)
- Elementary, [anomaly detection for dbt: volume, freshness, column and dimension monitors](https://docs.elementary-data.com/key-features)
- Datafold, [data diff in CI for dbt pull requests](https://docs.datafold.com/deployment_testing)
- Airbnb's Midas certification process: [summary](https://secoda.co/glossary/midas-data-process)
- Bitol / Linux Foundation, [Open Data Contract Standard](https://bitol.io/)
