-- Row conservation: nothing is silently dropped.
-- Every line delivered to bronze must end up EITHER usable (pass / fixed / warn) OR in the
-- quarantine model - and never both. Returns the files where the books do not balance.

with delivered as (
    select source_file_name, count(*) as n_delivered
    from {{ source('crawl', 'crawl_lines') }}
    group by source_file_name
),

usable as (
    select source_file_name, count(*) as n_usable
    from {{ ref('stg_crawl__product_observations') }}
    where dq_status != 'quarantine'
    group by source_file_name
),

quarantined as (
    select source_file_name, count(*) as n_quarantined
    from {{ ref('qa_raw__quarantined_lines') }}
    group by source_file_name
)

select
    d.source_file_name,
    d.n_delivered,
    coalesce(u.n_usable, 0)       as n_usable,
    coalesce(q.n_quarantined, 0)  as n_quarantined
from delivered d
left join usable u using (source_file_name)
left join quarantined q using (source_file_name)
where d.n_delivered != coalesce(u.n_usable, 0) + coalesce(q.n_quarantined, 0)
