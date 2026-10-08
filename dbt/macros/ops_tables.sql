{#
  Operational tables of the delivery gate
  ---------------------------------------
  Plain: dbt builds the marts; a separate program (qa/, the delivery gate) inspects each delivery and
  writes down what it found and whether the delivery was released. Those notes must live in the warehouse
  too, next to the data they judge - but dbt must NOT rebuild them, or it would erase the history.

  So dbt only guarantees the empty tables exist (CREATE ... IF NOT EXISTS, run before every dbt command
  via on-run-start); the gate appends rows; dbt reads them back as a source (models/sources/ops).

    qa_check_results   one row per (gate run, delivery, check, subject)   - the audit trail
    delivery_releases  one row per release decision                         - what BI is allowed to see
  On Databricks both are Delta tables with delta.appendOnly = true: an audit log nobody can rewrite.
#}

{% macro ops_schema() -%}
    {%- if target.name == 'prod' -%} ops {%- else -%} {{ target.schema }}_ops {%- endif -%}
{%- endmacro %}

{% macro ops_relation(table_name) -%}
    {%- if target.type == 'databricks' -%}{{ target.database }}.{%- endif -%}{{ ops_schema() }}.{{ table_name }}
{%- endmacro %}

{% macro create_ops_tables() %}
    {%- set table_suffix -%}
        {%- if target.type == 'databricks' %} tblproperties ('delta.appendOnly' = 'true')
        {%- else %} using parquet
        {%- endif -%}
    {%- endset -%}

    {%- set schema_ref -%}
        {%- if target.type == 'databricks' -%}{{ target.database }}.{%- endif -%}{{ ops_schema() }}
    {%- endset -%}

    {%- set create_results -%}
    create table if not exists {{ ops_relation('qa_check_results') }} (
        run_id        string    comment 'one gate execution',
        checked_at    timestamp comment 'when the gate ran',
        dataset       string    comment 'marts = what clients receive; legacy_replay = the old design, audited for comparison',
        scope         string    comment 'micro | macro',
        as_of_date    date      comment 'the delivery being audited',
        check_id      string,
        dimension     string    comment 'data-quality dimension of the check',
        severity      string    comment 'block = a failure stops the release; warn = never blocks',
        subject       string    comment 'what the value is about (a market, a category) or all',
        observed      double    comment 'measured value',
        warn_rule     string,
        fail_rule     string,
        status        string    comment 'pass | warn | fail | skip',
        message       string
    ) {{ table_suffix }}
    {%- endset -%}

    {%- set create_releases -%}
    create table if not exists {{ ops_relation('delivery_releases') }} (
        release_id    string,
        scope         string    comment 'micro | macro',
        as_of_date    date      comment 'the delivery made visible to BI',
        run_id        string    comment 'the gate run that decided it',
        decision      string    comment 'PASS | WARN (BLOCK is never released unless forced)',
        is_forced     boolean   comment 'released by a human despite a BLOCK',
        reason        string    comment 'mandatory when forced',
        released_at   timestamp,
        released_by   string
    ) {{ table_suffix }}
    {%- endset -%}

    {#- one statement per call: Spark and the Databricks SQL endpoint run a single statement at a time -#}
    {%- if execute -%}
        {%- do run_query('create schema if not exists ' ~ schema_ref) -%}
        {%- do run_query(create_results) -%}
        {%- do run_query(create_releases) -%}
    {%- endif -%}
{% endmacro %}
