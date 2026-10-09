// Read a snapshot CSV with explicit types. Ids stay strings (a hash like "0e48..." must never become a
// number), dates become UTC dates, flags become booleans, everything numeric becomes a number.
import {csvParse} from "d3";

const DATE = /(_date|_month|_date_used)$/;
const TIMESTAMP = /_at$/;
const KEEP = /(_id$|^sku$|^object_id$|_file$|_rule$|^message$|^subject$|^run_id$)/;

function typed(value, key) {
  if (value === "") return null;
  if (KEEP.test(key)) return value;
  if (DATE.test(key)) return new Date(`${value}T00:00:00Z`);
  if (TIMESTAMP.test(key)) return new Date(`${value.replace(" ", "T")}Z`);
  if (value === "true") return true;
  if (value === "false") return false;
  const n = Number(value);
  return Number.isNaN(n) ? value : n;
}

// Pages call load(FileAttachment("data/x.csv").text()): reading the file as text keeps Framework from
// pulling a CSV parser from a CDN at build time, so the site builds offline from node_modules.
export async function load(text) {
  return csvParse(await text, (row) => {
    for (const k in row) row[k] = typed(row[k], k);
    return row;
  });
}
