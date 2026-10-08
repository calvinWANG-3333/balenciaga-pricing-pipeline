-- SCD2 integrity: for every object, price periods are ordered, non-empty and do not overlap, and exactly
-- one period (the last) is current.

with periods as (
    select
        object_id,
        valid_from,
        valid_to,
        is_current_period,
        lead(valid_from) over (partition by object_id order by valid_from) as next_valid_from
    from {{ ref('int_prices__historized') }}
),

current_count as (
    select object_id, count_if(is_current_period) as n_current
    from {{ ref('int_prices__historized') }}
    group by object_id
)

select p.object_id, p.valid_from, p.valid_to, 'overlap or empty period' as problem
from periods p
where p.valid_to is not null and (p.valid_to <= p.valid_from or p.valid_to != p.next_valid_from)
union all
select object_id, null, null, 'not exactly one current period'
from current_count
where n_current != 1
