{#
  dim_product
  -----------
  Grain   : one row per product (SKU; the same SKU is sold in every market).
  Purpose : who-is-what for every consumer (BI, agent, deliverables): name, harmonized category,
            the brand's own tags for traceability, lifespan, and whether a client tracks it (Micro).
#}

with products as (

    select * from {{ ref('int_products__categorized') }}

),

pointers as (

    select * from {{ ref('micro_pointers') }}

)

select
    cast(p.sku as string)                                                as sku,
    cast(p.product_name as string)                                       as product_name,
    cast(p.color as string)                                              as color,
    cast(p.collection as string)                                         as collection,
    cast(p.ly_category_code as string)                                   as ly_category_code,
    cast(p.ly_category_name as string)                                   as ly_category_name,
    cast(p.ly_level_1 as string)                                         as ly_level_1,
    cast(p.ly_level_2 as string)                                         as ly_level_2,
    cast(p.macro_category as string)                                     as macro_category,
    cast(p.macro_category is not null as boolean)                        as is_in_macro_scope,
    cast(p.categorized_by_rule as string)                                as categorized_by_rule,
    cast(p.brand_macro_category as string)                               as brand_macro_category,
    cast(p.brand_super_micro_category as string)                         as brand_super_micro_category,
    cast(p.first_seen_date as date)                                      as first_seen_date,
    cast(p.last_seen_date as date)                                       as last_seen_date,
    cast(p.n_markets_seen as int)                                        as n_markets_seen,
    cast(ptr.pointer_id is not null as boolean)                          as is_micro_pointer,
    cast(ptr.pointer_id as string)                                       as micro_pointer_id,
    cast(ptr.product_label as string)                                    as micro_product_label
from products p
left join pointers ptr using (sku)
