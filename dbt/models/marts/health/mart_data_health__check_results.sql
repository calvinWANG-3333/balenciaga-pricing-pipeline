{#
  mart_data_health__check_results
  -------------------------------
  Grain   : one row per (dataset, scope, delivery date, check, subject) - from the LATEST gate run on
            each delivery.
  Purpose : the detail behind mart_data_health__deliveries. The data-health page draws it as a grid of
            deliveries x checks, and the triage agent starts from it: which check, on which subject
            (a market, a category), measured what, against which rule.
  A view for the same reason as the deliveries mart: the gate writes after dbt runs.
#}

{{ config(materialized='view') }}

with results as (

    select * from {{ ref('stg_ops__qa_check_results') }}

),

latest_run as (

    select dataset, scope, as_of_date, max_by(run_id, checked_at) as run_id
    from results
    group by dataset, scope, as_of_date

)

select
    r.dataset,
    r.scope,
    r.as_of_date,
    r.run_id,
    r.checked_at,
    r.check_id,
    r.dimension,
    r.severity,
    r.subject,
    r.observed,
    r.warn_rule,
    r.fail_rule,
    r.status,
    r.message
from results r
inner join latest_run l
    using (dataset, scope, as_of_date, run_id)
