{#
  metricflow_time_spine
  ---------------------
  Grain   : one row per calendar day.
  Purpose : required by the dbt semantic layer (MetricFlow): the calendar every metric's time
            dimension is aligned to. 2026-2027 covers the project's data with room to grow.
#}

{{ config(materialized='table') }}

select explode(sequence(date'2026-01-01', date'2027-12-31', interval 1 day)) as date_day
