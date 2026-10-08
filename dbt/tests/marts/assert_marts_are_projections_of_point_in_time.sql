-- Micro and Macro are not allowed to have their own version of the truth.
-- Every price the Micro mart shows, and every product count / min / max the Macro mart shows, must be
-- reproducible from the point-in-time catalogue at the same date. Together with the killer test this
-- closes the loop: the catalogue is right, and the deliverables faithfully read it.
-- (Same SKU + same date => same price, whichever deliverable you look at.)

with micro_mismatch as (

    select
        'micro' as deliverable, cast(m.delivery_date as string) as as_of, m.market, m.sku as item,
        cast(m.price_local as string) as mart_value, cast(c.price_local as string) as catalogue_value
    from {{ ref('mart_micro__hero_prices_weekly') }} m
    left join {{ ref('fct_catalogue_as_of') }} c
        on  c.as_of_date = m.delivery_date
        and c.sku = m.sku
        and c.market = m.market
    where not (m.price_local <=> c.price_local)

),

macro_recomputed as (

    select
        c.as_of_date, c.market, p.macro_category,
        count(*) as n_products, min(c.price_local) as min_price, max(c.price_local) as max_price
    from {{ ref('fct_catalogue_as_of') }} c
    inner join {{ ref('dim_product') }} p using (sku)
    where c.is_macro_date and c.has_price and p.is_in_macro_scope
    group by c.as_of_date, c.market, p.macro_category

),

macro_mismatch as (

    select
        'macro' as deliverable, cast(m.as_of_date as string) as as_of, m.market, m.macro_category as item,
        concat_ws('/', cast(m.n_products as string), cast(m.min_price as string), cast(m.max_price as string)),
        concat_ws('/', cast(r.n_products as string), cast(r.min_price as string), cast(r.max_price as string))
    from {{ ref('mart_macro__category_monthly') }} m
    full outer join macro_recomputed r
        on  r.as_of_date = m.as_of_date
        and r.market = m.market
        and r.macro_category = m.macro_category
    where m.n_products is null or r.n_products is null
       or m.n_products != r.n_products or m.min_price != r.min_price or m.max_price != r.max_price

)

select * from micro_mismatch
union all
select * from macro_mismatch
