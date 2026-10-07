-- =====================================================================================================
-- 03_load_answer_key.sql          run once after uploading data/_truth/*.csv to landing/_truth/
--
-- These tables are NOT pipeline sources. They are the generator's ground truth, used only by tests that
-- grade the QA layer ("did we catch every planted defect?") and check the planted business signal.
-- They are rebuilt from scratch each time (CREATE OR REPLACE) because they are reference data, not history.
--
-- CSV options: the files are written by Python's csv module, which escapes quotes by doubling them ("")
-- and may contain line breaks inside quoted fields (planted whitespace defects) -> escape + multiLine.
-- inferSchema off: everything arrives as STRING, we cast explicitly where it matters.
-- =====================================================================================================

CREATE OR REPLACE TABLE workspace.answer_key.defect_manifest AS
SELECT *
FROM read_files(
  '/Volumes/workspace/raw/landing/_truth/defect_manifest.csv',
  format => 'csv', header => true, multiLine => true, escape => '"', inferSchema => false
);

CREATE OR REPLACE TABLE workspace.answer_key.batch_manifest AS
SELECT *
FROM read_files(
  '/Volumes/workspace/raw/landing/_truth/batch_manifest.csv',
  format => 'csv', header => true, multiLine => true, escape => '"', inferSchema => false
);

CREATE OR REPLACE TABLE workspace.answer_key.product_master AS
SELECT *
FROM read_files(
  '/Volumes/workspace/raw/landing/_truth/product_master.csv',
  format => 'csv', header => true, escape => '"', inferSchema => false
);

CREATE OR REPLACE TABLE workspace.answer_key.price_changes AS
SELECT *
FROM read_files(
  '/Volumes/workspace/raw/landing/_truth/price_changes.csv',
  format => 'csv', header => true, escape => '"', inferSchema => false
);

-- hero_products.csv is NOT loaded here: it becomes a dbt seed (dbt/seeds/) in Phase 3,
-- because the Micro scope is business configuration that belongs in version control.
