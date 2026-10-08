{#
  int_prices__historized
  ----------------------
  Grain   : one row per (object, price period) - a product in a market at one price, from the crawl
            where that price first appeared until the crawl where it changed.
  Purpose : slowly-changing-dimension type 2 (SCD2) of shelf prices, DERIVED from history.

  Why not a dbt snapshot? Snapshots record how a MUTABLE source looks each time dbt runs; if you miss a
  run, that history is gone forever. Our bronze is append-only, so the full history is already there:
  periods can be rebuilt from scratch, deterministically, at any time. (A "gaps and islands" pattern:
  LAG finds where the price changes, a running sum numbers each island.)
#}

{{ config(materialized='table') }}

with observations as (

    select object_id, sku, market, currency_code, crawl_date, price_local
    from {{ ref('int_observations__accepted') }}

),

flagged as (

    select
        *,
        case
            when lag(price_local) over (partition by object_id order by crawl_date) = price_local then 0
            else 1
        end                                                              as is_new_price
    from observations

),

islands as (

    select
        *,
        sum(is_new_price) over (
            partition by object_id order by crawl_date
            rows between unbounded preceding and current row
        )                                                                as price_period_number
    from flagged

),

periods as (

    select
        object_id,
        sku,
        market,
        currency_code,
        price_period_number,
        any_value(price_local)                                           as price_local,
        min(crawl_date)                                                  as valid_from,
        max(crawl_date)                                                  as last_observed_date,
        count(*)                                                         as n_observations
    from islands
    group by object_id, sku, market, currency_code, price_period_number

)

select
    {{ dbt_utils.generate_surrogate_key(['object_id', 'valid_from']) }}  as price_period_id,
    object_id,
    sku,
    market,
    currency_code,
    price_period_number,
    price_local,
    lag(price_local) over (partition by object_id order by valid_from)  as previous_price_local,
    round(price_local / lag(price_local) over (partition by object_id order by valid_from) - 1, 4)
                                                                         as change_vs_previous,
    valid_from,
    lead(valid_from) over (partition by object_id order by valid_from)  as valid_to,
    last_observed_date,
    n_observations,
    lead(valid_from) over (partition by object_id order by valid_from) is null
                                                                         as is_current_period
from periods
