// The "Model card" at the bottom of every page: how the page was designed, from the business question
// down to the model and what guarantees it. Same chain on every page:
//   question -> decision -> grain -> model -> guarantees -> why this chart
import {html} from "htl";

const DOCS = "../dbt-docs/#!/model/model.balenciaga_pricing.";

export function modelCard({question, decision, grain, models, guarantees, chart}) {
  return html`<section class="model-card">
    <h2>Model card</h2>
    <p class="model-card__lede">How this page was designed: from the question it answers down to the model it reads
    and what makes the numbers trustworthy.</p>
    <dl>
      <div><dt>01 Question</dt><dd>${question}</dd></div>
      <div><dt>02 Decision it supports</dt><dd>${decision}</dd></div>
      <div><dt>03 Grain</dt><dd>${grain}</dd></div>
      <div><dt>04 Model</dt><dd><ul>${models.map((m) => html`<li>
        <a href="${DOCS}${m.name}"><code>${m.name}</code></a> <span>${m.role}</span></li>`)}</ul></dd></div>
      <div><dt>05 Guarantees</dt><dd><ul>${guarantees.map((g) => html`<li>${g}</li>`)}</ul></dd></div>
      <div><dt>06 Why this chart</dt><dd>${chart}</dd></div>
    </dl>
  </section>`;
}

/** A stat tile: label, value, optional note. */
export function tile(label, value, note = "", tone = "") {
  return html`<div class="tile ${tone}"><span class="tile__label">${label}</span>
    <span class="tile__value">${value}</span>${note ? html`<span class="tile__note">${note}</span>` : ""}</div>`;
}

/** A collapsible table view under a chart: every value reachable without hovering. */
export function tableView(table, label = "Table view") {
  return html`<details class="table-view"><summary>${label}</summary>${table}</details>`;
}
