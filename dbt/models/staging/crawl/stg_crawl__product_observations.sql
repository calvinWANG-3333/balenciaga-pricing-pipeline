{#
  stg_crawl__product_observations
  -------------------------------
  Grain   : one row per delivered crawl line (crawl_line_id) - exactly as many rows as the source.
            Nothing is filtered out here: a bad row is FLAGGED (dq_issues / dq_status), never dropped.
            Dropping or quarantining is decided downstream, where it can be counted and tested.
  An "observation" = one product, seen in one market, in one delivered crawl file.

  What happens here (and only here):
    1. parse     - price text -> number, epoch -> timestamp, "true" -> boolean
    2. repair    - deterministic fixes; the raw value always stays next to the repaired one
    3. flag      - every rule that fired is listed in dq_issues; dq_status = worst handling
  What does NOT happen here: joins, deduplication, categorization, choosing which crawl to trust.

  Materialization: table, overriding the staging default (view). This model parses ~240k JSON
  lines with regexes and is read by several downstream models; as a view that work would be
  repeated on every read.
#}

{{ config(materialized='table') }}

{% set mojibake_pattern = "'[\\\\x{00C2}-\\\\x{00C3}][\\\\x{0080}-\\\\x{00BF}]|[\\\\x{00E4}-\\\\x{00E9}][\\\\x{0080}-\\\\x{00BF}]{2}'" %}

with base as (

    select * from {{ ref('base_crawl__lines') }}

),

-- 1. identity + market ----------------------------------------------------------------------------
identified as (

    select
        *,
        coalesce(
            nullif(trim(market_raw), ''),
            regexp_extract(source_raw, '_([A-Z]{3})$', 1)              -- source = Balenciaga_USA
        )                                                                as market,
        try_element_at(skus_raw, 1)                                      as sku_primary_raw,
        try_element_at(skus_raw, 2)                                      as sku_secondary
    from base

),

with_sku as (

    select
        *,
        nullif(upper(regexp_replace(sku_primary_raw, '[\\s\\-]', '')), '')              as sku_from_list,
        nullif(upper(regexp_replace(
            regexp_extract(object_id_raw, '^[^_]+_[A-Za-z]{3}_(.+)$', 1), '[\\s\\-]', '')), '')
                                                                                         as sku_from_object_id,
        {{ market_currency('market') }}                                                  as expected_currency
    from identified

),

-- 2. currency + price text ------------------------------------------------------------------------
currency as (

    select
        *,
        coalesce(sku_from_list, sku_from_object_id)                      as sku,
        case
            when upper(trim(original_currency_raw)) rlike '^[A-Z]{3}$' then upper(trim(original_currency_raw))
            else expected_currency          -- a symbol such as "$" is ambiguous on its own: trust the market
        end                                                              as currency_code,
        -- full-width (１２５０) and Arabic-Indic (١٢٥٠) digits -> ASCII
        translate(trim(original_price_raw), '０１２３４５６７８９٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
                                                                         as price_text_ascii
    from with_sku

),

price_text as (

    select
        *,
        {{ currency_minor_units('currency_code') }}                      as currency_minor_units,
        regexp_replace(price_text_ascii, '[^0-9.,]', '')                 as price_digits,
        case
            when original_price_raw is null                                   then 'missing'
            when price_text_ascii rlike '(?i)request|demande|咨询'             then 'on_request'
            when price_text_ascii rlike '(?i)from|partir|\\d\\s*[-–]\\s*\\d'   then 'from_or_range'
            when regexp_replace(price_text_ascii, '[^0-9]', '') = ''          then 'no_digits'
            else 'numeric'
        end                                                              as price_text_class
    from currency

),

separators as (

    select
        *,
        length(price_digits) - length(replace(price_digits, '.', ''))   as n_dots,
        length(price_digits) - length(replace(price_digits, ',', ''))   as n_commas
    from price_text

),

-- 3. price parsing: decide what "." and "," mean ---------------------------------------------------
--    both present      -> the LAST one is the decimal mark          1,250.00 | 1.250,00
--    only commas       -> groups of 3 = thousands, else decimal      1,250   | 1250,5
--    only one dot      -> 3 digits after it = thousands (unless the currency has 3 decimals), else decimal
price_parsed as (

    select
        *,
        case
            when price_text_class != 'numeric' then null
            when n_dots > 0 and n_commas > 0 then
                case when instr(reverse(price_digits), '.') < instr(reverse(price_digits), ',')
                     then replace(price_digits, ',', '')
                     else replace(replace(price_digits, '.', ''), ',', '.')
                end
            when n_commas > 0 then
                case when price_digits rlike '^\\d{1,3}(,\\d{3})+$'               then replace(price_digits, ',', '')
                     when n_commas = 1 and price_digits rlike ',\\d{1,2}$'        then replace(price_digits, ',', '.')
                end
            when n_dots > 1 then
                case when price_digits rlike '^\\d{1,3}(\\.\\d{3})+$' then replace(price_digits, '.', '') end
            when n_dots = 1 then
                case when price_digits rlike '\\.\\d{3}$' and currency_minor_units != 3 then replace(price_digits, '.', '')
                     when price_digits rlike '\\.\\d{1,2}$'                              then price_digits
                end
            else price_digits
        end                                                              as price_normalized_text
    from separators

),

priced as (

    select
        *,
        try_cast(price_normalized_text as decimal(18, 2))                as price_local,
        case
            when price_text_class = 'on_request'                         then 'price_on_request'
            when price_text_class = 'from_or_range'                      then 'price_from_or_range'
            when price_text_class in ('missing', 'no_digits')            then 'price_unparseable'
            when try_cast(price_normalized_text as decimal(18, 2)) is null then
                case when n_dots = 1 and price_digits rlike '\\.\\d{3}$' then 'price_ambiguous_separator'
                     else 'price_unparseable' end
            when try_cast(price_normalized_text as decimal(18, 2)) = 0
              or price_digits rlike '^9{6,}$'                            then 'price_placeholder'
            when price_text_ascii != trim(original_price_raw)            then 'price_non_ascii_digits'
            when price_text_ascii rlike '[^0-9.,\\s\\x{00A0}\\x{202F}]'  then 'price_currency_symbol'
            when (n_dots > 0 and n_commas > 0
                  and instr(reverse(price_digits), ',') < instr(reverse(price_digits), '.'))
              or (n_dots = 0 and n_commas = 1 and price_digits rlike ',\\d{1,2}$')
                                                                         then 'price_eu_decimal_format'
            when n_commas > 0                                            then 'price_us_thousands_separator'
            when n_dots = 1 and price_digits rlike '\\.\\d{3}$'          then 'price_dot_thousands_ambiguous'
            when n_dots >= 1                                             then 'price_trailing_decimals'
        end                                                              as price_issue
    from price_parsed

),

-- 4. text, categories, timestamps, validity --------------------------------------------------------
cleaned as (

    select
        *,
        -- names: decode the HTML entities crawlers leak, then collapse every kind of whitespace
        replace(replace(replace(replace(replace(product_name_raw,
            '&amp;', '&'), '&nbsp;', ' '), '&#39;', ''''), '&quot;', '"'), '&#124;', '|')
                                                                         as product_name_unescaped,
        transform(categories_raw, c -> {{ repair_mojibake('c') }})        as categories,
        transform_values(product_details_raw, (k, v) -> {{ repair_mojibake('v') }})
                                                                         as product_details,
        exists(categories_raw, c -> c rlike {{ mojibake_pattern }})
          or exists(map_values(product_details_raw), v -> v rlike {{ mojibake_pattern }})
                                                                         as had_mojibake,
        try_cast(created_at_raw as bigint)                               as created_at_number,
        try_cast(http_status_raw as int)                                 as http_status,
        case lower(trim(is_valid_raw)) when 'true' then true when 'false' then false end
                                                                         as is_valid,
        coalesce(validation_errors_raw, array())                         as validation_errors
    from priced

),

shaped as (

    select
        *,
        nullif(trim(regexp_replace(product_name_unescaped, '[\\s\\x{00A0}\\x{202F}]+', ' ')), '')
                                                                         as product_name,
        -- epoch SECONDS (10 digits) vs MILLISECONDS (13 digits)
        timestamp_millis(case when created_at_number < 100000000000 then created_at_number * 1000
                              else created_at_number end)                as crawled_at,
        concat_ws('_', '{{ var("brand_slug") }}', market, sku)           as object_id,
        coalesce(
            try_element_at(product_details, 'macroCategory'),
            nullif(array_join(filter(categories, c -> lower(c) like 'bal_macro%'), '|'), '')
        )                                                                as brand_macro_category_raw,
        coalesce(
            try_element_at(product_details, 'microCategory'),
            try_element_at(filter(categories, c -> lower(c) rlike '^bal?_micro_'), 1)
        )                                                                as brand_micro_category_raw,
        coalesce(
            try_element_at(product_details, 'superMicroCategory'),
            try_element_at(filter(categories, c -> lower(c) rlike '^bal?_super_micro_'), 1)
        )                                                                as brand_super_micro_category_raw
    from cleaned

),

-- 5. within-file duplicates (a window is not a join: still one row in, one row out) --------------
with_duplicates as (

    select
        *,
        size(collect_set(xxhash64(raw_line)) over (partition by source_file_name, object_id)) > 1
                                                                         as has_conflicting_duplicate
    from shaped

),

-- 6. every rule that fired ------------------------------------------------------------------------
flagged as (

    select
        *,
        filter(array(
            price_issue,
            case when raw_line rlike '"original_price":\\s*-?[0-9]'       then 'price_numeric_type_drift' end,
            case when price_minor_units_raw is null                       then 'missing_price_value' end,
            case when original_currency_raw is not null
                  and original_currency_raw != currency_code              then 'currency_code_notation' end,
            case when currency_code != expected_currency                  then 'currency_market_mismatch' end,
            case when product_name_raw rlike '&(amp|nbsp|quot|#\\d+);'    then 'name_html_entity' end,
            case when product_name is not null
                  and product_name_unescaped != product_name              then 'name_whitespace_noise' end,
            case when product_name is null                                then 'name_missing' end,
            case when (crawler_name = 'BalenciagaChina'
                       and product_name = upper(product_name) and product_name rlike '[A-Z].*[A-Z]')
                   or (crawler_name != 'BalenciagaChina' and product_name != lower(product_name))
                                                                          then 'name_case_drift' end,
            case when had_mojibake                                        then 'category_mojibake' end,
            case when sku_primary_raw is not null
                  and sku_primary_raw != coalesce(sku_from_list, '')      then 'sku_format_variant' end,
            case when sku_from_list is null and sku_from_object_id is not null
                                                                          then 'sku_recovered_from_object_id' end,
            case when nullif(trim(market_raw), '') is null                then 'market_recovered_from_source' end,
            case when created_at_number < 100000000000                    then 'timestamp_epoch_seconds' end,
            case when raw_line rlike '"isValid":\\s*"'                    then 'is_valid_as_string' end,
            case when nullif(trim(product_url_raw), '') is null           then 'url_missing' end,
            case when nullif(trim(preview_url_raw), '') is null           then 'preview_url_missing' end,
            case when identical_line_ordinal > 1                          then 'exact_duplicate_line' end,
            case when has_conflicting_duplicate                           then 'conflicting_duplicate' end,
            case when sku rlike '^(GIFTCARD|TEST)'
                   or lower(product_name) rlike 'gift card|test product'  then 'non_product_page' end,
            case when http_status != 200 or is_valid = false              then 'http_error_or_invalid' end,
            case when size(validation_errors) > 0 and is_valid = true     then 'is_valid_contradiction' end
        ), x -> x is not null)                                           as dq_issues
    from with_duplicates

)

select
    -- keys
    crawl_line_id,
    object_id,
    sku,
    sku_secondary,
    market,

    -- delivery
    source_file_name,
    delivered_file_name,
    file_crawl_date,
    file_exported_at,
    file_name_has_copy_suffix,
    loaded_at,
    crawled_at,

    -- product
    product_name,
    lower(product_name)                                                  as product_name_normalized,
    nullif(trim(product_url_raw), '')                                    as product_url,
    nullif(trim(preview_url_raw), '')                                    as preview_url,

    -- price
    price_local,
    currency_code,
    expected_currency,

    -- brand-side category labels (raw, localized - harmonized later in intermediate)
    {{ normalize_brand_tag('brand_macro_category_raw') }}                 as brand_macro_category,
    {{ normalize_brand_tag('brand_micro_category_raw') }}                 as brand_micro_category,
    {{ normalize_brand_tag('brand_super_micro_category_raw') }}           as brand_super_micro_category,
    coalesce(try_element_at(product_details, 'topCategory'), try_element_at(categories, 1))
                                                                         as top_category_label,
    coalesce(try_element_at(product_details, 'category'), try_element_at(categories, 2))
                                                                         as category_label,
    try_element_at(product_details, 'productCategory')                   as product_category_label,
    try_element_at(product_details, 'subCategory')                       as sub_category_label,
    try_element_at(product_details, 'color')                             as color,
    try_element_at(product_details, 'colorId')                           as color_id,
    try_element_at(product_details, 'collection')                        as collection,
    try_element_at(product_details, 'stock')                             as stock_status,
    categories,

    -- crawler metadata
    source_raw                                                           as source_name,
    crawler_name,
    import_source,
    http_status,
    is_valid,
    validation_errors,

    -- raw values kept for audit (lineage of every repair)
    object_id_raw,
    product_name_raw,
    original_price_raw,
    original_currency_raw,
    price_minor_units_raw,
    created_at_raw,

    -- data quality
    price_issue                                                          as price_parse_issue,
    dq_issues,
    {{ dq_status('dq_issues') }}                                         as dq_status

from flagged
