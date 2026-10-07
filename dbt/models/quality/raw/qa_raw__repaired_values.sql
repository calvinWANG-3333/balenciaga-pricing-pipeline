{#
  qa_raw__repaired_values
  -----------------------
  Grain   : one row per (crawl line, repair rule that fired) - a line repaired twice appears twice.
  Purpose : the audit trail of every automatic repair. For each one: the rule, the field it touched,
            the value as delivered and the value the pipeline now uses. If a repair rule is ever
            wrong, this table shows exactly which rows it touched.
#}

with observations as (

    select * from {{ ref('stg_crawl__product_observations') }}

),

base as (

    select
        crawl_line_id,
        identical_line_ordinal,
        market_raw,
        is_valid_raw,
        skus_raw,
        categories_raw
    from {{ ref('base_crawl__lines') }}

),

exploded as (

    select
        o.*,
        b.identical_line_ordinal,
        b.market_raw,
        b.is_valid_raw,
        b.skus_raw,
        b.categories_raw,
        explode(array_intersect(o.dq_issues, {{ dq_reasons_with_handling('fix') }})) as repair_rule
    from observations o
    inner join base b using (crawl_line_id)

)

select
    crawl_line_id,
    delivered_file_name,
    market,
    object_id,
    repair_rule,
    case
        when repair_rule = 'missing_price_value'          then 'price.price'
        when repair_rule like 'price_%'                   then 'price_local'
        when repair_rule like 'currency_%'                then 'currency_code'
        when repair_rule = 'name_case_drift'              then 'product_name_normalized'
        when repair_rule like 'name_%'                    then 'product_name'
        when repair_rule = 'category_mojibake'            then 'categories'
        when repair_rule like 'sku_%'                     then 'sku'
        when repair_rule = 'market_recovered_from_source' then 'market'
        when repair_rule = 'timestamp_epoch_seconds'      then 'crawled_at'
        when repair_rule = 'is_valid_as_string'           then 'is_valid'
        when repair_rule = 'exact_duplicate_line'         then '<whole line>'
    end                                                                       as repaired_field,
    case
        when repair_rule = 'missing_price_value'          then '<absent>'
        when repair_rule like 'price_%'                   then original_price_raw
        when repair_rule like 'currency_%'                then original_currency_raw
        when repair_rule = 'name_case_drift'              then product_name
        when repair_rule like 'name_%'                    then product_name_raw
        when repair_rule = 'category_mojibake'            then array_join(categories_raw, ' | ')
        when repair_rule = 'sku_format_variant'           then try_element_at(skus_raw, 1)
        when repair_rule = 'sku_recovered_from_object_id' then to_json(skus_raw)
        when repair_rule = 'market_recovered_from_source' then '<absent>'
        when repair_rule = 'timestamp_epoch_seconds'      then created_at_raw
        when repair_rule = 'is_valid_as_string'           then concat('"', is_valid_raw, '" (text)')
        when repair_rule = 'exact_duplicate_line'         then concat('identical copy #', identical_line_ordinal)
    end                                                                       as raw_value,
    case
        when repair_rule = 'missing_price_value'          then 'not needed: price.price is never used'
        when repair_rule like 'price_%'                   then cast(price_local as string)
        when repair_rule like 'currency_%'                then currency_code
        when repair_rule = 'name_case_drift'              then product_name_normalized
        when repair_rule like 'name_%'                    then product_name
        when repair_rule = 'category_mojibake'            then array_join(categories, ' | ')
        when repair_rule like 'sku_%'                     then sku
        when repair_rule = 'market_recovered_from_source' then concat(market, ' (from source ', source_name, ')')
        when repair_rule = 'timestamp_epoch_seconds'      then cast(crawled_at as string)
        when repair_rule = 'is_valid_as_string'           then cast(is_valid as string)
        when repair_rule = 'exact_duplicate_line'         then 'dropped by deduplication downstream'
    end                                                                       as repaired_value,
    dq_status                                                                 as final_row_status
from exploded
