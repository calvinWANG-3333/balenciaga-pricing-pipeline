import {utcFormat} from "d3";

export const fmtDate = utcFormat("%-d %b %Y");
export const fmtDay = utcFormat("%-d %b");
export const fmtMonth = utcFormat("%B %Y");
export const iso = utcFormat("%Y-%m-%d");

/** +5.24 % - a change is always signed. */
export function pct(x, digits = 1) {
  if (x == null || Number.isNaN(x)) return "—";
  const v = (x * 100).toFixed(digits);
  return `${x > 0 ? "+" : x < 0 ? "−" : ""}${v.replace("-", "")} %`;
}

/** 3,310 USD - prices keep their own currency; they are never converted. */
export function money(x, currency) {
  if (x == null || Number.isNaN(x)) return "—";
  return `${Math.round(x).toLocaleString("en-US")} ${currency ?? ""}`.trim();
}

export const int = (x) => (x == null ? "—" : Math.round(x).toLocaleString("en-US"));
