-- Products that fell through every categorization rule.
-- Severity warn: a new brand tag should be noticed (and a rule added to the seed) without blocking
-- the whole pipeline. They land in UNCATEGORIZED, which Macro excludes, so no metric is polluted.
{{ config(severity='warn') }}

select sku, product_name, brand_macro_category, brand_super_micro_category
from {{ ref('int_products__categorized') }}
where ly_category_code = 'UNCATEGORIZED'
