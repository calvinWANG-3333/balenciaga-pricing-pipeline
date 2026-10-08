{#
  int_observations__classified
  ----------------------------
  Grain   : one row per delivered crawl line (crawl_line_id) - same row count as staging.
  Purpose : give every line exactly ONE fate. This is where the bookkeeping of the whole pipeline
            closes: a line is either accepted, or excluded for a named reason.

     blocked_delivery        its file is a duplicate copy or a stale re-export
     exact_duplicate         second copy of an identical line in the same file
     quarantined_in_staging  a staging rule quarantined it
     price_scale_outlier     price is ~10x / 100x / 1000x away from the same product's usual price
     accepted                usable downstream

  The price-scale check needs CONTEXT, which is why it could not live in staging: "61600000" is a
  perfectly valid-looking yen price on its own; it is only wrong because the same bag was 616000 in
  every other crawl. Two references, in this order:
    1. history       the product's median price over its other readings (needs >= 3 readings)
    2. price ladder  markets crawled only monthly have too little history, so compare with the SAME
                     SKU in France in the SAME crawl, scaled by that market's typical local/EUR ratio
                     (the ratio itself is measured from the data: median over all SKUs)
  A reading a whole power of ten (x10, x100, /10 ...) away from its reference is an outlier.
#}

{{ config(materialized='table') }}

with observations as (

    select * from {{ ref('stg_crawl__product_observations') }}

),

batches as (

    select * from {{ ref('int_market_batches__assessed') }}

),

joined as (

    select
        o.*,
        b.market_batch_id,
        b.crawl_date,
        b.delivered_at,
        b.crawl_scope,
        b.is_trusted_delivery,
        b.is_partial                                                     as is_partial_market_batch
    from observations o
    inner join batches b
        on  b.source_file_name = o.source_file_name
        and b.market = o.market

),

pre_fate as (

    select
        *,
        case
            when not is_trusted_delivery                                 then 'blocked_delivery'
            when array_contains(dq_issues, 'exact_duplicate_line')       then 'exact_duplicate'
            when dq_status = 'quarantine'                                then 'quarantined_in_staging'
        end                                                              as pre_fate
    from joined

),

-- reference 1: the product's usual price = median over its candidate readings (same market)
usual_price as (

    select
        object_id,
        percentile_approx(price_local, 0.5)                              as usual_price_local,
        count(*)                                                         as n_candidate_observations
    from pre_fate
    where pre_fate is null and price_local > 0
    group by object_id

),

history_scored as (

    select
        p.*,
        u.usual_price_local,
        u.n_candidate_observations,
        log10(p.price_local / u.usual_price_local)                       as log10_ratio_to_usual
    from pre_fate p
    left join usual_price u using (object_id)

),

-- reference 2: the same SKU in France in the same crawl (only French readings that pass reference 1)
france as (

    select sku, crawl_date, percentile_approx(price_local, 0.5)          as france_price_eur
    from history_scored
    where pre_fate is null and market = 'FRA' and price_local > 0
      and not coalesce(n_candidate_observations >= 3
                       and abs(round(log10_ratio_to_usual)) >= 1
                       and abs(log10_ratio_to_usual - round(log10_ratio_to_usual)) < 0.1, false)
    group by sku, crawl_date

),

price_ladder as (

    -- typical local price / French price, per market, measured on the data
    select
        h.market,
        percentile_approx(h.price_local / f.france_price_eur, 0.5)       as ladder_factor
    from history_scored h
    inner join france f using (sku, crawl_date)
    where h.pre_fate is null and h.price_local > 0
    group by h.market

),

scored as (

    select
        h.*,
        case
            when h.n_candidate_observations >= 3 then h.usual_price_local
            else f.france_price_eur * l.ladder_factor
        end                                                              as reference_price_local,
        case
            when h.n_candidate_observations >= 3                         then 'history'
            when f.france_price_eur is not null and l.ladder_factor is not null then 'price_ladder'
        end                                                              as reference_method
    from history_scored h
    left join france f using (sku, crawl_date)
    left join price_ladder l using (market)

),

final_scored as (

    select
        *,
        log10(price_local / reference_price_local)                       as log10_ratio_to_reference
    from scored

)

select
    crawl_line_id,
    market_batch_id,
    source_file_name,
    delivered_file_name,
    crawl_date,
    delivered_at,
    crawl_scope,
    is_partial_market_batch,
    market,
    object_id,
    sku,
    sku_secondary,
    crawler_name,
    product_name,
    product_name_normalized,
    color,
    color_id,
    collection,
    stock_status,
    brand_macro_category,
    brand_micro_category,
    brand_super_micro_category,
    price_local,
    currency_code,
    crawled_at,
    dq_status,
    dq_issues,
    reference_method,
    round(reference_price_local, 2)                                      as reference_price_local,
    round(price_local / reference_price_local, 4)                        as price_to_reference_ratio,
    -- a whole power of ten away from the reference (x10, x100, /10 ...).
    -- Evaluated on every reading that has a price (also in blocked deliveries, for the legacy replay).
    coalesce(reference_method is not null
             and abs(round(log10_ratio_to_reference)) >= 1
             and abs(log10_ratio_to_reference - round(log10_ratio_to_reference)) < 0.1, false)
                                                                         as is_price_scale_outlier,
    coalesce(
        pre_fate,
        case when reference_method is not null
                  and abs(round(log10_ratio_to_reference)) >= 1
                  and abs(log10_ratio_to_reference - round(log10_ratio_to_reference)) < 0.1
             then 'price_scale_outlier' end,
        'accepted'
    )                                                                    as fate,
    array_contains(dq_issues, 'non_product_page')
      or array_contains(dq_issues, 'http_error_or_invalid')             as is_not_a_product_page
from final_scored
