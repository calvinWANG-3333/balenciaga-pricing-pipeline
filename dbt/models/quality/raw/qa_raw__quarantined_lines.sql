{#
  qa_raw__quarantined_lines
  -------------------------
  Grain   : one row per quarantined crawl line.
  Purpose : the "isolation room". Every line the pipeline refuses to trust is listed here with the
            rule(s) that quarantined it and the untouched raw JSON as evidence. Marts never see these
            rows; a human (or the source owner) decides what to do with them.
  Reads staging + base on purpose - never the marts - so diagnostics keep full raw context.
#}

with observations as (

    select * from {{ ref('stg_crawl__product_observations') }}
    where dq_status = 'quarantine'

),

base as (

    select crawl_line_id, raw_line from {{ ref('base_crawl__lines') }}

)

select
    o.crawl_line_id,
    o.source_file_name,
    o.file_crawl_date,
    o.market,
    o.object_id,
    o.sku,
    o.product_name,
    array_intersect(o.dq_issues, {{ dq_reasons_with_handling('quarantine') }})  as quarantine_reasons,
    o.dq_issues                                                                   as all_issues,
    o.original_price_raw,
    o.original_currency_raw,
    o.expected_currency,
    o.price_local,
    o.http_status,
    o.is_valid,
    o.validation_errors,
    b.raw_line
from observations o
inner join base b using (crawl_line_id)
