{#
  Where does a model land?

  Plain: in development every developer gets their own set of shelves (dbt_rwang_staging,
  dbt_rwang_marts ...) so nobody's half-finished work overwrites anyone else's. In production the
  shelves have clean, shared names (staging, marts ...).

  dbt's default behaviour is "<target schema>_<custom schema>" in EVERY environment. This override
  keeps that for development and uses the bare custom schema in the production target.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}
    {%- if custom_schema_name is none -%}
        {{ default_schema }}
    {%- elif target.name == 'prod' -%}
        {{ custom_schema_name | trim }}
    {%- else -%}
        {{ default_schema }}_{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
