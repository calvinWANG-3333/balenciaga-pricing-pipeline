-- =====================================================================================================
-- 02_load_crawl_files.sql         run after every upload of new crawl files - safe to re-run any time
--
-- COPY INTO keeps a log of the file paths it has already loaded into this table and silently skips them.
-- Re-running this statement therefore never creates duplicates of a file it has seen.
--
-- What it does NOT protect against: the SAME content arriving under a DIFFERENT file name
-- (the "... (1).ndjson.gz" copy, or an old crawl re-exported under a new date). Path-based
-- idempotency cannot see content - that is the dbt layer's job (Phase 2).
-- =====================================================================================================

COPY INTO workspace.raw.crawl_lines
FROM (
  SELECT
    value                              AS raw_line,               -- the TEXT reader puts each line in `value`
    _metadata.file_path                AS source_file_path,
    _metadata.file_name                AS source_file_name,
    _metadata.file_size                AS source_file_size,
    _metadata.file_modification_time   AS source_file_modified_at,
    current_timestamp()                AS loaded_at
  FROM '/Volumes/workspace/raw/landing/balenciaga/'
)
FILEFORMAT = TEXT
PATTERN = '*.ndjson.gz';

-- Expected first run : num_affected_rows = 238707 (seed 42), num_inserted_rows = 238707
-- Expected re-run    : num_affected_rows = 0
