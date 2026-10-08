-- No row of the point-in-time catalogue may come from a blocked delivery, an incomplete market batch,
-- a crawl dated after the reporting date, or a file delivered after the end of that day.
-- (Look-ahead bias is the classic way a backfilled history lies.)

select c.*
from {{ ref('int_catalogue__as_of') }} c
inner join {{ ref('int_as_of_dates') }} d using (as_of_date)
left join {{ ref('int_market_batches__assessed') }} pb on pb.market_batch_id = c.presence_batch_id
left join {{ ref('int_market_batches__assessed') }} xb on xb.market_batch_id = c.price_batch_id
where not pb.is_eligible
   or c.presence_crawl_date > c.as_of_date
   or pb.delivered_at >= d.knowledge_cutoff
   or (c.has_price and (not xb.is_trusted_delivery
                        or c.price_crawl_date > c.as_of_date
                        or xb.delivered_at >= d.knowledge_cutoff))
