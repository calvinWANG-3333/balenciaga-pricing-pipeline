{#
  qa_raw__file_profile
  --------------------
  Grain   : one row per delivered file.
  Purpose : the human-facing view of the delivery checks. The logic lives in int_deliveries__profiled
            (the pipeline uses it to decide which deliveries to trust); this model exposes it in the
            quality schema next to the other QA tables.
#}

select * from {{ ref('int_deliveries__profiled') }}
