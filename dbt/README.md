# dbt project – `balenciaga_pricing`

Runs on Databricks through the dbt platform (Studio IDE). Build log and design explanations: [`../docs/`](../docs/).

```
models/
  staging/crawl/       base_crawl__lines -> stg_crawl__product_observations   (parse, repair, flag - never filter)
  staging/answer_key/  test-only source: the synthetic generator's ground truth
  intermediate/        deliveries (trust) -> observations (one fate per line) -> products (categorization)
                       -> prices (SCD2 history, point-in-time catalogue) ; legacy/ (replay of the old design)
  marts/core/          dim_product, dim_market, fct_price_observations (incremental MERGE), fct_price_changes,
                       fct_catalogue_as_of                       - star schema, enforced contracts
  marts/micro/         mart_micro__hero_prices_weekly            - weekly hero prices (complete grid, statuses)
  marts/macro/         mart_macro__category_monthly(_global)     - monthly levels + like-for-like change
  marts/_exposures.yml dashboards and the metrics agent that read the marts
  quality/raw/         qa_raw__quarantined_lines, qa_raw__repaired_values, qa_raw__file_profile
  quality/intermediate qa_int__price_scale_outliers
  quality/incident/    qa_incident__legacy_vs_point_in_time  (the production incident, replayed and measured)
  quality/answer_key/  qa_answer_key__recall  (grades the QA layer against the answer key)
seeds/                 ly_category_tree, ly_category_rules (rule engine), micro_pointers (Micro watchlist), markets
tests/                 singular tests: row conservation, answer-key recall, point-in-time guarantees, SCD2 integrity,
                       marts = projections of the point-in-time catalogue
tests/generic/         serves_latest_eligible_crawl - the killer test, run on the new AND the legacy design
macros/                generate_schema_name, data-quality helpers driven by vars
```

```bash
dbt deps
dbt build                 # models + data tests + unit tests
dbt source freshness      # warns 8 days after the last bronze load
```
