{#
  Helpers that turn the business configuration in dbt_project.yml (vars) into SQL.
  Keeping the rules in vars means a reviewer changes ONE line in a pull request, not a CASE
  statement buried in a model.
#}

{# CASE expression: market code -> currency the website should show #}
{% macro market_currency(market_column) -%}
    case {{ market_column }}
    {%- for market, currency in var('market_currency').items() %}
        when '{{ market }}' then '{{ currency }}'
    {%- endfor %}
    end
{%- endmacro %}


{# CASE expression: ISO currency -> number of decimals (default 2) #}
{% macro currency_minor_units(currency_column) -%}
    case {{ currency_column }}
    {%- for currency, units in var('currency_minor_units').items() %}
        when '{{ currency }}' then {{ units }}
    {%- endfor %}
        else 2
    end
{%- endmacro %}


{# SQL array literal of every dq reason with the given handling ('fix' | 'warn' | 'quarantine') #}
{% macro dq_reasons_with_handling(handling) -%}
    {%- set reasons = [] -%}
    {%- for reason, h in var('dq_reasons').items() if h == handling -%}
        {%- do reasons.append("'" ~ reason ~ "'") -%}
    {%- endfor -%}
    array({{ reasons | join(', ') }})
{%- endmacro %}


{# Row status from its list of issues: the most severe handling wins #}
{% macro dq_status(issues_column) -%}
    case
        when size(array_intersect({{ issues_column }}, {{ dq_reasons_with_handling('quarantine') }})) > 0 then 'quarantine'
        when size(array_intersect({{ issues_column }}, {{ dq_reasons_with_handling('warn') }})) > 0 then 'warn'
        when size(array_intersect({{ issues_column }}, {{ dq_reasons_with_handling('fix') }})) > 0 then 'fixed'
        else 'pass'
    end
{%- endmacro %}


{#
  Mojibake = UTF-8 bytes that were decoded as Latin-1 somewhere upstream ("Prêt" -> "PrÃªt",
  "女士" -> "å¥³å£«"). Repair = encode back to the original bytes with Latin-1, decode as UTF-8.
  Only applied when the tell-tale byte pattern is present, so legitimate accents ("Prêt") are
  never touched.
#}
{% macro repair_mojibake(expr) -%}
    case
        when {{ expr }} rlike '[\\x{00C2}-\\x{00C3}][\\x{0080}-\\x{00BF}]|[\\x{00E4}-\\x{00E9}][\\x{0080}-\\x{00BF}]{2}'
            then decode(encode({{ expr }}, 'ISO-8859-1'), 'UTF-8')
        else {{ expr }}
    end
{%- endmacro %}


{# Normalize brand tag typos: 'Bal_super_micro_x' / 'ba_micro_x' -> 'bal_super_micro_x' / 'bal_micro_x' #}
{% macro normalize_brand_tag(expr) -%}
    regexp_replace(lower(trim({{ expr }})), '^ba_', 'bal_')
{%- endmacro %}
