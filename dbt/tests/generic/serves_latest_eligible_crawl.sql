{#
  THE KILLER TEST
  ---------------
  "For every reporting date and market, the catalogue a deliverable reads must be built from the most
   recent ELIGIBLE crawl (by crawl date) that had been delivered by the end of that day."

  Returns one row per (date, market) where the catalogue served anything else - an older crawl, a
  blocked delivery, a half-finished crawl.

  It is applied to BOTH designs (see _intermediate__models.yml):
    int_catalogue__as_of            the new design  -> must return 0 rows       (normal test)
    int_legacy__catalogue_replayed  the old design  -> must return > 0 rows      (inverted thresholds)
  So every `dbt build` proves two things at once: the fix holds, and the very same check would have
  caught the production incident.

  The expected crawl is recomputed here with a plain MAX, independently of the model's own logic.
#}

{% test serves_latest_eligible_crawl(model, crawl_date_column) %}

with expected as (

    select
        d.as_of_date,
        b.market,
        max(b.crawl_date)                                                as expected_crawl_date
    from {{ ref('int_as_of_dates') }} d
    inner join {{ ref('int_market_batches__assessed') }} b
        on  b.is_eligible
        and b.crawl_date <= d.as_of_date
        and b.delivered_at < d.knowledge_cutoff
    group by d.as_of_date, b.market

),

served as (

    select
        as_of_date,
        market,
        min({{ crawl_date_column }})                                     as min_served_crawl_date,
        max({{ crawl_date_column }})                                     as max_served_crawl_date
    from {{ model }}
    group by as_of_date, market

)

select
    e.as_of_date,
    e.market,
    e.expected_crawl_date,
    s.min_served_crawl_date,
    s.max_served_crawl_date
from expected e
left join served s using (as_of_date, market)
where s.max_served_crawl_date is null
   or s.min_served_crawl_date != e.expected_crawl_date
   or s.max_served_crawl_date != e.expected_crawl_date

{% endtest %}
