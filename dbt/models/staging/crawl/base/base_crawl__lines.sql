{#
  base_crawl__lines
  -----------------
  Grain   : one row per delivered line (identical to the source - nothing added, nothing removed).
  Purpose : give every line a stable id and pull every JSON field out as TEXT. No cleaning, no
            casting decisions, no filtering - those belong to stg_crawl__product_observations.

  Why a separate "base" model? The staging model below is long; splitting extraction from
  cleaning keeps each one readable, and lets the unit tests feed the cleaning logic hand-written rows.

  get_json_object() returns every scalar as a STRING, whether the JSON held "2490" or 2490. That is
  what we want: types are decided later, deliberately, not guessed here.
#}

with source as (

    select * from {{ source('crawl', 'crawl_lines') }}

),

numbered as (

    select
        *,
        -- identical lines can be delivered twice in the same file; number them so each row gets its own id
        row_number() over (
            partition by source_file_name, raw_line
            order by loaded_at
        ) as identical_line_ordinal
    from source

)

select
    sha2(concat_ws('|', source_file_name, raw_line, cast(identical_line_ordinal as string)), 256)
                                                                    as crawl_line_id,

    -- delivery (file) attributes ---------------------------------------------------------------
    source_file_name,                                               -- as captured by COPY INTO (join key)
    url_decode(source_file_name)                                    as delivered_file_name,  -- %20 -> space
    source_file_path,
    source_file_size,
    loaded_at,
    -- file names look like ALT_<crawl date>_<export epoch ms>_balenciaga[ (n)].ndjson.gz
    try_cast(regexp_extract(source_file_name, '^[A-Za-z]+_(\\d{4}-\\d{2}-\\d{2})_', 1) as date)
                                                                    as file_crawl_date,
    timestamp_millis(try_cast(regexp_extract(source_file_name, '_(\\d{13})_', 1) as bigint))
                                                                    as file_exported_at,
    url_decode(source_file_name) rlike ' \\(\\d+\\)\\.'             as file_name_has_copy_suffix,
    identical_line_ordinal,

    -- the payload, every field as text ------------------------------------------------------------
    raw_line,
    get_json_object(raw_line, '$.objectID')                         as object_id_raw,
    get_json_object(raw_line, '$.brandId')                          as brand_id_raw,
    get_json_object(raw_line, '$.name')                             as product_name_raw,
    get_json_object(raw_line, '$.url')                              as product_url_raw,
    get_json_object(raw_line, '$.previewUrl')                       as preview_url_raw,
    get_json_object(raw_line, '$.price.original_price')             as original_price_raw,
    get_json_object(raw_line, '$.price.original_currency')          as original_currency_raw,
    get_json_object(raw_line, '$.price.price')                      as price_minor_units_raw,
    get_json_object(raw_line, '$.price.currency')                   as price_currency_label_raw,
    get_json_object(raw_line, '$.status')                           as http_status_raw,
    get_json_object(raw_line, '$.source')                           as source_raw,
    get_json_object(raw_line, '$.market')                           as market_raw,
    get_json_object(raw_line, '$.crawlerName')                      as crawler_name,
    get_json_object(raw_line, '$.importSource')                     as import_source,
    get_json_object(raw_line, '$.createdAt')                        as created_at_raw,
    get_json_object(raw_line, '$.isValid')                          as is_valid_raw,
    from_json(get_json_object(raw_line, '$.skus'), 'array<string>')               as skus_raw,
    from_json(get_json_object(raw_line, '$.categories'), 'array<string>')         as categories_raw,
    from_json(get_json_object(raw_line, '$.validationErrors'), 'array<string>')   as validation_errors_raw,
    map_from_entries(
        from_json(get_json_object(raw_line, '$.productDetails'), 'array<struct<key:string,value:string>>')
    )                                                               as product_details_raw

from numbered
