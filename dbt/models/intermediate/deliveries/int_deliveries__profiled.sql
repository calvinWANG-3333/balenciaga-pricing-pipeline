{#
  int_deliveries__profiled
  ------------------------
  Grain   : one row per delivered file.
  Purpose : decide, per delivery, whether it can be trusted - using batch-level checks that no single
            row can reveal. This is the gatekeeper every downstream model relies on.

    duplicate content  same lines as an earlier file under a different name ("... (1).ndjson")
                       -> COPY INTO loaded it because the PATH was new; the content is not.
    stale content      the newest crawl timestamp inside the file is days older than the date in its
                       name: an old crawl re-delivered as if it were new (the original incident)
    missing markets    a market expected in this crawl scope is absent
    partial markets    a market delivered far fewer rows than it usually does

  file_status: block (never used downstream) | warn (used, issue surfaced) | ok.

  Content fingerprint: sum of 64-bit hashes of every line. Order-independent, so the same lines in a
  different order still match; summed as DECIMAL(38,0) so it cannot overflow.

  Moved here from quality/raw in Phase 3: a model that DECIDES what the pipeline trusts is business
  logic and belongs to the intermediate layer; qa_raw__file_profile now only presents it.
#}

with observations as (

    select * from {{ ref('stg_crawl__product_observations') }}

),

base as (

    select crawl_line_id, raw_line from {{ ref('base_crawl__lines') }}

),

per_file as (

    select
        o.source_file_name,
        any_value(o.delivered_file_name)                                 as delivered_file_name,
        any_value(o.file_crawl_date)                                     as file_crawl_date,
        any_value(o.file_exported_at)                                    as file_exported_at,
        any_value(o.file_name_has_copy_suffix)                           as file_name_has_copy_suffix,
        min(o.loaded_at)                                                 as loaded_at,
        count(*)                                                         as n_lines,
        sort_array(collect_set(o.market))                                as markets,
        min(o.crawled_at)                                                as first_crawled_at,
        max(o.crawled_at)                                                as last_crawled_at,
        sum(cast(xxhash64(b.raw_line) as decimal(38, 0)))                as content_fingerprint
    from observations o
    inner join base b using (crawl_line_id)
    group by o.source_file_name

),

per_file_market as (

    select source_file_name, market, count(*) as n_lines
    from observations
    group by source_file_name, market

),

market_baseline as (

    -- the "usual" size of each market's crawl = median over every file that contains it
    select market, percentile_approx(n_lines, 0.5) as median_lines
    from per_file_market
    group by market

),

partial as (

    select
        f.source_file_name,
        sort_array(collect_list(f.market))                               as partial_markets
    from per_file_market f
    inner join market_baseline b using (market)
    where f.n_lines < b.median_lines * {{ var('partial_crawl_threshold') }}
    group by f.source_file_name

),

ranked as (

    select
        *,
        row_number() over (
            partition by content_fingerprint, n_lines
            order by file_name_has_copy_suffix, file_exported_at, source_file_name
        )                                                                as content_rank,
        first_value(delivered_file_name) over (
            partition by content_fingerprint, n_lines
            order by file_name_has_copy_suffix, file_exported_at, source_file_name
        )                                                                as first_file_with_same_content
    from per_file

),

checked as (

    select
        r.*,
        case when size(r.markets) > size(array({% for m in var('weekly_markets') %}'{{ m }}'{{ ',' if not loop.last }}{% endfor %}))
             then 'extended' else 'weekly' end                           as crawl_scope,
        r.content_rank > 1                                               as is_duplicate_content,
        datediff(r.file_crawl_date, to_date(r.last_crawled_at)) > {{ var('stale_file_tolerance_days') }}
                                                                         as is_stale_content,
        coalesce(p.partial_markets, array())                             as partial_markets
    from ranked r
    left join partial p using (source_file_name)

),

final as (

    select
        *,
        case
            when crawl_scope = 'weekly'
                then array_except(array({% for m in var('weekly_markets') %}'{{ m }}'{{ ',' if not loop.last }}{% endfor %}), markets)
            else array_except(array({% for m in var('market_currency').keys() %}'{{ m }}'{{ ',' if not loop.last }}{% endfor %}), markets)
        end                                                              as missing_markets
    from checked

)

select
    source_file_name,
    delivered_file_name,
    file_crawl_date,                                                     -- what the file NAME claims
    to_date(first_crawled_at)                                            as content_crawl_date, -- what the DATA says
    file_exported_at                                                     as delivered_at,
    loaded_at,
    crawl_scope,
    n_lines,
    size(markets)                                                        as n_markets,
    markets,
    first_crawled_at,
    last_crawled_at,
    content_fingerprint,
    is_duplicate_content,
    case when is_duplicate_content then first_file_with_same_content end as duplicate_of_file,
    is_stale_content,
    missing_markets,
    partial_markets,
    case
        when is_duplicate_content or is_stale_content                    then 'block'
        when size(missing_markets) > 0 or size(partial_markets) > 0      then 'warn'
        else 'ok'
    end                                                                  as file_status,
    not (is_duplicate_content or is_stale_content)                       as is_trusted
from final
