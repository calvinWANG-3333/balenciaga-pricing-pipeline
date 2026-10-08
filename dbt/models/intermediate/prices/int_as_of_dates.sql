{#
  int_as_of_dates
  ---------------
  Grain   : one row per reporting date ("as-of date").
  Purpose : the moments at which a deliverable is produced.
    micro  the day after every crawl (crawls run on Monday, the weekly Micro delivery goes out Tuesday)
    macro  the last day of every month that has crawls (monthly Macro delivery)
  A date can serve both scopes; deliverables read the catalogue "as it was known at the END of that day".
#}

with crawl_dates as (

    select distinct content_crawl_date as crawl_date
    from {{ ref('int_deliveries__profiled') }}
    where is_trusted

),

micro as (

    select date_add(crawl_date, 1) as as_of_date, true as is_micro_date, false as is_macro_date
    from crawl_dates

),

macro as (

    select distinct last_day(crawl_date) as as_of_date, false as is_micro_date, true as is_macro_date
    from crawl_dates

),

unioned as (

    select * from micro
    union all
    select * from macro

)

select
    as_of_date,
    bool_or(is_micro_date)                                               as is_micro_date,
    bool_or(is_macro_date)                                               as is_macro_date,
    -- "known at the end of that day": anything delivered before midnight counts
    to_timestamp(date_add(as_of_date, 1))                                as knowledge_cutoff
from unioned
group by as_of_date
