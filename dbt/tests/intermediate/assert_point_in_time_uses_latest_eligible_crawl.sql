-- For every reporting date and market, the catalogue must be built from the most recent ELIGIBLE crawl
-- (by crawl date) that had been delivered by the end of that day. Recomputed here independently with a
-- plain MAX, so a bug in the model's ranking logic cannot hide itself. Returns the disagreements.

with expected as (
    select
        d.as_of_date,
        b.market,
        max(b.crawl_date) as expected_crawl_date
    from {{ ref('int_as_of_dates') }} d
    inner join {{ ref('int_market_batches__assessed') }} b
        on  b.is_eligible
        and b.crawl_date <= d.as_of_date
        and b.delivered_at < d.knowledge_cutoff
    group by d.as_of_date, b.market
),

actual as (
    select as_of_date, market, max(presence_crawl_date) as actual_crawl_date, min(presence_crawl_date) as min_crawl_date
    from {{ ref('int_catalogue__as_of') }}
    group by as_of_date, market
)

select e.*, a.actual_crawl_date, a.min_crawl_date
from expected e
left join actual a using (as_of_date, market)
where a.actual_crawl_date is null
   or a.actual_crawl_date != e.expected_crawl_date
   or a.min_crawl_date != e.expected_crawl_date
