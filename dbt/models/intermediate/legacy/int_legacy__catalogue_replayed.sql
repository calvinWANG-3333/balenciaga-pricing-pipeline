{#
  int_legacy__catalogue_replayed
  ------------------------------
  Grain   : one row per (as-of date, object) - what the OLD shared catalogue would have shown.
  Purpose : a faithful replay of the design this project replaces, so its failure can be measured
            instead of described. Same dates, same rows, same row-level quality rules as
            int_catalogue__as_of - ONLY the batch-selection rule differs:

      old rule  for each market, the catalogue holds whatever file was IMPORTED LAST
                (by delivery time, regardless of what crawl date it contains or whether it is a copy)
      new rule  the latest eligible crawl by CRAWL DATE (int_catalogue__as_of)

  Presence and price follow the same rules as the new design (a real product page is present; a
  quarantined reading has no price), so any difference measured downstream is caused by batch
  selection alone.

  This model exists for the incident analysis (qa_incident__legacy_vs_point_in_time) and is never
  used by a mart.
#}

{{ config(materialized='table') }}

with as_of_dates as (

    select * from {{ ref('int_as_of_dates') }}

),

batches as (

    select * from {{ ref('int_market_batches__assessed') }}       -- ALL batches: the old import had no trust check

),

observations as (

    select * from {{ ref('int_observations__classified') }}  -- every line, including blocked deliveries

),

last_imported as (

    select *
    from (
        select
            d.as_of_date,
            b.market,
            b.market_batch_id,
            b.source_file_name,
            b.crawl_date,
            b.delivered_file_name,
            row_number() over (
                partition by d.as_of_date, b.market
                order by b.delivered_at desc, b.source_file_name desc
            )                                                            as import_rank
        from as_of_dates d
        inner join batches b
            on b.delivered_at < d.knowledge_cutoff
    )
    where import_rank = 1

)

select
    li.as_of_date,
    li.market,
    o.object_id,
    any_value(o.sku)                                                     as sku,
    any_value(li.market_batch_id)                                        as legacy_batch_id,
    any_value(li.delivered_file_name)                                    as legacy_file,
    any_value(li.crawl_date)                                             as legacy_crawl_date,
    max(case when o.dq_status != 'quarantine' and not o.is_price_scale_outlier
             then o.price_local end)                                     as price_local,
    any_value(o.currency_code)                                           as currency_code
from last_imported li
inner join observations o
    on  o.source_file_name = li.source_file_name
    and o.market = li.market
    and not array_contains(o.dq_issues, 'exact_duplicate_line')
    and not o.is_not_a_product_page
group by li.as_of_date, li.market, o.object_id
