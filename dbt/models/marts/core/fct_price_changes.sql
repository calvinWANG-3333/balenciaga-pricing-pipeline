{#
  fct_price_changes
  -----------------
  Grain   : one row per price change event = (product-market, crawl where the new price first appeared).
  Purpose : "what moved, where, when, by how much" - the most asked question about a price monitor.
  Built from the SCD2 price periods: every period except the first one of an object is a change.
  macro_category is denormalized from the product dimension so the semantic layer (and the metrics
  agent) can slice changes by category without a join.
#}

with periods as (

    select * from {{ ref('int_prices__historized') }}

),

products as (

    select sku, macro_category from {{ ref('int_products__categorized') }}

)

select
    cast(price_period_id as string)                                      as price_change_id,
    cast(object_id as string)                                            as object_id,
    cast(periods.sku as string)                                          as sku,
    cast(market as string)                                               as market,
    cast(p.macro_category as string)                                     as macro_category,
    cast(currency_code as string)                                        as currency_code,
    cast(valid_from as date)                                             as changed_on_crawl_date,
    cast(previous_price_local as decimal(18, 2))                         as price_before,
    cast(price_local as decimal(18, 2))                                  as price_after,
    cast(change_vs_previous as decimal(10, 4))                           as change_pct,
    cast(case when price_local > previous_price_local then 'increase' else 'decrease' end as string)
                                                                         as change_direction
from periods
left join products p
    on p.sku = periods.sku
where previous_price_local is not null
