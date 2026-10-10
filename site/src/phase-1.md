---
title: Phase 1 · Synthetic data + bronze
---

```js
import {chapterHead, lineageSection, pager} from "./components/chapter.js";
display(chapterHead("p1", "Before cleaning any data, I needed data I was allowed to show. I wrote a program that invents a luxury shop with realistic prices, mixes in the kinds of errors that real price-collecting robots make, and keeps a list of every error it planted. Then I loaded the files into the database exactly as they arrived, into a table that cannot erase or edit anything."));
```

<section class="block"><div class="label">01 Problem</div><div class="content">

I could not publish my former employer's data. Random fake data would teach nothing: a €40 Le City bag makes every
number downstream meaningless. Clean fake data would hide the real work, because real crawl files are dirty.

So I needed files that look and behave like a real price crawler's output, with known problems planted in them and a
list of each one. Later, the cleaning layer can be graded against that list.

Then the files had to land in the database. The original incident came from a shared table that every import wiped and
rewrote. The raw layer has to keep every delivery forever, change nothing, and survive the same load being run twice.

</div></section>

<section class="block"><div class="label">02 Decision</div><div class="content">

**Fake the shop, keep the numbers.** A Python generator invents about 2,000 products. Their prices are sampled from
real per-category price quantiles, measured on four real weekly crawls, then converted with the real price ladder
between countries. It plants defects and writes an answer key with the file and line of each one.

**Load untouched.** `COPY INTO` reads the files from a Unity Catalog volume into `workspace.raw.crawl_lines`: one row
per line, kept as raw text, with its file metadata. The table is append-only.

| Piece | Choice | Why |
|---|---|---|
| Calendar | 13 Monday crawls, 2026-07-06 to 2026-09-28 | 8 markets weekly, 16 on the last Monday of each month: the real cadence behind the incident |
| Signal | From 2026-09-07, about 85 % of bags and leather goods rise 5 to 8 % | The marts need something true to find |
| Dirt | 36 defect codes, each with a handling: fix, quarantine, warn or block | QA is graded against the answer key |
| Traps | A duplicate file (F01) and a stale re-import (F02) | F02 is the incident itself |

</div></section>

<section class="block"><div class="label">03 Rejected<span>The alternatives I considered, and why not.</span></div><div class="content">

| Alternative | Why not |
|---|---|
| Random fake prices | A €40 Le City bag makes every downstream number meaningless. Prices follow the real category distributions instead. |
| Create a table from the upload screen | One file becomes one new table. Not repeatable, and no history of what was loaded. |
| Auto Loader or Lakeflow pipelines | Built for streaming millions of files. Overkill for weekly batches, and Free Edition allows one active pipeline. |
| Parse the JSON on load | Databricks would have to guess a type for `original_price`, which arrives as `"2490"`, `2490`, `"1 250,00"` or `"Sur demande"`. A wrong guess fails the load or turns odd values into NULL, and destroys the evidence QA needs. |
| Skip files by hash at load | The stale re-import is not byte-identical, because the export touched `updatedAt`. A hash check lets it through. Only content logic catches it, and that logic lives in dbt. |

</div></section>

<section class="block"><div class="label">04 Tools and features<span>What each one does in this phase.</span></div><div class="content">

| Feature | What it does here |
|---|---|
| Python generator, `--seed 42` | Standard library only, about 30 s. `validate.py` runs 13 pass/fail checks, determinism included. |
| Unity Catalog volume | The landing zone. 15 gzipped crawl files (about 330 MB down to about 25 MB) plus the answer-key CSVs. |
| `COPY INTO` | Idempotent batch load: it remembers the file paths it has loaded and skips them on later runs. |
| `FILEFORMAT = TEXT` | Each line lands whole in one string column. Schema-on-read: types come later, in staging. |
| `_metadata` column | File path, name, size and modification time on every row. Any number traces back to its file. |
| `delta.appendOnly = true` | The storage layer refuses `UPDATE` and `DELETE`. The rule is enforced, so nobody has to remember it. |
| `read_files`, `answer_key` schema | The answer key loads into its own schema, so nobody mistakes it for a production source. |

```pgsql
-- ingestion/01_create_bronze.sql
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
```

</div></section>

```js
display(lineageSection("p1", null));
```

<section class="block"><div class="label">06 Proof<span>Reference run, synthetic data, seed 42.</span></div><div class="content">

<div class="versus">
  <div><span class="micro">First load</span><b>238,707</b><p>lines inserted from 15 files</p></div>
  <div><span class="micro">Same statement, run again</span><b>0</b><p>rows affected: every file was already in the log</p></div>
</div>

| Check | Result |
|---|--:|
| EUR reference price inside the real min–max of its category | 2,001 / 2,001 products |
| Clean local price inside the real category × market envelope | 188,946 / 188,946 rows |
| Files whose loaded row count differs from the generator's | 0 |
| Planted row-level defects | 11,866 (about 5 % of lines) |
| Planted batch-level defects | 5 |
| `DELETE` on `crawl_lines` | Error: the table is append-only |

<p class="cap">The 15 files are 13 crawls, 1 byte-identical duplicate and 1 stale re-import. COPY INTO loads both traps, as it should: they have new file names, and bronze records every delivery. Which delivery to trust is a content question, answered in dbt from Phase 2.</p>

</div></section>

```js
display(pager("p1"));
```
