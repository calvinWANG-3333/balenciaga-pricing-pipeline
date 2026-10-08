{#
  fct_price_observations
  ----------------------
  Grain   : one row per accepted price reading = (market batch, product). Append-mostly history.
  Purpose : the event-level fact every price question can be answered from.

  Materialization: INCREMENTAL. Each run only processes deliveries that arrived recently and MERGEs
  them on observation_id (insert new, update existing), instead of rebuilding ~200k rows every week.
    - lookback window: re-process the last N days of deliveries, so a reading whose classification
      changed when newer crawls arrived (e.g. a price-outlier decision) is updated, not left stale
    - a full rebuild (`dbt build --full-refresh`) is always possible and always gives the same result,
      because the input history is immutable
    - equal_rowcount against int_observations__accepted (tested) catches any drift between the two
  On Databricks the strategy is MERGE (Delta). The local Spark test harness has no Delta, so there the
  model simply rebuilds in full (insert_overwrite without the incremental filter).
#}

{{ config(
    materialized='incremental',
    unique_key='observation_id',
    incremental_strategy=('merge' if target.type == 'databricks' else 'insert_overwrite'),
    on_schema_change='append_new_columns'
) }}

with accepted as (

    select * from {{ ref('int_observations__accepted') }}

    {% if is_incremental() and target.type == 'databricks' %}
    -- only deliveries newer than (latest already loaded - lookback)
    where delivered_at > (
        select coalesce(max(delivered_at), timestamp '1900-01-01')
               - interval {{ var('incremental_lookback_days', 35) }} days
        from {{ this }}
    )
    {% endif %}

)

select
    cast(crawl_line_id as string)                                        as observation_id,
    cast(market_batch_id as string)                                      as market_batch_id,
    cast(crawl_date as date)                                             as crawl_date,
    cast(delivered_at as timestamp)                                      as delivered_at,
    cast(crawl_scope as string)                                          as crawl_scope,
    cast(is_partial_market_batch as boolean)                             as is_partial_market_batch,
    cast(market as string)                                               as market,
    cast(sku as string)                                                  as sku,
    cast(object_id as string)                                            as object_id,
    cast(price_local as decimal(18, 2))                                  as price_local,
    cast(currency_code as string)                                        as currency_code,
    cast(stock_status as string)                                         as stock_status,
    cast(crawled_at as timestamp)                                        as crawled_at
from accepted
