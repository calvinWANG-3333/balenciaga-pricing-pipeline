-- Every defect the generator planted that this phase is responsible for must be caught by the
-- right rule AND handled the way the answer key expects. Returns the defect codes that fall short.
-- Codes marked expected_phase = 3 need price history and are graded once the intermediate layer exists.

select *
from {{ ref('qa_answer_key__recall') }}
where expected_phase <= 2
  and (n_detected < n_planted or not handled_as_expected)
