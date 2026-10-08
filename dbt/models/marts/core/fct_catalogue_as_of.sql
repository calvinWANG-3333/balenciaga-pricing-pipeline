{#
  fct_catalogue_as_of
  -------------------
  Grain   : one row per (reporting date, product-market).
  Purpose : the point-in-time catalogue exposed to consumers (BI, agent). Micro and Macro are
            projections of this table at their own dates - and a test proves it.
#}

select
    cast(catalogue_row_id as string)                                     as catalogue_row_id,
    cast(as_of_date as date)                                             as as_of_date,
    cast(is_micro_date as boolean)                                       as is_micro_date,
    cast(is_macro_date as boolean)                                       as is_macro_date,
    cast(market as string)                                               as market,
    cast(sku as string)                                                  as sku,
    cast(object_id as string)                                            as object_id,
    cast(presence_crawl_date as date)                                    as presence_crawl_date,
    cast(presence_age_days as int)                                       as presence_age_days,
    cast(has_price as boolean)                                           as has_price,
    cast(price_local as decimal(18, 2))                                  as price_local,
    cast(currency_code as string)                                        as currency_code,
    cast(price_crawl_date as date)                                       as price_crawl_date,
    cast(is_price_carried_forward as boolean)                            as is_price_carried_forward
from {{ ref('int_catalogue__as_of') }}
