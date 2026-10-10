// The chapter template, enforced by code: every phase page has the same head, the same lineage section
// and the same pager. The prose sections in between are markdown, in a fixed order:
//   01 Problem · 02 Decision · 03 Rejected · 04 dbt features · 05 Lineage · 06 Proof
import {html} from "htl";
import {phases, byId, REPO} from "../data/phases.js";

const fmtNodes = ([a, b]) => (b === 0 ? "—" : a === b ? `${b} nodes (unchanged)` : `${a} → ${b} nodes (+${b - a})`);

/** Kicker, headline, plain-words lede and the spec strip. */
export function chapterHead(id, lede) {
  const p = byId.get(id);
  const i = phases.indexOf(p);
  return html`<header class="chapter-head">
    <p class="kicker">Chapter ${String(i + 1).padStart(2, "0")} / ${phases.length} · ${p.label} · ${p.title}</p>
    <h1>${p.headline}</h1>
    <div class="plain"><p class="lede">${lede}</p></div>
    <dl class="spec">
      <div><dt>Merged</dt><dd>${p.merged}${p.commit ? html` · <a href="${REPO}/commit/${p.commit}"><code>${p.commit}</code></a>` : ""}</dd></div>
      <div><dt>DAG</dt><dd>${fmtNodes(p.nodes)}</dd></div>
      <div><dt>Result</dt><dd>${p.result}</dd></div>
      <div><dt>Adds</dt><dd>${p.adds}</dd></div>
      <div><dt>Full chapter</dt><dd>${p.doc.split(", ").map((d, k) => html`${k ? ", " : ""}<a href="${REPO}/blob/main/${d}"><code>${d.replace("docs/", "")}</code></a>`)}</dd></div>
    </dl>
  </header>`;
}

/** Section 05: the DAG as it was when this phase was merged (or a note for phases without dbt models).
 *  options.note replaces the legend, for a phase that shows today's full graph instead of its own. */
export function lineageSection(id, svgText, {note} = {}) {
  const p = byId.get(id);
  const frame = document.createElement("div");
  frame.className = "lineage";
  frame.tabIndex = 0;
  frame.setAttribute("role", "img");
  frame.setAttribute("aria-label", `Lineage after ${p.label}, scroll sideways`);
  if (svgText) frame.innerHTML = svgText.replace(/<\?xml[^>]*>/, "").replace(/ id="/g, ` id="${p.id}-`);
  return html`<section class="block">
    <div class="label">05 Lineage<span>${note ? "Today's DAG, regenerated from the production manifest on every deploy." : "The DAG when this phase was merged, compiled from git by dbt parse."}</span></div>
    <div class="content">
      ${svgText ? frame : html`<p>No dbt models yet: this phase builds the ground they stand on. The first models appear in Phase 2.</p>`}
      ${svgText && note ? html`<p class="cap">${note} Scroll sideways →</p>` : ""}
      ${svgText && !note ? html`<div class="legend"><span><i style="background:var(--ink)"></i>new in ${p.label}</span>
        <span><i style="background:var(--paper)"></i>built earlier</span>
        <span><i style="background:var(--bg);border-style:dashed;border-color:var(--rule)"></i>later phases</span></div>
        <p class="cap">Lanes, left to right: sources and seeds, staging, intermediate, marts, published, semantic layer,
        exposures. The band at the bottom is the quality lane. Every picture shares one layout, so a model never moves
        between phases. Scroll sideways →</p>` : ""}
    </div>
  </section>`;
}

/** Previous / next chapter. */
export function pager(id) {
  const i = phases.findIndex((p) => p.id === id);
  const prev = phases[i - 1], next = phases[i + 1];
  return html`<nav class="pager" aria-label="Chapters">
    ${prev ? html`<a class="prev" href="./${prev.slug}"><span class="micro">← ${prev.label}</span><b>${prev.title}</b></a>` : html`<a class="prev" href="./"><span class="micro">← Home</span><b>The story</b></a>`}
    ${next ? html`<a class="next" href="./${next.slug}"><span class="micro">${next.label} →</span><b>${next.title}</b></a>` : html`<a class="next" href="./bi/" rel="external"><span class="micro">The result →</span><b>BI pages</b></a>`}
  </nav>`;
}
