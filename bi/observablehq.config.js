// Observable Framework configuration: a static BI site, built from the snapshot in src/data/.
// Design: the same system as the portfolio site (cool grey, black, mono figures; red only for BLOCK).
export default {
  title: "Pricing pipeline · BI",
  root: "src",
  output: "dist",
  style: "style.css",
  sidebar: false,
  pager: false,
  toc: false,
  search: false,
  pages: [
    {name: "Overview", path: "/"},
    {name: "Micro", path: "/micro"},
    {name: "Macro", path: "/macro"},
    {name: "Price changes", path: "/price-changes"},
    {name: "The incident", path: "/incident"},
    {name: "Data health", path: "/data-health"}
  ],
  head: `<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">`,
  header: `<nav class="topnav">
  <a class="brand" href="./">Pricing<span>·</span>BI</a>
  <a href="./">Overview</a><a href="./micro">Micro</a><a href="./macro">Macro</a>
  <a href="./price-changes">Price changes</a><a href="./incident">The incident</a><a href="./data-health">Data health</a>
  <a class="out" href="../" rel="external">← Project</a>
</nav>`,
  footer: `Independent portfolio project by Ruihang Wang · synthetic data calibrated on public price ranges · not affiliated with Balenciaga.
Built with dbt on Databricks; this site reads only the public, gate-released layer.`
};
