{{ config(materialized='view') }}

-- Published = released by the delivery gate. BI and the agent read this view, never the mart directly.
select m.*
from {{ ref('mart_micro__hero_prices_weekly') }} m
where m.delivery_date in (
    select as_of_date from {{ ref('pub_released_deliveries') }} where scope = 'micro'
)
