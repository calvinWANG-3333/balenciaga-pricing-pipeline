# 03 · Phase 1b – Loading the crawl files into bronze

**Goal of this phase:** the 15 crawl files sit in a Databricks table called `workspace.raw.crawl_lines`,
one row per line, exactly as delivered. Loading is **idempotent** (running it twice adds nothing) and the
table is **append-only** (it physically refuses deletes and updates).

**Time:** ~45 minutes. **Files:** `ingestion/01…04_*.sql`.

---

## 1. The big picture first

```
your Mac                         Databricks volume                      bronze table
data/raw/balenciaga/*.ndjson  →  /Volumes/workspace/raw/landing/   →  workspace.raw.crawl_lines
        (gzip)                         balenciaga/*.ndjson.gz             raw_line | source_file_* | loaded_at
data/_truth/*.csv             →        _truth/*.csv               →  workspace.answer_key.*
```

This is the **EL** of ELT: *Extract* (the crawler did it) and *Load* (move the bytes into the platform
untouched). There is no **T** (transformation) here at all – dbt does the T from Phase 2 onwards. Keeping the
two apart is the first architectural decision.

---

## 2. Four concepts, each in plain English first

### 2.1 Why load with `COPY INTO`

**Plain.** Picture a warehouse loading dock with a clerk and a logbook. Every crate that arrives is logged by
its shipping label. If a crate with a label already in the logbook turns up again, the clerk refuses it:
"already received". You can tell the clerk "check the dock" a hundred times – each crate goes on the shelf
exactly once.

**Term.** `COPY INTO` is an **idempotent** batch load: it keeps track of which *file paths* it has already
loaded into the target table and skips them on later runs. *Idempotent* = running it once or many times gives
the same result.

**Deeper – the options Databricks offers, and why this one:**

| Option | What it is | Fits us? |
|---|---|---|
| UI "Create table from file" | click-ops, one file → one new table | no: not repeatable, no history |
| **`COPY INTO`** | SQL statement, batch, remembers loaded files | **yes**: files arrive weekly, SQL only, idempotent |
| Auto Loader / Lakeflow pipelines | streaming file ingestion, scales to millions of files | overkill here; and Free Edition allows one active pipeline |

**The catch – and it is the heart of this project.** The clerk checks the *label*, not what is inside the
crate. Our generator delivers two traps:

- `ALT_2026-08-10_…_balenciaga (1).ndjson.gz` – a byte-identical copy with a new name (F01)
- `ALT_2026-09-15_…_balenciaga.ndjson.gz` – the 08-31 crawl re-exported under a new date (F02, the incident)

Both have new labels, so `COPY INTO` *will* load them. That is correct behaviour for a bronze layer – bronze
records what was delivered, not what is true. Deciding which delivery to trust is a **content** question,
answered in dbt (Phase 2–3).

### 2.2 Why each line is stored as raw text

**Plain.** When a parcel arrives you photograph it before opening it. If you open it and something breaks, you
still have the photo of what came in.

**Term.** **Schema-on-read**: bronze stores the payload as an untyped string; types are applied later, when
reading. The opposite, *schema-on-write*, parses and types at load time.

**Deeper.** If we let Databricks parse the JSON at load time, it would have to *guess* a type for
`original_price`. Our data contains `"2490"`, `2490` (a number), `"2.490"`, `"1 250,00"`, `"Sur demande"`.
A guessed type would either fail the whole load or silently turn the strange values into `NULL` – destroying
exactly the evidence the QA layer needs. As text, nothing is lost; Databricks can still read fields on the fly
with the `:` path syntax:

```sql
SELECT raw_line:price.original_price::string FROM workspace.raw.crawl_lines LIMIT 5;
```

### 2.3 Why `delta.appendOnly = true`

**Plain.** The original incident happened because anyone could wipe the shared whiteboard. This table is a
whiteboard on which you can only *add* lines – the eraser has been removed.

**Term.** A **Delta table property** that makes the storage layer reject `UPDATE` and `DELETE`.

**Deeper.** Most teams *promise* not to overwrite raw data. Here the promise is enforced by the platform, so
the fix does not depend on people remembering a rule. In an interview this turns "we agreed not to" into
"the system cannot".

### 2.4 Why file metadata is kept on every row

**Plain.** Every photographed parcel keeps its delivery slip.

**Term.** Databricks exposes a hidden `_metadata` column during reads (file path, name, size, modification
time). We copy it onto every row: this is **lineage** – for any number in any dashboard you can walk back to
the exact file and line it came from.

---

## 3. Step by step

### Step 1 – compress the files (Terminal, on your Mac)

```bash
cd ~/Documents/LY_data_pipeline_CV_project/balenciaga-pricing-pipeline
gzip -k data/raw/balenciaga/*.ndjson        # -k keeps the original .ndjson next to the .gz
ls -lh data/raw/balenciaga/*.gz             # 15 files, roughly 1-3 MB each
```

*Why:* ~330 MB becomes ~25 MB, so uploading is fast. Databricks decompresses `.gz` transparently.

### Step 2 – create the bronze objects

Databricks → **SQL Editor** → paste `ingestion/01_create_bronze.sql` → **Run all**.

Then **Catalog** → `workspace` → `raw`: you should see the table `crawl_lines` (empty) and the volume
`landing`; and a new schema `answer_key`.

### Step 3 – upload the files into the volume

Catalog → `workspace` → `raw` → `landing`:

1. **Create directory** `balenciaga`, open it, **Upload to this volume** → select the **15 `.gz` files**
   (not the `.ndjson` ones).
2. Back in `landing`, **Create directory** `_truth`, upload the 4 CSVs from `data/_truth/`:
   `defect_manifest.csv`, `batch_manifest.csv`, `product_master.csv`, `price_changes.csv`.

### Step 4 – load

SQL Editor → paste `ingestion/02_load_crawl_files.sql` → **Run**. The result shows `num_affected_rows` and
`num_inserted_rows` = **238,707**.

### Step 5 – prove idempotency

Run the same statement **again**. Result: `num_affected_rows = 0`. Every file was already in the logbook.

### Step 6 – load the answer key

Run `ingestion/03_load_answer_key.sql`.

### Step 7 – verify

Run the queries in `ingestion/04_verify_load.sql` **one at a time** and compare with the comments:

| Query | Expected |
|---|---|
| [1] row count per file vs generator | **0 rows** returned (every file complete) |
| [2] overview | 15 files, 238,707 lines |
| [3] answer key by family | A … G, 11,883 rows in total |
| [4] non-numeric prices | a mix of `1,250` / `1.250,00` / `$1,250` / `Sur demande` … |
| [5] the commented `DELETE` – uncomment it and run | **an error** saying the table is append-only |

### Step 8 – commit the ingestion code (Terminal)

Git workflow you will use for every phase from now on:

```bash
cd ~/Documents/LY_data_pipeline_CV_project/balenciaga-pricing-pipeline
git checkout main && git pull                     # get what Studio merged (the dbt/ folder)
git checkout -b phase-1/bronze-ingestion          # a branch for this phase
git add ingestion/ docs/
git commit -m "feat(ingestion): bronze table, idempotent COPY INTO, answer key"
git push -u origin phase-1/bronze-ingestion
gh pr create --fill                               # opens a pull request
gh pr merge --merge --delete-branch               # merge it (in a team: after a review)
git checkout main && git pull
```

**Checkpoint – Phase 1b is done when:**
- [ ] `workspace.raw.crawl_lines` holds 238,707 rows from 15 files
- [ ] re-running `COPY INTO` inserts 0 rows
- [ ] `DELETE` on `crawl_lines` fails with an append-only error
- [ ] `workspace.answer_key.defect_manifest` holds 11,883 rows
- [ ] the PR is merged and `main` contains `ingestion/`

---

## 4. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `num_inserted_rows = 0` on the first run | files uploaded as `.ndjson`, or into the wrong folder | check the path `/Volumes/workspace/raw/landing/balenciaga/` and the `.gz` suffix |
| `PATH_NOT_FOUND` | directory name typo (case-sensitive) | compare with Catalog → landing |
| query [1] returns rows | a file was cut off during upload | stop and send me the output – the bronze table cannot be "fixed" by deleting (that is the point), so a broken delivery is handled as a new delivery |
| `UNRESOLVED_COLUMN value` | the format is not TEXT | check `FILEFORMAT = TEXT` |
| answer-key counts are off by a few | a CSV field with a line break was split | make sure `multiLine => true` and `escape => '"'` are in the statement |

---

## 5. Interview lines

> "Bronze is append-only at the storage level – the Delta table property refuses updates and deletes – so the
> rule that caused our incident, overwriting a shared table, is now physically impossible rather than a
> convention."

> "I load with `COPY INTO`, which is idempotent by file path. I'm explicit about its limit: it can't detect the
> same content under a new file name. Content-level deduplication and choosing which delivery is authoritative
> are modelled in dbt, where they're tested."

> "Each line lands as raw text with its file metadata. Schema-on-read means a malformed price can't break the
> load or be silently nulled; it survives intact so staging can parse it, repair it, or quarantine it with the
> evidence attached."
