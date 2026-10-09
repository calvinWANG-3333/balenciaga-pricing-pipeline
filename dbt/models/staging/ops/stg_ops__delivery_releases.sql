{#
  stg_ops__delivery_releases
  --------------------------
  Grain   : one row per release decision - identical to the source.
  Purpose : the single entry point to the publish switch. Read by the published layer (which deliveries
            BI may see) and by the data-health mart (which deliveries were released, and how).
#}

select
    release_id,
    scope,
    as_of_date,
    run_id,
    decision,
    is_forced,
    reason,
    released_at,
    released_by
from {{ source('ops', 'delivery_releases') }}
