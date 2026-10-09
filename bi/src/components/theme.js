// The design system, in one place. Monochrome by intent: a price monitor's job is to make the
// exception visible, so colour is reserved for the one state that stops a delivery (BLOCK).
export const INK = "#0B0B0B";
export const BG = "#E4E4E1";
export const PAPER = "#F7F7F5";
export const MUTED = "#6E6E68";
export const MID = "#A6A6A0";
export const LIGHT = "#CFCFCA";
export const RULE = "#C2C2BD";
export const RED = "#C8102E";

// Gate verdicts: always shown with their word (PASS / WARN / BLOCK), never colour alone.
export const DECISION = {domain: ["PASS", "WARN", "BLOCK"], range: [LIGHT, MUTED, RED]};

// Check results inside a delivery, from quiet to loud. A failure of a blocking check is the only red.
export const CHECK_STATUS = {
  domain: ["skip", "pass", "warn", "fail", "block"],
  range: [PAPER, LIGHT, MID, INK, RED],
  label: {skip: "·", pass: "✓", warn: "!", fail: "×", block: "×"}
};

// Micro price statuses: movements are dark, stillness is light, absences are paper with a word.
export const PRICE_STATUS = {
  domain: ["price_increase", "price_decrease", "unchanged", "first_delivery", "no_valid_price", "not_found", "page_error"],
  range: [INK, MUTED, LIGHT, "#EBEBE8", PAPER, PAPER, PAPER],
  label: {price_increase: "increase", price_decrease: "decrease", unchanged: "unchanged",
          first_delivery: "first delivery", no_valid_price: "no valid price", not_found: "not found",
          page_error: "page error"}
};

// Plot defaults shared by every chart.
export const plotStyle = {
  background: "transparent",
  color: INK,
  fontFamily: "'JetBrains Mono', ui-monospace, monospace",
  fontSize: "11px",
  overflow: "visible"
};
