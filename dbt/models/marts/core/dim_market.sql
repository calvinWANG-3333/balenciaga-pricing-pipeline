{#
  dim_market
  ----------
  Grain   : one row per market.
  Purpose : market reference for every consumer, with the crawl cadence that decides which
            deliverable can use it (weekly markets feed Micro; all markets feed Macro).
#}

select
    cast(market as string)                                               as market,
    cast(market_name as string)                                          as market_name,
    cast(region as string)                                               as region,
    cast(currency_code as string)                                        as currency_code,
    cast(crawl_cadence as string)                                        as crawl_cadence,
    cast(crawl_cadence = 'weekly' as boolean)                            as is_in_micro_scope,
    cast(display_order as int)                                           as display_order
from {{ ref('markets') }}
