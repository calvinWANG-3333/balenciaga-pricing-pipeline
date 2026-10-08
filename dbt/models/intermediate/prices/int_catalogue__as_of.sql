{#
  int_catalogue__as_of
  --------------------
  Grain   : one row per (as-of date, object) - "product P in market M, as it was known at the end of
            day D".
  Purpose : THE fix for the shared-catalogue incident. The catalogue at any date is a pure function of
            the immutable history and that date:

    1. presence  for each market, take the LATEST ELIGIBLE crawl of that market whose crawl date is
                 <= D and which was delivered before the end of D. Its products are "on sale at D".
                 Eligible = trusted delivery (not a copy, not a stale re-export) and complete market.
                 Chosen by CRAWL DATE, never by "whatever was imported last".
    2. price     the latest ACCEPTED price reading of that product delivered before the end of D.
                 Usually it comes from the same crawl; if that crawl's reading was quarantined, the
                 last trustworthy price is carried forward and flagged.

  Micro reads it at weekly dates, Macro at month-ends. They never share a mutable table, so one cannot
  change the other's numbers: re-delivering an old crawl, or importing in a different order, cannot
  move any row of this model.
#}

{{ config(materialized='table') }}

with as_of_dates as (

    select * from {{ ref('int_as_of_dates') }}

),

batches as (

    select * from {{ ref('int_market_batches__assessed') }}
    where is_eligible

),

classified as (

    select * from {{ ref('int_observations__classified') }}

),

accepted as (

    select * from {{ ref('int_observations__accepted') }}

),

-- 1. for every date and market: the latest eligible crawl known at that date
chosen_batches as (

    select *
    from (
        select
            d.as_of_date,
            d.is_micro_date,
            d.is_macro_date,
            b.market,
            b.market_batch_id                                            as presence_batch_id,
            b.crawl_date                                                 as presence_crawl_date,
            b.crawl_scope                                                as presence_crawl_scope,
            row_number() over (
                partition by d.as_of_date, b.market
                order by b.crawl_date desc, b.delivered_at desc
            )                                                            as recency_rank
        from as_of_dates d
        inner join batches b
            on  b.crawl_date <= d.as_of_date
            and b.delivered_at < d.knowledge_cutoff
    )
    where recency_rank = 1

),

-- products present in that crawl (any real product page, whatever the quality of its price reading)
present as (

    select distinct
        cb.as_of_date,
        cb.is_micro_date,
        cb.is_macro_date,
        cb.market,
        cb.presence_batch_id,
        cb.presence_crawl_date,
        cb.presence_crawl_scope,
        c.object_id,
        c.sku
    from chosen_batches cb
    inner join classified c
        on  c.market_batch_id = cb.presence_batch_id
        and c.fate in ('accepted', 'price_scale_outlier', 'quarantined_in_staging')
        and not c.is_not_a_product_page

),

-- 2. latest trustworthy price known at that date
latest_price as (

    select *
    from (
        select
            p.as_of_date,
            p.object_id,
            a.price_local,
            a.currency_code,
            a.crawl_date                                                 as price_crawl_date,
            a.market_batch_id                                            as price_batch_id,
            row_number() over (
                partition by p.as_of_date, p.object_id
                order by a.crawl_date desc, a.delivered_at desc
            )                                                            as recency_rank
        from present p
        inner join as_of_dates d using (as_of_date)
        inner join accepted a
            on  a.object_id = p.object_id
            and a.crawl_date <= p.as_of_date
            and a.delivered_at < d.knowledge_cutoff
    )
    where recency_rank = 1

)

select
    {{ dbt_utils.generate_surrogate_key(['p.as_of_date', 'p.object_id']) }}  as catalogue_row_id,
    p.as_of_date,
    p.is_micro_date,
    p.is_macro_date,
    p.market,
    p.object_id,
    p.sku,
    p.presence_batch_id,
    p.presence_crawl_date,
    p.presence_crawl_scope,
    datediff(p.as_of_date, p.presence_crawl_date)                        as presence_age_days,
    lp.price_local,
    lp.currency_code,
    lp.price_crawl_date,
    lp.price_batch_id,
    lp.price_local is not null                                           as has_price,
    -- the crawl that shows the product had no trustworthy reading: last known price is used instead
    coalesce(lp.price_crawl_date < p.presence_crawl_date, false)         as is_price_carried_forward
from present p
left join latest_price lp
    on  lp.as_of_date = p.as_of_date
    and lp.object_id = p.object_id
