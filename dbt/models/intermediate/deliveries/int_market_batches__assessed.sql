{#
  int_market_batches__assessed
  ----------------------------
  Grain   : one row per (delivered file, market) - "the crawl of market M inside delivery D".
  Purpose : the unit the point-in-time logic chooses from. A market batch is ELIGIBLE to represent
            "the catalogue of market M" only if
              - its delivery is trusted (not a duplicate copy, not a stale re-export), and
              - the market is complete in that delivery (not a partial crawl).
            A partial market batch still contributes valid prices (see int_catalogue__as_of), but it
            cannot define which products are on sale: 45% of a catalogue would make 55% look delisted.
#}

with deliveries as (

    select * from {{ ref('int_deliveries__profiled') }}

),

observations as (

    select * from {{ ref('stg_crawl__product_observations') }}

),

market_rows as (

    select
        source_file_name,
        market,
        count(*)                                                         as n_lines,
        count_if(dq_status != 'quarantine')                              as n_usable_lines,
        min(crawled_at)                                                  as first_crawled_at,
        max(crawled_at)                                                  as last_crawled_at
    from observations
    group by source_file_name, market

)

select
    {{ dbt_utils.generate_surrogate_key(['m.source_file_name', 'm.market']) }}   as market_batch_id,
    m.source_file_name,
    d.delivered_file_name,
    m.market,
    d.crawl_scope,
    d.content_crawl_date                                                 as crawl_date,
    d.delivered_at,
    m.n_lines,
    m.n_usable_lines,
    m.first_crawled_at,
    m.last_crawled_at,
    d.file_status                                                        as delivery_status,
    d.is_trusted                                                         as is_trusted_delivery,
    array_contains(d.partial_markets, m.market)                          as is_partial,
    d.is_trusted and not array_contains(d.partial_markets, m.market)     as is_eligible
from market_rows m
inner join deliveries d using (source_file_name)
