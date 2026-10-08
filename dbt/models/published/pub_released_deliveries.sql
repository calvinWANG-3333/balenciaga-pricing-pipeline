{#
  pub_released_deliveries
  -----------------------
  Grain   : one row per released delivery (scope, as_of_date).
  Purpose : the PUBLISH step of write-audit-publish. dbt builds every delivery into the marts (WRITE);
            the delivery gate audits it (AUDIT) and, if it passes, appends a row to ops.delivery_releases
            (PUBLISH). Every view in this folder exposes only released deliveries, so BI and the agent can
            never read a delivery the gate has not cleared.
  A view, so a release is visible the moment the gate writes it - no dbt run needed.
#}

{{ config(materialized='view') }}

select
    scope,
    as_of_date,
    max_by(decision, released_at)                                        as decision,
    bool_or(is_forced)                                                   as is_forced,
    min(released_at)                                                     as first_released_at
from {{ source('ops', 'delivery_releases') }}
group by scope, as_of_date
