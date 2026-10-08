{{ config(materialized='view') }}

-- Price change events, up to the latest released delivery: a change observed in a crawl that no
-- released delivery has used yet is not public.
select *
from {{ ref('fct_price_changes') }}
where changed_on_crawl_date < (select max(as_of_date) from {{ ref('pub_released_deliveries') }})
