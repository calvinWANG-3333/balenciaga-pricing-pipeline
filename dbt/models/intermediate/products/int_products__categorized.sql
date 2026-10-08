{#
  int_products__categorized
  -------------------------
  Grain   : one row per product (SKU - the same SKU is sold in every market).
  Purpose : (1) one set of descriptive attributes per product, (2) its harmonized LY category.

  Attributes come from the most recent accepted observation on the international site (English
  labels, full productDetails); the China crawler only fills in products never seen elsewhere.

  Categorization is a small rule engine driven by the ly_category_rules seed:
    every rule that matches the product is a candidate -> the lowest priority number wins.
  Rules are data, not SQL: a merchandiser can change one CSV line in a pull request, and the test
  suite tells them what moved.
#}

{{ config(materialized='table') }}

with observations as (

    select * from {{ ref('int_observations__accepted') }}

),

rules as (

    select * from {{ ref('ly_category_rules') }}

),

tree as (

    select * from {{ ref('ly_category_tree') }}

),

ranked_observations as (

    select
        *,
        row_number() over (
            partition by sku
            order by case when crawler_name = 'BalenciagaInternational' then 0 else 1 end,
                     crawled_at desc,
                     market
        )                                                                as attribute_rank
    from observations

),

lifespan as (

    select
        sku,
        min(crawl_date)                                                  as first_seen_date,
        max(crawl_date)                                                  as last_seen_date,
        count(distinct market)                                           as n_markets_seen,
        count(*)                                                         as n_observations
    from observations
    group by sku

),

products as (

    select
        r.sku,
        r.product_name_normalized                                        as product_name,
        r.color,
        r.color_id,
        r.collection,
        r.brand_macro_category,
        r.brand_micro_category,
        r.brand_super_micro_category,
        l.first_seen_date,
        l.last_seen_date,
        l.n_markets_seen,
        l.n_observations
    from ranked_observations r
    inner join lifespan l using (sku)
    where r.attribute_rank = 1

),

rule_matches as (

    select
        p.sku,
        ru.rule_id,
        ru.priority,
        ru.match_field,
        ru.ly_category_code,
        row_number() over (partition by p.sku order by ru.priority)      as match_rank
    from products p
    inner join rules ru
        on  (ru.match_field = 'sku'                        and p.sku = ru.pattern)
        or  (ru.match_field = 'product_name'               and p.product_name rlike ru.pattern)
        or  (ru.match_field = 'brand_super_micro_category' and p.brand_super_micro_category rlike ru.pattern)
        or  (ru.match_field = 'brand_macro_category'       and p.brand_macro_category rlike ru.pattern)

)

select
    p.*,
    coalesce(m.ly_category_code, 'UNCATEGORIZED')                        as ly_category_code,
    t.ly_category_name,
    t.level_1                                                            as ly_level_1,
    t.level_2                                                            as ly_level_2,
    t.macro_category,
    m.rule_id                                                            as categorized_by_rule,
    m.match_field                                                        as categorized_on
from products p
left join rule_matches m
    on  m.sku = p.sku
    and m.match_rank = 1
left join tree t
    on  t.ly_category_code = coalesce(m.ly_category_code, 'UNCATEGORIZED')
