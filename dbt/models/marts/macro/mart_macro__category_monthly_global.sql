{#
  mart_macro__category_monthly_global
  -----------------------------------
  Grain   : one row per (month, macro category) - all markets together.
  Purpose : the one-line headline per category ("Bags +5.8% in September").

  Prices cannot be averaged across markets (16 currencies), but % changes can. Again two choices:
    market_weighted_lfl_change   mean of the markets' own LFL changes - every market counts once
                                 (a mean of means: what the headline uses)
    product_weighted_lfl_change  pool every product-market pair - markets with more products weigh more
  Both are published; the gap between them says whether big and small markets moved differently.
#}

with markets as (

    select * from {{ ref('mart_macro__category_monthly') }}
    where lfl_n_products > 0

)

select
    cast({{ dbt_utils.generate_surrogate_key(['report_month', 'macro_category']) }} as string)
                                                                         as macro_global_row_id,
    cast(report_month as date)                                           as report_month,
    cast(macro_category as string)                                       as macro_category,
    cast(count(*) as int)                                                as n_markets,
    cast(sum(lfl_n_products) as int)                                     as lfl_n_product_markets,
    cast(round(avg(lfl_mean_change), 4) as decimal(10, 4))               as market_weighted_lfl_change,
    cast(round(sum(lfl_mean_change * lfl_n_products) / sum(lfl_n_products), 4) as decimal(10, 4))
                                                                         as product_weighted_lfl_change,
    cast(min(lfl_mean_change) as decimal(10, 4))                         as min_market_lfl_change,
    cast(max(lfl_mean_change) as decimal(10, 4))                         as max_market_lfl_change,
    cast(max_by(market, lfl_mean_change) as string)                      as market_with_highest_change
from markets
group by report_month, macro_category
