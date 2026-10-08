{{ config(materialized='view') }}

-- Published = released by the delivery gate. The global table has no as_of_date: a month is published
-- when its month-end Macro delivery is.
select g.*
from {{ ref('mart_macro__category_monthly_global') }} g
where g.report_month in (
    select trunc(as_of_date, 'MM') from {{ ref('pub_released_deliveries') }} where scope = 'macro'
)
