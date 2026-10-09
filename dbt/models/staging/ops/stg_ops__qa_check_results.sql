{#
  stg_ops__qa_check_results
  -------------------------
  Grain   : one row per (gate run, dataset, delivery, check, subject) - identical to the source.
  Purpose : the single entry point to the gate's audit log. The gate (Python, qa/) writes typed columns,
            so nothing is cleaned here; this model exists so marts never read a source directly and a
            change in the gate's table touches one file.
#}

select
    run_id,
    checked_at,
    dataset,
    scope,
    as_of_date,
    check_id,
    dimension,
    severity,
    subject,
    observed,
    warn_rule,
    fail_rule,
    status,
    message
from {{ source('ops', 'qa_check_results') }}
