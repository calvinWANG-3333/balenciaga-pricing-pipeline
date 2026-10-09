{#
  drop_ci_schemas
  ---------------
  Plain: every pull request builds its changed models into its own throw-away shelves (ci_pr_12_staging,
  ci_pr_12_marts ...) so it never touches production or another PR. When the PR is closed, this macro
  removes those shelves.

  Run by .github/workflows/ci-cleanup.yml:
      dbt run-operation drop_ci_schemas --args '{prefix: ci_pr_12}' --target ci

  Safety: refuses any prefix that does not start with "ci_pr_", so it can never drop a dev or prod schema.
#}

{% macro drop_ci_schemas(prefix) %}
    {%- if not prefix or not prefix.startswith('ci_pr_') -%}
        {{ exceptions.raise_compiler_error("drop_ci_schemas: prefix must start with 'ci_pr_', got '" ~ prefix ~ "'") }}
    {%- endif -%}

    {%- set catalog_clause = (' in ' ~ target.database) if target.type == 'databricks' else '' -%}
    {%- set schemas = run_query("show schemas" ~ catalog_clause ~ " like '" ~ prefix ~ "*'") -%}

    {%- for row in schemas.rows -%}
        {%- set name = row[0] -%}
        {#- exact prefix match: ci_pr_1 must not also catch ci_pr_12 -#}
        {%- if name == prefix or name.startswith(prefix ~ '_') -%}
            {%- set qualified = (target.database ~ '.' ~ name) if target.type == 'databricks' else name -%}
            {%- do log('dropping schema ' ~ qualified, info=true) -%}
            {%- do run_query('drop schema if exists ' ~ qualified ~ ' cascade') -%}
        {%- endif -%}
    {%- endfor -%}
    {%- do log(schemas.rows | length ~ ' schema(s) matched ' ~ prefix, info=true) -%}
{% endmacro %}
