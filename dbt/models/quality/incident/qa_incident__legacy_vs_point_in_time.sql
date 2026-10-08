{#
  qa_incident__legacy_vs_point_in_time
  ------------------------------------
  Grain   : one row per (as-of date, market).
  Purpose : the incident, replayed and measured. For every reporting date and market: which crawl the
            old shared catalogue would have served, which crawl the point-in-time model serves, and how
            many products / prices disagree between the two.
#}

with legacy as (

    select * from {{ ref('int_legacy__catalogue_replayed') }}

),

pit as (

    select * from {{ ref('int_catalogue__as_of') }}

),

compared as (

    select
        coalesce(p.as_of_date, l.as_of_date)                             as as_of_date,
        coalesce(p.market, l.market)                                     as market,
        p.object_id is not null                                          as in_point_in_time,
        l.object_id is not null                                          as in_legacy,
        p.presence_crawl_date,
        l.legacy_crawl_date,
        l.legacy_file,
        p.price_local                                                    as pit_price,
        l.price_local                                                    as legacy_price
    from pit p
    full outer join legacy l
        on  l.as_of_date = p.as_of_date
        and l.object_id = p.object_id

)

select
    as_of_date,
    market,
    max(presence_crawl_date)                                             as point_in_time_crawl_date,
    max(legacy_crawl_date)                                               as legacy_crawl_date,
    max(legacy_file)                                                     as legacy_file,
    count_if(in_point_in_time)                                           as n_products_point_in_time,
    count_if(in_legacy)                                                  as n_products_legacy,
    count_if(in_point_in_time and not in_legacy)                         as n_missing_in_legacy,
    count_if(in_legacy and not in_point_in_time)                         as n_extra_in_legacy,
    count_if(in_point_in_time and in_legacy and pit_price != legacy_price) as n_price_differences,
    round(count_if(in_point_in_time and in_legacy and pit_price != legacy_price)
          / nullif(count_if(in_point_in_time and in_legacy), 0), 4)      as share_prices_different,
    max(legacy_crawl_date) != max(presence_crawl_date)
      or count_if(in_point_in_time != in_legacy) > 0
      or count_if(in_point_in_time and in_legacy and pit_price != legacy_price) > 0
                                                                         as legacy_would_be_wrong
from compared
group by as_of_date, market
