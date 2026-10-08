{{ config(materialized='view') }}

-- Published = released by the delivery gate. BI and the agent read this view, never the mart directly.
select m.*
from {{ ref('mart_macro__category_monthly') }} m
where m.as_of_date in (
    select as_of_date from {{ ref('pub_released_deliveries') }} where scope = 'macro'
)
