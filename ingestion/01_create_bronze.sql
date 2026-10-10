-- =====================================================================================================
-- 01_create_bronze.sql            run once, in the Databricks SQL Editor
--
-- Creates the bronze table that holds every crawl line ever delivered, exactly as delivered.
-- Two design decisions (explained in docs/03_bronze_ingestion.md):
--   1. each NDJSON line is stored as raw TEXT, not parsed  -> schema-on-read, nothing lost, drift-proof
--   2. delta.appendOnly = true                            -> UPDATE / DELETE are refused by the storage
--                                                            layer itself: the "never overwrite" rule
--                                                            is enforced, not just promised
-- =====================================================================================================

CREATE SCHEMA IF NOT EXISTS workspace.raw
  COMMENT 'Bronze: raw data exactly as delivered, append-only. Loaded by COPY INTO, not by dbt.';

CREATE VOLUME IF NOT EXISTS workspace.raw.landing
  COMMENT 'Landing zone: crawler files are dropped here before loading';

CREATE TABLE IF NOT EXISTS workspace.raw.crawl_lines (
  raw_line                STRING    COMMENT 'One NDJSON line exactly as delivered by the crawler (never edited)',
  source_file_path        STRING    COMMENT 'Full volume path of the delivered file',
  source_file_name        STRING    COMMENT 'File name, e.g. <source>_2026-08-31_1788173725123_balenciaga.ndjson.gz',
  source_file_size        BIGINT    COMMENT 'Compressed file size in bytes',
  source_file_modified_at TIMESTAMP COMMENT 'Last-modified time of the file in the volume (= upload time)',
  loaded_at               TIMESTAMP COMMENT 'When COPY INTO loaded this file into bronze'
)
COMMENT 'Bronze: every crawl line ever delivered. Append-only. One row per line per delivered file.'
TBLPROPERTIES ('delta.appendOnly' = 'true');

-- The generator's answer key lives in its own schema, so nobody mistakes it for a production source.
CREATE SCHEMA IF NOT EXISTS workspace.answer_key
  COMMENT 'Ground truth written by the synthetic data generator. Exists only because the data is synthetic; used to grade the QA layer.';
