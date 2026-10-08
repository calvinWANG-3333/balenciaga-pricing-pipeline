{{ config(materialized='view') }}

-- Published = released by the delivery gate: catalogue rows of the dates of a released delivery
-- (a date that serves both scopes is visible as soon as either delivery is released).
select c.*
from {{ ref('fct_catalogue_as_of') }} c
where c.as_of_date in (select as_of_date from {{ ref('pub_released_deliveries') }})
