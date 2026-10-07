# 04 · Phase 2 – Sources, staging and the raw QA lane

**Goal of this phase:** turn 238,707 raw JSON lines into typed, repaired, *flagged* observations –
without losing a single row – and prove it: every planted defect this layer is responsible for is caught,
graded against the generator's answer key.

**Result of the reference run (local Spark, seed 42):** `dbt build` → **37 / 37 PASS**
(6 models, 2 unit tests, 27 data tests, 2 singular tests). Recall 100% on all 34 defect codes owned by
this phase.

---

## 1. The picture first

```
source: crawl.crawl_lines   (bronze, append-only, raw text)                       [Phase 1]
   │
   ▼
base_crawl__lines                    view    1 row per line · id + every JSON field as TEXT
   │
   ▼
stg_crawl__product_observations      table   1 row per line · parse → repair → FLAG (never filter)
   │
   ├──► qa_raw__quarantined_lines    table   rows the pipeline refuses to trust + raw evidence
   ├──► qa_raw__repaired_values      table   audit trail: every automatic repair, raw vs repaired
   ├──► qa_raw__file_profile         table   file-level checks: duplicate / stale / missing / partial
   └──► qa_answer_key__recall        table   grade vs the generator's answer key
   │
   ▼
(Phase 3: intermediate – dedup, choose trusted crawls, categorize)
```

Folder layout (`dbt/`):

```
dbt_project.yml                      layer configs + business rules as vars
packages.yml                         dbt_utils
macros/generate_schema_name.sql      dev vs prod schema names
macros/data_quality.sql              vars -> SQL helpers (currency, dq status, mojibake repair)
models/staging/crawl/_crawl__sources.yml       source + freshness
models/staging/crawl/_crawl__models.yml        docs + data tests
models/staging/crawl/_crawl__unit_tests.yml    unit tests for the price parser
models/staging/crawl/base/base_crawl__lines.sql
models/staging/crawl/stg_crawl__product_observations.sql
models/staging/answer_key/_answer_key__sources.yml   (test-only source, no staging models)
models/quality/raw/qa_raw__*.sql
models/quality/answer_key/qa_answer_key__recall.sql
models/quality/_quality__models.yml
tests/staging/assert_every_line_has_exactly_one_outcome.sql
tests/quality/assert_answer_key_fully_caught.sql
```

---

## 2. Concepts, one at a time

### 2.1 Sources and freshness

**Plain.** A source is the label on the delivery crate: "this came from outside, dbt didn't make it". Freshness
is the best-before date on that label: if no new crate arrived in 8 days, someone should be warned.

**Term.** `sources:` declares tables dbt reads but does not build. `{{ source('crawl', 'crawl_lines') }}`
instead of a hard-coded table name gives lineage (the docs graph starts here) and lets you run
`dbt source freshness`, which compares `max(loaded_at)` with now.

**In practice** (`_crawl__sources.yml`): warn after 8 days, error after 15 – one missed weekly delivery
warns, two fail. *Our data is static, so after a week this will warn: that is the check working.*

### 2.2 `base` → `staging`: why two models for one source

**Plain.** First photograph the parcel and label every item (base). Then clean each item and stick a
coloured tag on anything suspicious (staging). Nothing goes in the bin at either step.

**Term.** `base_` models are an optional sub-step of staging (dbt's own convention: `staging/<source>/base/`).
`base_crawl__lines` only extracts; `stg_crawl__product_observations` parses, repairs and flags.

**Deeper – "staging is 1:1 with the source, and never filters".** Both models have exactly the source's row
count (tested with `dbt_utils.equal_rowcount`). A bad row is *flagged*, not dropped, because a row dropped in
staging is invisible forever – nobody can count it, nobody can audit it. Decisions to exclude happen later,
where they are counted and tested.

### 2.3 Schemas per layer

`+schema: staging` in `dbt_project.yml` + the `generate_schema_name` macro give:

| Environment | staging models land in | quality models land in |
|---|---|---|
| development (you, in Studio) | `workspace.dbt_rwang_staging` | `workspace.dbt_rwang_quality` |
| production (Phase 6 job, target `prod`) | `workspace.staging` | `workspace.quality` |

### 2.4 Materializations chosen

| Model | Materialization | Why |
|---|---|---|
| `base_crawl__lines` | view (layer default) | cheap extraction, always reflects bronze |
| `stg_crawl__product_observations` | **table** (override) | regex-parses 240k JSON lines and is read by 5 models – as a view that work would repeat on every read. The reason is written in the model's header: an override always needs one |
| `qa_*` | table (layer default) | people query them directly; they must be fast and stable |

### 2.5 Business rules live in `vars`, not in SQL

`dbt_project.yml → vars:` holds the market → currency map, the ISO minor units, the crawl scopes, the
thresholds, and **`dq_reasons`**: every rule the staging layer can fire and its handling. Macros turn these
into SQL (`{{ market_currency('market') }}` becomes a `CASE`). A reviewer changes one line in a pull request;
nobody hunts through a 300-line model.

### 2.6 The price parser – deciding what "." and "," mean

**Plain.** `1.250` is one thousand two hundred and fifty in Paris and one point two five in New York. The
string alone does not tell you which. We add one piece of outside knowledge – how many decimals the currency
has – and refuse to guess when even that is not enough.

| Text delivered | Rule applied | Result | Flag |
|---|---|---|---|
| `2490` | plain digits | 2490 | – |
| `1,250` | only commas, groups of 3 → thousands | 1250 | `price_us_thousands_separator` |
| `1.250,00` / `1 250,00` | both / comma + 2 digits → last mark is the decimal | 1250 | `price_eu_decimal_format` |
| `$1,250` / `1 250 €` | strip symbol, then as above | 1250 | `price_currency_symbol` |
| `１２５０`, `١٢٥٠` | translate to ASCII digits first | 1250 | `price_non_ascii_digits` |
| `1250.00` | one dot + 2 digits → decimal | 1250 | `price_trailing_decimals` |
| `2.490` | one dot + 3 digits, currency has 0 or 2 decimals → thousands | 2490 | `price_dot_thousands_ambiguous` |
| `1.250` in KWD | currency has 3 decimals → genuinely ambiguous | **null** | `price_ambiguous_separator` → quarantine |
| `Sur demande`, `From 1,250`, `1,200 - 1,500` | not a single price | **null** | quarantine |
| `0`, `99999999` | placeholder | kept, but | `price_placeholder` → quarantine |

`price.price` (the crawler's own number) is **never used**: it is in minor units for some markets only and
always labelled EUR (systemic quirk S1).

These cases are the two **unit tests** in `_crawl__unit_tests.yml`.

### 2.7 `dq_issues` and `dq_status`

Every rule that fires is appended to the row's `dq_issues` array. `dq_status` is the most severe handling
among them:

```
pass  <  fixed (repaired, raw kept)  <  warn (kept, surfaced)  <  quarantine (excluded from marts)
```

Reference run: **223,680 pass · 11,561 fixed · 2,046 warn · 1,420 quarantine.**

### 2.8 The QA lane

| Model | Answers the question |
|---|---|
| `qa_raw__quarantined_lines` | Which lines do we refuse, why, and what exactly did the crawler send? |
| `qa_raw__repaired_values` | Which values did we change automatically, from what, to what? |
| `qa_raw__file_profile` | Which *deliveries* are suspicious – copies, stale re-exports, incomplete? |
| `qa_answer_key__recall` | Of everything the generator planted, how much did we catch, handled the right way? |

**The content fingerprint** (in `qa_raw__file_profile`) = sum of a 64-bit hash of every line. Two files with
the same lines have the same fingerprint regardless of file name or line order. Result:

| File | Verdict | Why |
|---|---|---|
| `…08-10… (1).ndjson.gz` | **block** | same content as `…08-10….ndjson.gz` (F01) |
| `…09-15….ndjson.gz` | **block** | newest crawl timestamp inside is 15 days older than the file date – the 08-31 crawl re-delivered (F02, *the incident*) |
| `…08-17….ndjson.gz` | warn | HKG and KOR below 70% of their usual size (F03) |
| `…09-14….ndjson.gz` | warn | JPN missing from a weekly crawl (F04) |

### 2.9 Three kinds of tests

| Kind | Where | Checks | Example |
|---|---|---|---|
| **data test (generic)** | `_*__models.yml` | the built data, column by column | `unique`, `not_null`, `accepted_values`, `equal_rowcount` |
| **data test (singular)** | `tests/*.sql` | any SQL assertion – returns the failing rows | row conservation, answer-key recall |
| **unit test** | `_crawl__unit_tests.yml` | the *logic*, on hand-written inputs, before real data | the price parsing table above |

**Row conservation** (`assert_every_line_has_exactly_one_outcome`): for every file,
`delivered = usable + quarantined`. Nothing disappears silently.

---

## 3. Step by step

### Step 1 – bring the code onto a branch (Terminal)

The new files are already in your local repo. Remove Studio's example models, then commit on a branch:

```bash
cd ~/Documents/LY_data_pipeline_CV_project/balenciaga-pricing-pipeline
git checkout main && git pull
git checkout -b phase-2/staging-raw-qa
git rm -r dbt/models/example                     # the hello-world models from Phase 0
git add dbt/ docs/ generator/
git status                                       # review what will be committed
git commit -m "feat(dbt): sources, staging, raw QA lane, answer-key grading"
git push -u origin phase-2/staging-raw-qa
```

### Step 2 – run it in Studio

1. dbt platform → **Studio IDE** → branch selector (top left) → **`phase-2/staging-raw-qa`**.
2. Command bar:

```bash
dbt deps                       # installs dbt_utils (packages.yml)
dbt build                      # models + tests + unit tests, in dependency order
```

Expected: **37 PASS**. The staging table takes ~1–3 minutes on the 2X-Small warehouse.

3. Optional: `dbt source freshness` – passes now, warns after 8 days without a new load.
4. Clean up Phase 0 leftovers in Databricks SQL Editor (optional):
   `DROP VIEW IF EXISTS workspace.dbt_rwang.my_second_dbt_model; DROP TABLE IF EXISTS workspace.dbt_rwang.my_first_dbt_model;`

### Step 3 – look at the results (Databricks SQL Editor)

```sql
-- the grade sheet
SELECT defect_code, caught_by_rule, expected_phase, n_planted, n_detected, recall, handled_as_expected
FROM workspace.dbt_rwang_quality.qa_answer_key__recall ORDER BY defect_code;

-- the suspicious deliveries
SELECT delivered_file_name, crawl_scope, file_status, duplicate_of_file, is_stale_content,
       missing_markets, partial_markets
FROM workspace.dbt_rwang_quality.qa_raw__file_profile ORDER BY delivered_file_name;

-- one example of every repair
SELECT repair_rule, raw_value, repaired_value
FROM (SELECT *, row_number() OVER (PARTITION BY repair_rule ORDER BY crawl_line_id) AS rn
      FROM workspace.dbt_rwang_quality.qa_raw__repaired_values)
WHERE rn = 1 ORDER BY repair_rule;
```

`A09_minor_units_leak` and `G01_unit_scale_error` show recall 0 with `expected_phase = 3`: a price ×100 or
×10 is a perfectly valid-looking number on its own; catching it needs the product's price in *other* crawls.
That is Phase 3.

### Step 4 – merge

```bash
gh pr create --fill
gh pr merge --merge --delete-branch
git checkout main && git pull
```

**Checkpoint – Phase 2 is done when:**
- [ ] `dbt build` = 37 PASS in Studio
- [ ] `qa_answer_key__recall`: recall = 1.0 for every `expected_phase = 2` code
- [ ] `qa_raw__file_profile` blocks the `(1)` copy and the 09-15 stale file
- [ ] PR merged

---

## 4. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `dbt_utils` not found | `dbt deps` not run on this branch | run `dbt deps` |
| `Table or view not found: raw.crawl_lines` | catalog not `workspace` in the connection | Project settings → connection → Catalog |
| unit test fails with a type error | Studio's dbt version differs from the reference run | send me the full error |
| `url_decode` / `try_element_at` unknown | very old runtime (should not happen on serverless) | send me the error |
| build is slow | first serverless start + 240k regex parses | normal: ~1-3 min for the staging table |

---

## 5. Interview lines

> "Staging never filters. Every rule that fires is recorded on the row, and the row's status is the most severe
> handling among them. Quarantine is a separate, auditable model – and a row-conservation test proves that
> every delivered line ends up either usable or quarantined."

> "The price parser resolves '1.250' with the currency's ISO minor units, and where that still isn't enough
> it refuses to guess. The parsing rules are covered by dbt unit tests, so the logic is tested independently of
> the data."

> "Because the data is synthetic I can measure recall, which you normally can't: the generator writes an
> answer key, and a dbt model grades the QA layer against it. This phase catches 100% of the defects it owns;
> the two it can't – unit-scale errors – need price history and are graded in the next layer."

> "The stale re-import passes every row-level check – it's valid data, just old. Only a file-level profile
> sees it: its newest crawl timestamp is 15 days older than its file date. That is the exact delivery that
> broke our weekly and monthly reports in production."
