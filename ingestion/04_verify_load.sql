-- =====================================================================================================
-- 04_verify_load.sql              run each query one by one and compare with the expected result
-- =====================================================================================================

-- [1] Row count per delivered file must equal what the generator wrote.  Expected: 0 rows returned.
WITH loaded AS (
  SELECT replace(source_file_name, '.gz', '') AS file_name, count(*) AS n_loaded
  FROM workspace.raw.crawl_lines
  GROUP BY 1
)
SELECT b.file_name, cast(b.n_rows AS INT) AS n_expected, l.n_loaded
FROM workspace.answer_key.batch_manifest b
FULL OUTER JOIN loaded l USING (file_name)
WHERE l.n_loaded IS NULL OR b.n_rows IS NULL OR cast(b.n_rows AS INT) != l.n_loaded;

-- [2] Overview: one row per file.  Expected: 15 files, 238,707 lines in total (seed 42).
SELECT source_file_name, count(*) AS n_lines, min(loaded_at) AS loaded_at
FROM workspace.raw.crawl_lines
GROUP BY source_file_name
ORDER BY source_file_name;

-- [3] Answer key size.  Expected: 11,883 rows (11,878 row-level + 5 batch-level).
SELECT defect_family, count(*) AS n
FROM workspace.answer_key.defect_manifest
GROUP BY defect_family
ORDER BY defect_family;

-- [4] First taste of schema-on-read: parse a few lines on the fly. Notice the different price formats.
SELECT
  source_file_name,
  raw_line:objectID::string                  AS object_id,
  raw_line:price.original_price::string      AS original_price_raw,
  raw_line:price.original_currency::string   AS currency_raw
FROM workspace.raw.crawl_lines
WHERE raw_line:price.original_price::string RLIKE '[^0-9]'     -- anything that is not just digits
LIMIT 20;

-- [5] Append-only proof.  Expected: an ERROR saying the table is append-only. That error is the point.
-- DELETE FROM workspace.raw.crawl_lines WHERE source_file_name LIKE '%(1)%';
