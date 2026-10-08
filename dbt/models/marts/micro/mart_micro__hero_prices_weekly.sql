{#
  mart_micro__hero_prices_weekly
  ------------------------------
  Grain   : one row per (weekly delivery date, hero product, weekly market) - a complete grid: a hero
            that could not be found still has its row, with status 'not_found'.
  Purpose : the Micro deliverable. Every Tuesday a client receives the price of each tracked hero
            product in each weekly market, the change vs the previous delivery, and flags that used to be
            checked by hand in a spreadsheet (stale crawl, carried-forward price, not found).

  "Not found" vs "page error": a hero missing from the crawl is not the same as a hero whose product
  page returned an error (HTTP 4xx/5xx, captcha, empty page). The first may mean the product left the
  catalogue; the second only means the crawler could not read it that week. Telling them apart stops an
  analyst from reporting a delisting that never happened.

  Reads only the point-in-time catalogue at Micro dates - never a shared, mutable table.
#}

with dates as (

    select as_of_date from {{ ref('int_as_of_dates') }} where is_micro_date

),

pointers as (

    select * from {{ ref('micro_pointers') }}

),

markets as (

    select * from {{ ref('dim_market') }} where is_in_micro_scope

),

catalogue as (

    select * from {{ ref('int_catalogue__as_of') }} where is_micro_date

),

-- the crawl each market was served from at each date (one per date x market - the killer test proves it)
served_crawls as (

    select distinct as_of_date, market, presence_batch_id, presence_crawl_date
    from catalogue

),

-- products whose page could not be read in a given crawl (error page, not a product page)
unreadable_pages as (

    select distinct market_batch_id, sku
    from {{ ref('int_observations__classified') }}
    where is_not_a_product_page

),

-- the full grid: every date x every hero x every weekly market
grid as (

    select d.as_of_date, p.pointer_id, p.sku, p.product_label, m.market, m.currency_code
    from dates d
    cross join pointers p
    cross join markets m

),

joined as (

    select
        g.*,
        c.object_id,
        u.sku is not null                                                as is_page_error,
        coalesce(c.presence_crawl_date, s.presence_crawl_date)           as crawl_date_used,
        c.has_price,
        c.price_local,
        c.price_crawl_date,
        c.is_price_carried_forward,
        -- previous delivery's price: the last non-null price before this date (skips weeks without one)
        last_value(c.price_local, true) over (
            partition by g.pointer_id, g.market
            order by g.as_of_date
            rows between unbounded preceding and 1 preceding
        )                                                                as previous_price_local
    from grid g
    left join catalogue c
        on  c.as_of_date = g.as_of_date
        and c.sku = g.sku
        and c.market = g.market
    left join served_crawls s
        on  s.as_of_date = g.as_of_date
        and s.market = g.market
    left join unreadable_pages u
        on  u.market_batch_id = s.presence_batch_id
        and u.sku = g.sku
        and c.object_id is null

)

select
    cast({{ dbt_utils.generate_surrogate_key(['as_of_date', 'pointer_id', 'market']) }} as string)
                                                                         as micro_row_id,
    cast(as_of_date as date)                                             as delivery_date,
    cast(pointer_id as string)                                           as pointer_id,
    cast(sku as string)                                                  as sku,
    cast(product_label as string)                                        as product_label,
    cast(market as string)                                               as market,
    cast(currency_code as string)                                        as currency_code,
    cast(price_local as decimal(18, 2))                                  as price_local,
    cast(previous_price_local as decimal(18, 2))                         as previous_price_local,
    cast(round(price_local / previous_price_local - 1, 4) as decimal(10, 4))
                                                                         as change_vs_previous_pct,
    cast(case
        when object_id is null and is_page_error       then 'page_error'
        when object_id is null                         then 'not_found'
        when not has_price                             then 'no_valid_price'
        when previous_price_local is null              then 'first_delivery'
        when price_local > previous_price_local        then 'price_increase'
        when price_local < previous_price_local        then 'price_decrease'
        else 'unchanged'
    end as string)                                                       as price_status,
    cast(crawl_date_used as date)                                        as crawl_date_used,
    cast(price_crawl_date as date)                                       as price_crawl_date,
    cast(coalesce(datediff(as_of_date, crawl_date_used) > 7, false) as boolean)
                                                                         as is_stale_crawl,
    cast(coalesce(is_price_carried_forward, false) as boolean)           as is_price_carried_forward
from joined
