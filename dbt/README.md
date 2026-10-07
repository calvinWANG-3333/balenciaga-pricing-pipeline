# dbt project – `balenciaga_pricing`

Runs on Databricks through the dbt platform (Studio IDE). Build log and design explanations: [`../docs/`](../docs/).

```
models/
  staging/crawl/       base_crawl__lines -> stg_crawl__product_observations   (parse, repair, flag - never filter)
  staging/answer_key/  test-only source: the synthetic generator's ground truth
  quality/raw/         qa_raw__quarantined_lines, qa_raw__repaired_values, qa_raw__file_profile
  quality/answer_key/  qa_answer_key__recall  (grades the QA layer against the answer key)
tests/                 singular tests: row conservation, answer-key recall
macros/                generate_schema_name, data-quality helpers driven by vars
```

```bash
dbt deps
dbt build                 # models + data tests + unit tests
dbt source freshness      # warns 8 days after the last bronze load
```
