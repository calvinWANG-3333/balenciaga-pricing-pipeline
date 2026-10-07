# 01 · Phase 0 – Environment setup (GitHub + Databricks + dbt platform)

**Goal of this phase:** at the end you type `dbt run` in the dbt Studio IDE, and a new view appears inside
your Databricks workspace. Nothing about Balenciaga yet – this phase only proves the three tools can talk to
each other.

**Time:** ~1.5 hours. **Cost:** €0 (all three tools have free tiers).

> UI labels drift over time. If a button is named slightly differently from what is written here, look for
> the closest match; if you are stuck for more than 5 minutes, screenshot it and ask.

---

## 0.1 The mental model (read this first)

Keep using the restaurant analogy from the DataQuest notes:

| Plain (restaurant) | Term | Tool in this project |
|---|---|---|
| The building: cold room + kitchen | **Lakehouse** – storage and compute in one platform | **Databricks** |
| Labelled shelving: *building → room → shelf* | **Unity Catalog**, three-level name `catalog.schema.table` | `workspace.raw.crawl_lines` |
| The loading dock where crates are dropped before unpacking | **Volume** – a folder for raw files inside Unity Catalog | `/Volumes/workspace/raw/landing/` |
| The stove: off when idle, you pay while it burns | **SQL warehouse** – compute that runs SQL; *serverless* = starts in seconds | "Serverless Starter Warehouse" |
| The recipe book + the chef's workstation | **dbt project** + **Studio IDE** (browser editor) | dbt platform |
| The archive of every version of every recipe | **Git repository** | GitHub |
| The key card to enter the kitchen | **Personal access token (PAT)** – a password for programs | Databricks → Settings → Developer |

**Deeper – why three tools and not one?** Separation of concerns. Databricks *stores and computes*; dbt
*describes* the transformations as code; GitHub *versions* that code. In a company, the warehouse is shared,
the code is reviewed through pull requests, and dbt is the contract between them. Learning this split is the
point of the project.

---

## 0.2 GitHub – put the project under version control

**Plain.** Git is "track changes" for a whole folder. GitHub is the online copy of that history.

**In practice** (Terminal on your Mac):

```bash
# 1. tools (skip what you already have)
xcode-select --install          # installs git
brew install gh                 # GitHub's command-line tool (needs Homebrew: https://brew.sh)
gh auth login                   # choose: GitHub.com → HTTPS → login with a web browser

# 2. go to the project folder
cd ~/Documents/LY_data_pipeline_CV_project/balenciaga-pricing-pipeline

# 3. check what git WOULD track – data/ must NOT appear (it is in .gitignore)
git init -b main
git status

# 4. first commit + create the GitHub repo (PRIVATE for now) + push
git add .
git commit -m "chore: scaffold repo with synthetic data generator and docs"
gh repo create balenciaga-pricing-pipeline --private --source=. --push
```

> **Why private first?** `generator/calibration/category_profiles.json` is derived from your former
> employer's exports (aggregates only: price quantiles, label vocabularies, public product names). Your
> manager approved *keeping* the data; publishing a public repo is a different question. Ask before you flip
> the repo to public in Phase 6 (Settings → General → Danger zone → Change visibility).

**Checkpoint:** `https://github.com/<your-user>/balenciaga-pricing-pipeline` shows `generator/`, `docs/`,
`README.md` – and **no** `data/` folder.

---

## 0.3 Databricks Free Edition – the warehouse

1. Sign up: <https://login.databricks.com/?intent=CE_SIGN_UP> (Free Edition – **not** a paid trial, no cloud
   account needed). A workspace is created for you automatically.
2. Look around the left sidebar: **Catalog**, **SQL Editor**, **SQL Warehouses**.
3. Open **Catalog**. You should see a catalog (usually named `workspace`) containing a schema `default`.
4. Open **SQL Editor**, pick the warehouse in the top-right drop-down, and run:

```sql
-- where am I?
SELECT current_catalog(), current_schema();
SHOW CATALOGS;

-- bronze layer: raw data exactly as delivered (filled in Phase 1, not by dbt)
CREATE SCHEMA IF NOT EXISTS workspace.raw
  COMMENT 'Bronze: raw crawl lines exactly as delivered, append-only';

-- landing zone: the folder where crawl files are dropped
CREATE VOLUME IF NOT EXISTS workspace.raw.landing
  COMMENT 'Landing zone for crawler NDJSON files';
```

If `SHOW CATALOGS` shows a different name than `workspace`, replace `workspace` everywhere in these docs
with that name.

**Term – what you just made.** A *schema* (a shelf) and a *volume* (a crate area on that shelf). dbt will
create its own schemas later; `raw` is deliberately **not** managed by dbt because loading is the "EL" of
ELT, and dbt only does the "T".

**Free Edition limits that matter for us** (from Databricks' docs): serverless only; one SQL warehouse of
size 2X-Small; daily/monthly compute quotas (when exceeded, compute stops until the quota resets);
inactive accounts can be deleted; non-commercial use only. Our ~240k rows are tiny for this.

### Connection details + token

5. **SQL Warehouses** → click your warehouse → tab **Connection details**. Copy:
   - **Server hostname** – looks like `dbc-xxxxxxxx-xxxx.cloud.databricks.com`
   - **HTTP path** – looks like `/sql/1.0/warehouses/xxxxxxxxxxxxxxxx`
6. Top-right avatar → **Settings** → **Developer** → **Access tokens** → **Manage** → **Generate new token**.
   Comment `dbt platform – dev`, lifetime 90 days. **Copy the token now – it is shown only once.** Put it in
   your password manager, never in a file inside the repo.

> Databricks calls PATs "legacy" and recommends OAuth for companies. For a single-developer Free Edition
> workspace a PAT is the pragmatic choice; mention you know the difference in interviews.

**Checkpoint:** you have three values saved: hostname, HTTP path, token.

---

## 0.4 dbt platform – the transformation layer

1. Sign up at <https://www.getdbt.com/signup> → choose the free **Developer** plan (1 seat, Studio IDE, job
   scheduler, 1 project, 3,000 successful model builds per month – plenty for us).
2. Create a project named `balenciaga_pricing`.
3. **Connection** → choose **Databricks** (adapter `dbt-databricks`) and fill in:

   | Field | Value |
   |---|---|
   | Server Hostname | from step 0.3.5 |
   | HTTP Path | from step 0.3.5 |
   | Catalog | `workspace` |

4. **Development credentials** (yours only, used when you work in the IDE):

   | Field | Value |
   |---|---|
   | Auth method | Token |
   | Token | the PAT from step 0.3.6 |
   | Schema | `dbt_rwang` |

   Click **Test connection** → it must succeed.

   **Term – the development schema.** Every developer builds into their own schema (`dbt_rwang`), so your
   half-finished models never overwrite anyone else's – the exact disease this project cures, applied to
   developers. Production gets its own schemas later (Phase 6).

5. **Repository** → **GitHub** → authorize the dbt GitHub app (it asks GitHub for permission to read the
   repo) → pick `balenciaga-pricing-pipeline`.
6. **Project settings** → **Project subdirectory** → `dbt`. (Our repo also holds the generator, the agent and
   the BI site, so dbt lives in its own folder.)
7. **Release track / dbt version** → keep the default "Latest".

---

## 0.5 First run in the Studio IDE

1. Open **Studio IDE** (it takes a minute the first time).
2. **Create branch** → name it `phase-0/init-dbt`.
   *Plain:* a branch is a private copy of the recipe book; `main` stays clean until you merge.
3. Click **Initialize dbt project**. Studio creates `dbt_project.yml`, `models/example/…` etc. inside `dbt/`.
   (If it complains the folder is not empty or missing, tell me the exact message.)
4. In the command bar at the bottom type:

```bash
dbt debug       # checks the connection - every line should say OK
dbt run         # builds the two example models
```

5. Back in Databricks → **Catalog** → `workspace` → you should now see a schema **`dbt_rwang`** with
   `my_first_dbt_model` (a table) and `my_second_dbt_model` (a view).
6. In Studio: **Commit and sync** → message `chore(dbt): initialize project` → **Create pull request** →
   on GitHub click **Merge pull request** → back on your Mac run `git pull` so your local copy has `dbt/`.

**Checkpoint – Phase 0 is done when:**
- [ ] the GitHub repo exists (private) and `main` contains `dbt/dbt_project.yml`
- [ ] `dbt debug` is all green
- [ ] `workspace.dbt_rwang.my_second_dbt_model` exists in Databricks
- [ ] `workspace.raw.landing` volume exists

---

## 0.6 Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Invalid access token` | token copied with a space, or expired | generate a new token, paste again |
| First query takes 10-20 s | serverless warehouse was asleep | normal; it auto-stops when idle |
| `Catalog 'workspace' not found` | your catalog has another name | `SHOW CATALOGS;` and use that name |
| Studio cannot see the repo | dbt GitHub app not installed on that repo | GitHub → Settings → Applications → dbt → Configure → add the repo |
| `Compute quota exceeded` | Free Edition quota | wait for the reset; avoid leaving notebooks running |

---

## 0.7 Interview lines

> "I set up a Databricks workspace with Unity Catalog and connected it to dbt through a serverless SQL
> warehouse. Each developer builds into a personal schema, and production is a separate environment, so
> development work can never overwrite what consumers read."

> "Loading is deliberately outside dbt: the bronze layer is filled by an idempotent `COPY INTO` from a Unity
> Catalog volume, and dbt starts from that table as a declared source with a freshness check."

> "I used a personal access token because it is a single-developer free workspace; in a company I'd use OAuth
> or a service principal, and keep credentials in the platform's secret store, never in the repository."
