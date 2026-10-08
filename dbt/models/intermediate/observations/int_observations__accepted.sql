{#
  int_observations__accepted
  --------------------------
  Grain   : one row per (market batch, object) - one trustworthy price reading of one product in one
            market in one trusted delivery.
  Purpose : the clean, append-only price history every downstream model builds on.
#}

select
    crawl_line_id,
    market_batch_id,
    source_file_name,
    crawl_date,
    delivered_at,
    crawl_scope,
    is_partial_market_batch,
    market,
    object_id,
    sku,
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
    crawled_at
from {{ ref('int_observations__classified') }}
where fate = 'accepted'
