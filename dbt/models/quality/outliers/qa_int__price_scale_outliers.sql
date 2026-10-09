{#
  qa_int__price_scale_outliers
  ----------------------------
  Grain   : one row per observation excluded as a price-scale outlier.
  Purpose : the readings that look valid on their own but sit a whole power of ten away from the same
            product's usual price (a crawler that wrote minor units, or dropped / added a zero).
#}

select
    crawl_line_id,
    delivered_file_name,
    crawl_date,
    market,
    object_id,
    sku,
    product_name,
    price_local,
    reference_method,
    reference_price_local,
    price_to_reference_ratio,
    currency_code
from {{ ref('int_observations__classified') }}
where fate = 'price_scale_outlier'
