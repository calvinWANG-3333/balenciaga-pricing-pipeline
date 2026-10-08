{#
  qa_answer_key__recall
  ---------------------
  Grain   : one row per planted defect code (A01 ... G04, F01 ... F04).
  Purpose : grade the QA layer against the generator's answer key.
            recall              = share of planted defects the pipeline flagged with the right rule
            handled_as_expected = share where our handling (fix / warn / quarantine / block) equals the
                                  handling the answer key expects
  Only exists because the data is synthetic. In production you cannot know what you missed;
  here we can, so we measure it.

  Matching: the bronze layer has no line numbers, so a planted row-level defect is matched on
  (file, objectID as delivered) and must carry the mapped dq reason.
#}

with code_map as (

    -- generator code -> the staging rule (or file check) that should catch it
    select * from values
        ('A01_us_thousands_separator',   'price_us_thousands_separator',   2),
        ('A02_eu_decimal_format',        'price_eu_decimal_format',        2),
        ('A03_currency_symbol_in_price', 'price_currency_symbol',          2),
        ('A04_trailing_decimals',        'price_trailing_decimals',        2),
        ('A05_price_on_request',         'price_on_request',               2),
        ('A06_from_price',               'price_from_or_range',            2),
        ('A07_placeholder_price',        'price_placeholder',              2),
        ('A08_non_ascii_digits',         'price_non_ascii_digits',         2),
        ('A09_minor_units_leak',         'price_scale_outlier',            3),   -- needs price history (intermediate)
        ('A10_numeric_type_drift',       'price_numeric_type_drift',       2),
        ('A11_dot_thousands_ambiguous',  'price_dot_thousands_ambiguous',  2),
        ('B01_currency_code_notation',   'currency_code_notation',         2),
        ('B02_geo_redirect_currency',    'currency_market_mismatch',       2),
        ('C01_html_entity_in_name',      'name_html_entity',               2),
        ('C02_whitespace_noise',         'name_whitespace_noise',          2),
        ('C03_mojibake',                 'category_mojibake',              2),
        ('C04_missing_name',             'name_missing',                   2),
        ('C05_case_drift',               'name_case_drift',                2),
        ('D01_exact_duplicate_row',      'exact_duplicate_line',           2),
        ('D02_conflicting_duplicate',    'conflicting_duplicate',          2),
        ('D03_sku_format_variant',       'sku_format_variant',             2),
        ('D04_missing_sku',              'sku_recovered_from_object_id',   2),
        ('E01_missing_price_value',      'missing_price_value',            2),
        ('E02_null_url',                 'url_missing',                    2),
        ('E03_empty_preview_url',        'preview_url_missing',            2),
        ('E04_epoch_seconds_timestamp',  'timestamp_epoch_seconds',        2),
        ('E05_boolean_as_string',        'is_valid_as_string',             2),
        ('E06_missing_market_field',     'market_recovered_from_source',   2),
        ('G01_unit_scale_error',         'price_scale_outlier',            3),   -- needs price history (intermediate)
        ('G02_non_product_page',         'non_product_page',               2),
        ('G03_http_error_row',           'http_error_or_invalid',          2),
        ('G04_isvalid_contradiction',    'is_valid_contradiction',         2),
        ('F01_duplicate_file',           'file:duplicate_content',         2),
        ('F02_stale_reimport',           'file:stale_content',             2),
        ('F03_partial_crawl',            'file:partial_market',            2),
        ('F04_missing_market',           'file:missing_market',            2)
        as t(defect_code, dq_reason, expected_phase)

),

reason_handling as (

    select * from values
    {%- for reason, handling in var('dq_reasons').items() %}
        ('{{ reason }}', '{{ handling }}'),
    {%- endfor %}
        ('file:duplicate_content', 'block'),
        ('file:stale_content',     'block'),
        ('file:partial_market',    'warn'),
        ('file:missing_market',    'warn')
        as t(dq_reason, our_handling)

),

manifest as (

    select
        m.*,
        c.dq_reason,
        c.expected_phase
    from {{ source('answer_key', 'defect_manifest') }} m
    left join code_map c using (defect_code)
    -- a planted "defect" whose dirty value equals the clean value changed nothing (e.g. lower-casing
    -- an all-digit SKU): it is not a defect, so it is not graded
    where m.line_number is null
       or coalesce(m.clean_value, '') != coalesce(m.dirty_value, '')

),

observations as (

    -- staging rules + the history-based check of the intermediate layer, per delivered line
    select
        regexp_replace(s.delivered_file_name, '\\.gz$', '')              as file_name,
        s.object_id_raw,
        case when c.is_price_scale_outlier
             then array_union(s.dq_issues, array('price_scale_outlier'))
             else s.dq_issues
        end                                                              as dq_issues
    from {{ ref('stg_crawl__product_observations') }} s
    left join {{ ref('int_observations__classified') }} c using (crawl_line_id)

),

files as (

    select
        regexp_replace(delivered_file_name, '\\.gz$', '')                as file_name,
        is_duplicate_content,
        is_stale_content,
        partial_markets,
        missing_markets
    from {{ ref('qa_raw__file_profile') }}

),

row_level as (

    select
        m.defect_code,
        m.expected_handling,
        m.dq_reason,
        m.expected_phase,
        exists_flag.detected
    from manifest m
    left join (
        select distinct
            m2.file_name,
            m2.line_number,
            m2.defect_code,
            true as detected
        from manifest m2
        inner join observations o
            on  o.file_name = m2.file_name
            and o.object_id_raw = m2.object_id
            and array_contains(o.dq_issues, m2.dq_reason)
        where m2.line_number is not null
    ) exists_flag
        on  exists_flag.file_name = m.file_name
        and exists_flag.line_number = m.line_number
        and exists_flag.defect_code = m.defect_code
    where m.line_number is not null

),

batch_level as (

    select
        m.defect_code,
        m.expected_handling,
        m.dq_reason,
        m.expected_phase,
        case m.dq_reason
            when 'file:duplicate_content' then f.is_duplicate_content
            when 'file:stale_content'     then f.is_stale_content
            when 'file:partial_market'    then array_contains(f.partial_markets, m.field)
            when 'file:missing_market'    then array_contains(f.missing_markets, m.field)
        end                                                              as detected
    from manifest m
    left join files f on f.file_name = m.file_name
    where m.line_number is null

),

graded as (

    select * from row_level
    union all
    select * from batch_level

)

select
    g.defect_code,
    substr(g.defect_code, 1, 1)                                          as defect_family,
    g.dq_reason                                                          as caught_by_rule,
    g.expected_phase,
    any_value(g.expected_handling)                                       as expected_handling,
    any_value(h.our_handling)                                            as our_handling,
    count(*)                                                             as n_planted,
    count_if(coalesce(g.detected, false))                                as n_detected,
    round(count_if(coalesce(g.detected, false)) / count(*), 4)           as recall,
    any_value(h.our_handling) = any_value(g.expected_handling)           as handled_as_expected
from graded g
left join reason_handling h using (dq_reason)
group by g.defect_code, g.dq_reason, g.expected_phase
