# 08 · Phase 5b – Semantic layer + metrics agent + triage agent

**Goal of this phase:** let people ask the data questions in plain English, without the answers drifting
from the official definitions and without anyone being able to make the agent invent a number. And let the
delivery gate's verdicts explain themselves.

Three pieces:

1. **A semantic layer in dbt.** Every business number is defined exactly once (MetricFlow spec).
2. **A metrics Q&A agent.** It reads those definitions from dbt and answers only governed metrics, on
   released data only. It refuses everything else, with a reason.
3. **A triage agent.** For every delivery the gate did not PASS, it drills into the evidence and writes a
   review note: likely cause, action, and a draft client note.

**Result of the reference run (local Spark, seed 42):**

| | |
|---|---|
| Governed metrics | 10 (+2 hidden building blocks) on 3 semantic models |
| Evaluation set | **25 / 25** with the rule translator, including 4 that must be refused; the same exam grades the Claude translator |
| Unit tests | 55 for the agent (incl. 12 for the Claude path, replaying real LLM forms) + 15 for the gate = **70 passed**, offline (no warehouse, no API key) |
| Triage | the 5 WARN deliveries explained with their upstream cause; on the old design's replay, the 2026-09-15 BLOCK traced to the re-exported file `ALT_2026-09-15_…` (August content under a September name) |

---

## 1. The picture first

```
 dbt/models/semantic/*.yml ──dbt parse──► target/semantic_manifest.json      ONE definition of every metric
                                                     │
          question ──► TRANSLATE ──► Intent (a form) ┤
          (English)    rules (offline)     metric      │
                       or Claude (tool     filters     ▼
                       call, optional)     group by   GUARDRAILS ── no ──► refusal + reason + suggestion
                                           period      │ yes                (deterministic)
                                                       ▼
                                                    COMPILE ──► SQL template on ONE published view
                                                       │
                                                       ▼
                                                    warehouse (published = released deliveries only)
                                                       │
                                                       ▼
                                                    NARRATE ──► answer + provenance + SQL shown
                                                    template (or Claude: rephrase, never compute)

 gate results (ops) ──► TRIAGE ──► drill-down queries ──► review note: cause · action · client note
```

New in the repository:

```
dbt/models/semantic/        metricflow_time_spine, _semantic_models.yml, _metrics.yml
dbt/models/marts/core/      fct_price_changes now carries macro_category (for the semantic layer)
agent/
  semantic.py               reads the semantic manifest -> the governed catalogue
  vocabulary.py             what values exist (markets, heroes, categories, periods) + aliases
  intent.py                 the form a translator fills (and a Refusal)
  translate.py              RuleTranslator (offline) / ClaudeTranslator (tool call, optional)
  guardrails.py             may this be answered?
  compiler.py               Intent -> SQL (templates only)
  narrate.py                rows -> answer (template; Claude can rephrase)
  ask.py                    the pipeline
  triage.py                 explains the gate's WARN / BLOCK verdicts
  cli.py  app.py            terminal and Streamlit front-ends
  evals/questions.yml       the evaluation set (25 questions)
  tests/                    pytest, offline (a committed copy of the manifest + a fixed vocabulary)
```

---

## 2. Concepts, one at a time

### 2.1 A semantic layer: one definition per number

**Plain.** If three dashboards each write their own SQL for "bag price increase", sooner or later they
disagree. One divides by markets, another by products, a third forgets to exclude new products. A
semantic layer is the **dictionary** of the business's numbers. "Like-for-like change" is written down
once: which table, which column, which aggregation, what it can be cut by. Everyone, people and agents,
looks it up instead of rewriting it.

**Term.** dbt **semantic models** and **metrics** (the MetricFlow specification). A semantic model sits on
one table and declares:

- **entities** – keys
- **dimensions** – what you can group or filter by; one of them is the time dimension
- **measures** – aggregations: `sum`, `average`, `count` …

Metrics are built on measures:

- `simple`: one measure
- `ratio`: one metric divided by another

`dbt parse` validates all of it and compiles it into `target/semantic_manifest.json`.

| Semantic model | Published view | Time | Metrics |
|---|---|---|---|
| `hero_prices` | `pub_micro__hero_prices_weekly` | `delivery_date` (day) | `hero_price`, `hero_price_change`, `hero_price_increases` |
| `category_monthly` | `pub_macro__category_monthly` | `report_month` (month) | `category_lfl_change`, `category_lfl_change_product_weighted` (ratio), `category_product_count`, `category_median_price`, `category_share_increased` |
| `price_changes` | `pub_fct_price_changes` | `changed_on_crawl_date` (day) | `price_change_count`, `average_price_change` |

Two details worth knowing:

- **The semantic models sit on the `published` views**, so anything defined there only ever sees released
  deliveries. The governance of the delivery gate carries through to every question.
- **The ratio metric is product-weighted LFL**: Σ(market LFL × LFL products) ÷ Σ LFL products. Its two parts
  are declared as hidden metrics (a ratio divides metrics, not measures). The market-weighted headline is
  simply the `average` of the market values. The mean-of-means decision from Phase 4 is written once, here.

**Why not dbt's own Semantic Layer API?** Querying metrics through dbt's hosted service needs a paid dbt
plan. So the definitions use dbt's standard format, and a small compiler of ours turns them into SQL. The
day the paid API is available, the definitions do not change: only the executor does.

### 2.2 The agent's catalogue comes from dbt, not from the agent

**Plain.** The agent does not keep its own list of metrics. It reads the dictionary dbt compiled. Change a
definition in dbt, run `dbt parse`, and the agent follows. There is nothing to keep in sync.

**Term.** `agent/semantic.py` loads `semantic_manifest.json`: metrics, measures, dimensions, the published
view each semantic model sits on, and an `agent` block from each metric's `config.meta`:

| meta key | What it tells the agent | Example |
|---|---|---|
| `synonyms` | words a question may use | `like-for-like`, `lfl`, `price increase`… |
| `unit` | how to format | `percent` → +5.24%, `currency` → 3,310 USD |
| `requires` | dimensions a question must fix | `market` for every price in local currency |
| `default_group_by` | how to break down when the question doesn't say | `macro_category` for LFL |
| `default_time` | `latest` or `all` when no period is named | |
| `point_in_time` | a level, not a flow: over a period, take the latest value | prices, listed products |
| `hidden` | building block, never answered alone | the two halves of the ratio |

A test (`agent/tests/test_semantic.py`) fails if the committed copy of the manifest drifts from the dbt
YAML. It also fails if a currency metric ever stops requiring a market.

### 2.3 The LLM fills a form, it never writes SQL

**Plain.** At a bank counter you fill in a withdrawal slip, and the clerk checks it against your account.
You don't get to walk into the vault. Here the translator fills a slip (the **Intent**):

- which metric
- which filters
- grouped by what
- which period

A clerk (the **guardrails**) checks it. Only then does a fixed procedure (the **compiler**) fetch the numbers.

**Term.** Text-to-SQL by an LLM is flexible but ungovernable. It can invent a column, average currencies,
or read a table nobody released. Here the LLM's only possible output is a JSON object that has to match a
schema: a forced tool call whose `metric` and `group_by` fields are enums built from the manifest. Even a
perfectly wrong LLM can only produce an Intent that the guardrails then reject.

Two translators fill the same form:

- **RuleTranslator** (default, offline): synonym matching from the manifest. Values are recognised from the
  data itself (`Japan` → JPN, `the Le City` → *Le City Bag Medium (black)*, `sneakers` → Shoes), longest
  match first, so "Le City bag" is a hero and not the Bags category. Periods are parsed relative to the
  published data (`September`, `Q3`, `last month`, `latest`).
- **ClaudeTranslator** (when `ANTHROPIC_API_KEY` is set): better at messy phrasing, same form, same
  guardrails. The tool schema only offers categorical dimensions, with their real values as enums: no
  date column can be grouped or filtered.

**Reader vs policy.** A translator only *reads*: which metric, which values, which period the question
names. What the agent *decides* (latest delivery by default, a price is a point-in-time value, a rate is
shown per period, a currency metric is shown per market, a value pinned by a filter is not also a group)
lives in one function, `apply_policy`, that both translators go through. The Claude path also has a
cleaning step first: `Japan` → `JPN`, `HERO-02` → its product, a date written as a filter → a period,
a date column in `group_by` → ignored.

Why this split exists. The first live run with Claude scored **14/25** while the rules scored 25/25.
Claude had read every question correctly. It had filled the form *literally*: `report_month = 2026-09-01`
as a filter (refused by the value guardrail), `delivery_date` in `group_by`, no period when none was
named, the whole of August for a price. The fix was not a better prompt. The business rules moved out of
the rule translator into the shared policy, and the LLM's raw forms became replay tests
(`tests/test_claude_translator.py`, a stub client, no API key needed).

### 2.4 Guardrails: when the right answer is "no"

| Guardrail | Example it stops | Refusal |
|---|---|---|
| governed metrics only | "What is Balenciaga's revenue in France?" | lists what can be asked |
| no invented values | "LFL change for shoes in **Germany**" | Germany is not monitored; lists the 16 markets |
| dimensions of the metric's own model only | hero price "by category" | lists the available dimensions |
| **never average currencies** | median price of bags across markets (an LLM intent) | "ask for one market, or per market" |
| published data only | "price changes in December 2026" | gives the available period |

The currency rule deserves a sentence in an interview: averaging EUR 2,280 with JPY 430,100 gives a number
that looks precise and means nothing. The rule is declared in dbt (`requires: [market]`) and enforced in
code.

### 2.5 Small rules that make answers correct, not just runnable

- **Point-in-time vs flow.** "Price of the Rodeo bag in August" means the price at the last August
  delivery (2026-08-25), not the average of four weeks. "Price increases in September" is a count over the
  month. The `point_in_time` flag decides, and the answer states the assumption.
- **Rates are per period.** "LFL change in Q3" is shown month by month, not as an average of monthly
  changes, which would be a meaningless number.
- **Several values → compare.** "Bags in France and Japan" is grouped by market automatically.
- **Every answer carries its provenance:** the metric, the semantic model, the published view and the SQL.

### 2.6 Evaluate the agent like a model

**Plain.** You wouldn't ship a pricing model without a test set. Same for an agent.

**Term.** `agent/evals/questions.yml` holds 25 questions with the expected metric, filters, grouping,
period, or `refuse: true`. `python -m agent eval` runs them against the live vocabulary, and pytest runs
them offline against a fixed one. A change that improves one question and breaks another shows up at once.
When the Claude translator is switched on, the same evaluation set measures it, so the LLM is graded on
exactly the same exam as the rules (`--translator claude`; the default `auto` picks Claude whenever
`ANTHROPIC_API_KEY` is exported).

### 2.7 The triage agent: from "what failed" to "why, and what now"

**Plain.** The gate is the smoke detector; triage is the person who walks into the room and finds the
toaster.

**Term.** For each delivery whose latest gate verdict is not PASS, `agent/triage.py` reads the failing
checks and runs targeted drill-down queries:

| Check | Drill-down | What it concludes (reference run) |
|---|---|---|
| `served_crawl_age_days` | which crawl was served; file profile of the newer files | 09-15 JPN: the 09-14 file has no JPN → fell back to 09-07. Old design: served the **stale re-export** `ALT_2026-09-15_…` (content 08-31) |
| `hero_carried_forward` | the quarantined reading behind each carried price | 08-18 USA: `currency_market_mismatch` (raw 2,500 **EUR** on the US site) |
| `price_change_share_anomaly` | share and size of changes per category | 09-08: Bags and SLG +6.2% in all 8 markets → **brand-wide price campaign, real** |
| `hero_large_moves` | per product: how many markets, how consistent | 09-15: 3XL Sneaker −11.2% in 7 markets, almost identical → coordinated markdown, real |
| `price_reversion_share` / `price_decrease_share` | crawl served now vs the last two deliveries | old design 09-15: crawl served is *older* than last week's in 8 markets → an old crawl was served again |

Then the action:

- **BLOCK** → hold, fix the cause upstream, re-audit (or a forced release with a reason).
- **WARN** → release, with a **draft client note** assembled from the findings, for example: *"The brand
  raised prices on Bags, Small Leather Goods (about +6.2%)."*

It is deterministic. With an API key, Claude can add a three-sentence executive summary. It reads the
evidenced findings and never decides the action.

A finding that cannot be explained by evidence points to the next tool. For an isolated price move, the
note says "verify on the brand website", which is exactly the input of the Browser-Use verification agent
built during the internship.

---

## 3. Step by step

### Step 1 – branch (Terminal)

```bash
cd ~/Documents/LY_data_pipeline_CV_project/balenciaga-pricing-pipeline
git checkout main && git pull
git checkout -b phase-5b/semantic-layer-agent
```

### Step 2 – build in Studio

Switch Studio to the branch, then `dbt build`. New: `dbt_rwang_semantic.metricflow_time_spine`, and
`fct_price_changes` gains `macro_category` (its contract changes, so the model is rebuilt).

### Step 3 – dbt Core on your laptop, to compile the semantic manifest (once)

The agent needs `dbt/target/semantic_manifest.json`. Studio writes it in its own environment, so you
produce it locally with **dbt Core**, the open-source command-line dbt. `dbt parse` only reads the
project; it does not run anything on the warehouse.

```bash
source .venv/bin/activate
pip install -r agent/requirements.txt          # dbt-core + dbt-databricks + streamlit (+ anthropic)
mkdir -p ~/.dbt && nano ~/.dbt/profiles.yml     # paste the block below, save
```

```yaml
default:                      # = `profile: default` in dbt_project.yml
  target: dev
  outputs:
    dev:
      type: databricks
      catalog: workspace
      schema: dbt_rwang
      host: "{{ env_var('DATABRICKS_SERVER_HOSTNAME') }}"
      http_path: "{{ env_var('DATABRICKS_HTTP_PATH') }}"
      token: "{{ env_var('DATABRICKS_TOKEN') }}"
      threads: 4
```

`~/.dbt/` lives outside the repo, and the file only holds `env_var(...)` references, so no secret is
written anywhere. Then:

```bash
cd dbt
dbt deps        # installs dbt_utils locally
dbt parse       # writes target/semantic_manifest.json
cd ..
```

### Step 4 – run the agent

```bash
python -m pytest agent/tests qa/tests -q            # 70 passed
python -m agent metrics                             # the governed catalogue
python -m agent ask "How much is the Le City bag in the USA?"
python -m agent ask "Which market had the highest bag price increase last month?"
python -m agent ask "What is the median price of bags?"
python -m agent ask "LFL change for shoes in Germany"     # must refuse
python -m agent eval --translator rules             # 25/25, offline translator, free
python -m agent eval --translator claude            # same exam for the LLM (needs ANTHROPIC_API_KEY, a few cents)
python -m agent triage --out triage_marts.md
python -m agent triage --dataset legacy_replay --out triage_legacy.md
streamlit run agent/app.py                          # the UI, in your browser
```

### Step 5 – commit and merge

```bash
git add agent/ dbt/ docs/ README.md
git commit -m "feat: semantic layer (MetricFlow spec) + governed metrics agent + delivery triage agent"
git push -u origin phase-5b/semantic-layer-agent
# Studio back to main first, then:
gh pr create --fill && gh pr merge --merge --delete-branch
```

**Checkpoint – Phase 5b is done when:**
- [ ] `dbt build` passes in Studio (reference run: 165 PASS; new time spine, `fct_price_changes` with `macro_category`)
- [ ] `dbt parse` writes `dbt/target/semantic_manifest.json` locally
- [ ] `pytest agent/tests qa/tests` = 70 passed; `python -m agent eval --translator rules` = 25/25
- [ ] triage on `legacy_replay` names the stale re-export as the cause of 2026-09-15
- [ ] PR merged

---

## 4. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Semantic manifest not found` | `dbt parse` not run, or run elsewhere | Step 3 (run it inside `dbt/`) |
| `dbt parse`: `Could not find profile named 'default'` | `~/.dbt/profiles.yml` missing or a different top-level name | the top-level key must be `default` |
| `dbt parse`: `Env var required but not provided` | the `DATABRICKS_*` exports were done in another terminal | export again |
| `dbt deps` fails with a certificate error | the network re-signs HTTPS (see doc 07) | other network, or ask me: dbt does not use the macOS keychain |
| `test_fixture_matches_dbt_yaml` fails | you changed a metric in dbt | `dbt parse`, then copy `dbt/target/semantic_manifest.json` to `agent/tests/fixtures/` |
| the agent picks the wrong metric | no synonym matches the wording | add the phrase to the metric's `synonyms` in `_metrics.yml`, add the question to `evals/questions.yml`, re-parse |
| `eval` prints `Translator: claude` and a lower score | `ANTHROPIC_API_KEY` is exported, so `auto` chose Claude | compare with `--translator rules`; each FAIL line shows the field Claude filled differently. A pattern (a date as a filter, a missing period) belongs in `apply_policy` or the Claude cleaning step, with a replay case in `test_claude_translator.py` |
| answers are empty | nothing released yet | `python -m qa.gate audit` (the agent only reads released deliveries) |

---

## 5. Interview lines

> "Every metric is defined once, in dbt's semantic layer: measures, dimensions, ratio metrics. The agent
> doesn't have its own definitions. It reads the compiled semantic manifest, so changing a metric in dbt
> changes what the agent answers, with no drift."

> "The LLM never writes SQL. It fills a structured form through a tool call whose fields are enums from
> the manifest. Deterministic guardrails check the form, and a template compiler writes the SQL. The worst
> a wrong LLM can do is produce a form that gets refused."

> "Some refusals are the feature. Prices are in local currency, so the median price of bags across markets
> would average euros with yen. The metric declares that it requires a market, and the agent refuses and
> suggests asking per market."

> "I evaluate the agent like a model: 25 questions with expected metric, filters, period, or an expected
> refusal. It runs offline in pytest and live against the warehouse. The rule-based translator passes
> 25/25, and if I switch on Claude it's graded on the same exam."

> "The first time I plugged Claude in, it scored 14 out of 25 where the rules scored 25. It understood
> every question; it just filled the form literally, like putting a date in a filter. So I separated
> reading from deciding: the LLM only reads, and the business rules live in one deterministic policy that
> both translators go through. Its raw outputs became replay tests that run without an API key."

> "The gate tells me what failed; the triage agent tells me why. It drills into the evidence. On the
> replayed incident it pointed at the exact re-exported file that carried August prices under a September
> name, and for warnings it drafts the client note."

> "It only reads the published layer, so a question can never surface a delivery the gate hasn't released."
