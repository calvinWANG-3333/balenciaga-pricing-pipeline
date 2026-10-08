-- Every defect the generator planted must be caught by the right rule AND handled the way the
-- answer key expects. Returns the defect codes that fall short.
-- Row-level codes are caught in staging (phase 2); price-scale errors need price history and are
-- caught in the intermediate layer (phase 3).

select *
from {{ ref('qa_answer_key__recall') }}
where n_detected < n_planted or not handled_as_expected
