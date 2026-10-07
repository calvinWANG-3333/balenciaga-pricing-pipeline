# 00 · Roadmap – the whole picture before any detail

> How to read these docs: every concept is introduced in four layers –
> **Plain** (an everyday analogy) → **Term** (the professional word) → **Deeper** (why it is designed that way)
> → **In practice** (what you actually type or click). Each chapter ends with interview lines.

---

## 1. The problem we are solving

**Plain.** Imagine one shared whiteboard in an office. Two colleagues use it for two different reports. Every
time one of them needs fresh numbers, they wipe the whole board and copy the newest numbers onto it. If the
other colleague is halfway through a report based on *last week's* numbers, their report silently changes
under their feet – or they wipe the board back to last week's numbers and break the first colleague's work.

**Term.** A *shared mutable staging table* consumed by two *downstream deliveries* with *different cadences*.
Each import is a *destructive overwrite* at source level, so the table's content depends on *who imported
last*, not on any business rule. The result is *non-deterministic*: running the same delivery twice can give
two different answers.

**Deeper.** At the company this was the "catalogue" index: crawl feed → validation → catalogue (shared) →
Micro prod (weekly, client hero SKUs via pointers) and Macro prod (monthly, category min / max / mean). Both
products read the same catalogue rows for a source such as `Balenciaga_USA`, and every import of that source
replaced all of its rows.

**The fix in one sentence.** Never overwrite: keep every crawl forever (append-only), make every downstream
table a *pure function* of that history plus a date, and let each delivery choose its own date.

---

## 2. Target architecture

```
          ┌──────────────────────────── Databricks (Unity Catalog: workspace.*) ──────────────────────────┐
 generator│  Volume                bronze               dbt: silver                  dbt: gold           │
  (Python)│  /raw/landing/   →   raw.crawl_files    →   staging   →  intermediate  →  marts  ──┬─► agent  │
  NDJSON ─┼─► ALT_*.ndjson       (append-only,          1:1 with     joins, dedup,   micro_*   ├─► BI     │
          │                       one row per line,     source,      categorize,     macro_*   └─► QA     │
          │                       + file metadata)      clean only   as-of select    qa_*                 │
          └──────────────────────────────────────────────────────────────────────────────────────────────┘
                     ▲                                          ▲
                     │ COPY INTO (idempotent: a file is         │ dbt platform job: dbt source freshness → dbt build
                     │ loaded once, ever)                       │ GitHub Actions: CI on pull requests, site deploy
```

**Medallion vocabulary** (Databricks' words for the same idea dbt calls layers):

| Medallion | dbt layer | What lives there | Materialization |
|---|---|---|---|
| bronze | `source` | raw lines exactly as delivered + file metadata | Delta table loaded by `COPY INTO` (not dbt) |
| silver | `staging` | one model per source table: rename, cast, parse, flag – **no joins** | `view` |
| silver | `intermediate` | joins, dedup, categorization, as-of selection | `view` / `ephemeral` (heavy ones `table`) |
| gold | `marts` | business entities and metrics: `dim_`, `fct_`, `mart_` | `table`; price fact `incremental` + `merge` |
| – | `quality` | `qa_*` models that surface every quarantined row | `table` |
| – | `snapshots` | SCD2 history of product attributes | `snapshot` |

---

## 3. Phases

| # | Phase | You will learn | Done when |
|---|---|---|---|
| 0 | **Environment** – GitHub, Databricks Free Edition, dbt platform, connect them | what a catalog, schema, warehouse, token, branch are | `dbt run` in Studio creates a view you can see in Databricks |
| 1 | **Synthetic data + bronze load** – generate, upload to a Volume, `COPY INTO` | EL, idempotent loading, file metadata, why raw stays text | 15 files loaded once; re-running the load adds 0 rows |
| 2 | **Sources + staging + raw QA** | `_sources.yml`, freshness, naming, parsing, quarantine | every planted A–E defect is fixed or quarantined |
| 3 | **Intermediate + snapshots** | dedup, seeds, categorization rules, as-of selection, SCD2 | `int_catalogue__micro_asof` and `__macro_asof` from one history |
| 4 | **Marts + tests** | grain, incremental merge, contracts, unit tests, the killer test | same SKU + same as-of date ⇒ same price in Micro and Macro |
| 5 | **QA tool port + metrics agent** | turning a Python QA script into tested models; governed LLM querying | the old "evolution tab" is a dbt model; agent answers only governed metrics |
| 6 | **BI + CI/CD + portfolio site** | Evidence.dev, GitHub Actions, GitHub Pages, writing the story | public URL with architecture, defects, tests, dashboards |

---

## 4. Conventions decided up-front

These are fixed now so every later chapter follows them.

**Naming**

| Thing | Pattern | Example |
|---|---|---|
| source YAML | `_<source>__sources.yml` | `_crawl__sources.yml` |
| model YAML | `_<folder>__models.yml` | `_crawl__models.yml` |
| staging model | `stg_<source>__<entity>` | `stg_crawl__products` |
| intermediate model | `int_<entity>__<verb>` | `int_products__deduplicated` |
| marts | `dim_<entity>`, `fct_<event>`, `mart_<audience>__<topic>` | `fct_price_observations`, `mart_macro__category_monthly` |
| QA models | `qa_<layer>__<problem>` | `qa_raw__unparseable_prices` |
| seeds | noun, plural | `ly_category_rules`, `hero_products` |

**Rules**

1. Staging is 1:1 with a source table. It renames, casts, parses and flags. It never joins.
2. Joins, merges and deduplication only happen from `intermediate` onwards.
3. Every model has a declared **grain** (what one row means) in its YAML description, and a test that proves it.
4. Raw is never modified. A repaired value always sits next to the raw value it came from.
5. Nothing is silently dropped: every raw row ends up in staging *or* in a `qa_` model (row-conservation test).
6. Secrets only through environment variables / dbt platform credentials – never in the repo.
7. Every source has `freshness` with a `loaded_at_field`.
