---
title: Phase 6d · This site
---

```js
import {chapterHead, lineageSection, pager} from "./components/chapter.js";
display(chapterHead("p6d", "Everything in this project, the story, the dashboards and the technical documentation, is published as one website. Nobody updates it by hand: every time a change is approved and the data is rebuilt, the same pipeline rebuilds this site."));
```

<section class="block"><div class="label">01 Problem</div><div class="content">

The project lived in a repository: twelve teaching chapters in markdown, six BI pages that had to be built locally,
and dbt docs that only existed inside a production run. A recruiter has two minutes. A friend who does not work
with data has even less patience for jargon. A technical reviewer wants to check the claims, not read about them.

Nobody clones a repository to answer those questions. And any diagram drawn by hand would be out of date at the
next pull request.

</div></section>

<section class="block"><div class="label">02 Decision</div><div class="content">

One GitHub Pages site with three areas, built and published by the production pipeline itself. I designed it the
way I designed the BI pages, starting from the reader instead of the content:

| Reader | Their question | Where the site answers it |
|---|---|---|
| Recruiter, 2 minutes | What did this person solve? | The home page: the incident in three lines, the before and after |
| Friend outside data | What does any of it mean? | *In numbers*: every figure with a plain sentence; the plain lede on each chapter |
| Analytics engineer reviewing the work | How did they decide? | The chapters: problem, decision, rejected alternatives, dbt features |
| Engineer checking the claims | Is it real? | dbt docs from the production run, the lineage from its manifest, the source and its CI runs |

| Path | Built from | Tool |
|---|---|---|
| `/` | `site/src/*.md`, one page per phase | Observable Framework |
| `/bi/` | `bi/src/*.md` on the public snapshot | Observable Framework |
| `/dbt-docs/` | `dbt docs generate --static` in the production deploy | dbt |

<p class="cap">Every chapter follows one template, and the template is code (<code>site/src/components/chapter.js</code>): the header, the lineage section and the pager are generated from one table of facts per phase.</p>

</div></section>

<section class="block"><div class="label">03 Rejected<span>The alternatives I considered, and why not.</span></div><div class="content">

| Alternative | Why not |
|---|---|
| Diagrams drawn by hand | Out of date at the next pull request. Every lineage picture here is compiled from a dbt manifest. |
| A second site generator or hand-written HTML | A second design system to maintain. The site reuses the BI pages' tool, tokens and build. |
| A separate workflow that publishes on site changes only | The dbt docs on the site could then describe an older production build than the one running. |
| Publishing `index.html`, `manifest.json` and `catalog.json` | Three files fetched at run time. `--static` writes one self-contained page with the same content. |

</div></section>

<section class="block"><div class="label">04 dbt features<span>What each one does in this phase.</span></div><div class="content">

| Feature | What it does here |
|---|---|
| `dbt docs generate --static` | Writes the whole documentation, catalog included, into one HTML file that the site serves at `/dbt-docs/`. |
| `manifest.json` as data | The publish job runs `tools.lineage.collect --current` on the manifest of that production run, so the full lineage on the home page is the deployed DAG. |
| The production state artifact | The same artifact that Slim CI defers to now also carries the static docs to the publish job. |
| Exposures with `url` | Each BI page's exposure points at its address on this site, so dbt docs link the models to the pages that read them. |
| Model card links | Every BI page links its models to `../dbt-docs/#!/model/…`: from a chart to its SQL in one click. |

```yaml
# ci/deploy.yml.next (moved to .github/workflows/deploy.yml), the publish job
site:
  needs: deploy
  if: always() && needs.deploy.outputs.built == 'success'
```

</div></section>

```js
display(lineageSection("p6d", await FileAttachment("lineage/lineage_full.svg").text(), {note: "Phase 6d adds no dbt node. The site shows today's DAG, the one built in Phase 6c."}));
```

<section class="block"><div class="label">06 Proof<span>What runs on every merge to main.</span></div><div class="content">

| Step | Job | What it checks or produces |
|---|---|---|
| 1 | `deploy` | dbt build in production, the delivery gate, dbt docs, the production state |
| 2 | `site` | lineage from that manifest, the BI pages, this site, assembled with the dbt docs |
| 3 | `site` | one deployment to GitHub Pages, recorded in the `github-pages` environment |

Pull requests run a third CI job that builds the BI pages and the site without a warehouse, so a broken page is
caught before the merge. The assembly script has its own tests, part of the Python suite that CI runs.

</div></section>

```js
display(pager("p6d"));
```
