-- The publish rule, enforced: a delivery whose latest gate verdict is BLOCK must not be visible to BI,
-- unless a human forced the release (and wrote down why).
select *
from {{ ref('mart_data_health__deliveries') }}
where dataset = 'marts'
  and gate_decision = 'BLOCK'
  and is_published
  and not coalesce(is_forced_release, false)
