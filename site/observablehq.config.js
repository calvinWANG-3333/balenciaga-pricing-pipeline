// Observable Framework configuration: the portfolio site, built as static files.
// The BI pages (bi/) and dbt docs are separate builds, published next to it at ./bi/ and ./dbt-docs/
// by tools/site/assemble.py. Every page sits at the root, so the same relative links work everywhere.
export default {
  title: "Pricing pipeline · Ruihang Wang",
  root: "src",
  output: "dist",
  style: "style.css",
  sidebar: false,
  pager: false,
  toc: false,
  search: false,
  head: `<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<meta name="description" content="An analytics engineering project with dbt on Databricks: a real pricing incident, fixed by design and proved on the same data.">`,
  header: `<div class="masthead">
  <nav class="left" aria-label="Story"><a href="./#story">Story</a><a href="./#numbers">In numbers</a><a href="./#phases">Phases</a><a href="./#lineage">Lineage</a></nav>
  <a class="wordmark" href="./">Pricing Pipeline</a>
  <nav class="right" aria-label="Project"><a href="./bi/" rel="external">BI</a><a href="./dbt-docs/" rel="external">dbt docs</a><a href="https://github.com/calvinWANG-3333/balenciaga-pricing-pipeline">GitHub ↗</a></nav>
</div>`,
  footer: `Independent portfolio project by Ruihang Wang · synthetic data calibrated on public price ranges · not affiliated with Balenciaga.
Built with dbt on Databricks; published by the project's own production pipeline.`
};
