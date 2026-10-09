{#
  mart_data_health__deliveries
  ----------------------------
  Grain   : one row per (dataset, scope, delivery date) - the latest gate verdict on each delivery.
  Purpose : the "data health" page of the BI site and the triage agent's starting point: was this delivery
            audited, what was the verdict, how many checks warned or failed, and is it published.

  Materialized as a VIEW on purpose (override of the marts default): the gate writes its results AFTER
  dbt has run. A table would show yesterday's verdicts until the next dbt run; a view is always current.
#}

{{ config(materialized='view') }}

with results as (

    select * from {{ ref('stg_ops__qa_check_results') }}

),

latest_run as (

    select dataset, scope, as_of_date, max_by(run_id, checked_at) as run_id, max(checked_at) as checked_at
    from results
    group by dataset, scope, as_of_date

),

summary as (

    select
        r.dataset,
        r.scope,
        r.as_of_date,
        r.run_id,
        lr.checked_at,
        count(*)                                                         as n_results,
        sum(case when r.status = 'pass' then 1 else 0 end)               as n_pass,
        sum(case when r.status = 'warn' then 1 else 0 end)               as n_warn,
        sum(case when r.status = 'fail' then 1 else 0 end)               as n_fail,
        sum(case when r.status = 'skip' then 1 else 0 end)               as n_skip,
        sum(case when r.status = 'fail' and r.severity = 'block' then 1 else 0 end)
                                                                         as n_blocking_failures,
        sort_array(collect_set(case when r.status in ('warn', 'fail') then r.check_id end))
                                                                         as checks_not_passing
    from results r
    inner join latest_run lr
        using (dataset, scope, as_of_date, run_id)
    group by r.dataset, r.scope, r.as_of_date, r.run_id, lr.checked_at

),

releases as (

    select scope, as_of_date, max_by(decision, released_at) as released_decision,
           bool_or(is_forced) as is_forced, max(released_at) as released_at
    from {{ ref('stg_ops__delivery_releases') }}
    group by scope, as_of_date

)

select
    s.*,
    case
        when s.n_blocking_failures > 0                                  then 'BLOCK'
        when s.n_warn + s.n_fail > 0                                     then 'WARN'
        else 'PASS'
    end                                                                  as gate_decision,
    s.dataset = 'marts' and rl.as_of_date is not null                    as is_published,
    case when s.dataset = 'marts' then rl.is_forced end                  as is_forced_release,
    case when s.dataset = 'marts' then rl.released_at end                as released_at
from summary s
left join releases rl
    on  rl.scope = s.scope
    and rl.as_of_date = s.as_of_date
