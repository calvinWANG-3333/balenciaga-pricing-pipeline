{#
  mart_macro__category_monthly
  ----------------------------
  Grain   : one row per (month, market, macro category).
  Purpose : the Macro deliverable - the broad picture per category: how many products, the price range
            (min / median / mean / max, in local currency) and the like-for-like change vs last month.

  Like-for-like (LFL): compare ONLY products priced at both month-ends. Otherwise launches and
  discontinuations move the average even when no price changed (a new EUR 15,000 bag lifts the mean).

  Two LFL definitions are published side by side, because they answer different questions:
    lfl_mean_change    mean of each product's own % change    -> "how much did a typical product move"
    lfl_ratio_of_means sum(new prices) / sum(old prices) - 1  -> "how much did the basket move"
                                                                 (expensive products weigh more)
  Example: product A 100 -> 110 (+10%), product B 1,000 -> 1,000 (0%).
    mean of changes = +5.0%      ratio of means = 1,110 / 1,100 - 1 = +0.9%
  The deliverable headline uses lfl_mean_change (each product counts once); the unit test pins this.

  Reads only the point-in-time catalogue at month-end dates.
#}

with catalogue as (

    select * from {{ ref('int_catalogue__as_of') }}
    where is_macro_date and has_price

),

products as (

    select sku, macro_category from {{ ref('int_products__categorized') }}
    where macro_category is not null

),

priced as (

    select
        c.as_of_date,
        trunc(c.as_of_date, 'MM')                                        as report_month,
        c.market,
        c.currency_code,
        p.macro_category,
        c.sku,
        c.price_local
    from catalogue c
    inner join products p using (sku)

),

month_ends as (

    select
        as_of_date,
        lag(as_of_date) over (order by as_of_date)                       as previous_as_of_date
    from (select distinct as_of_date from priced)

),

-- like-for-like pairs: same product, same market, priced at this AND the previous month-end
lfl_pairs as (

    select
        cur.as_of_date,
        cur.market,
        cur.macro_category,
        cur.price_local / prev.price_local - 1                           as product_change,
        cur.price_local                                                  as price_now,
        prev.price_local                                                 as price_before
    from priced cur
    inner join month_ends me on me.as_of_date = cur.as_of_date
    inner join priced prev
        on  prev.as_of_date = me.previous_as_of_date
        and prev.market = cur.market
        and prev.sku = cur.sku

),

lfl as (

    select
        as_of_date,
        market,
        macro_category,
        count(*)                                                         as lfl_n_products,
        avg(product_change)                                              as lfl_mean_change,
        sum(price_now) / sum(price_before) - 1                           as lfl_ratio_of_means,
        avg(case when product_change > 0 then 1.0 else 0.0 end)          as lfl_share_increased
    from lfl_pairs
    group by as_of_date, market, macro_category

),

levels as (

    select
        as_of_date,
        report_month,
        market,
        macro_category,
        any_value(currency_code)                                         as currency_code,
        count(*)                                                         as n_products,
        min(price_local)                                                 as min_price,
        percentile_approx(price_local, 0.5)                              as median_price,
        avg(price_local)                                                 as mean_price,
        max(price_local)                                                 as max_price
    from priced
    group by as_of_date, report_month, market, macro_category

)

select
    cast({{ dbt_utils.generate_surrogate_key(['l.report_month', 'l.market', 'l.macro_category']) }} as string)
                                                                         as macro_row_id,
    cast(l.report_month as date)                                         as report_month,
    cast(l.as_of_date as date)                                           as as_of_date,
    cast(l.market as string)                                             as market,
    cast(l.macro_category as string)                                     as macro_category,
    cast(l.currency_code as string)                                      as currency_code,
    cast(l.n_products as int)                                            as n_products,
    cast(l.min_price as decimal(18, 2))                                  as min_price,
    cast(l.median_price as decimal(18, 2))                               as median_price,
    cast(round(l.mean_price, 2) as decimal(18, 2))                       as mean_price,
    cast(l.max_price as decimal(18, 2))                                  as max_price,
    cast(coalesce(f.lfl_n_products, 0) as int)                           as lfl_n_products,
    cast(round(f.lfl_mean_change, 4) as decimal(10, 4))                  as lfl_mean_change,
    cast(round(f.lfl_ratio_of_means, 4) as decimal(10, 4))               as lfl_ratio_of_means,
    cast(round(f.lfl_share_increased, 4) as decimal(10, 4))              as lfl_share_increased
from levels l
left join lfl f
    on  f.as_of_date = l.as_of_date
    and f.market = l.market
    and f.macro_category = l.macro_category
