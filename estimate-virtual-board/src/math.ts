/** Pure helpers duplicated from Django template autosave/recalc UX */
export function fmt2(n: number): string {
  return (Math.round(n * 100) / 100).toFixed(2);
}

export function parseNum(s: string | undefined | null): number {
  if (s === null || s === undefined) return 0;
  const t = String(s).replace(/\s/g, "").replace(",", ".");
  if (t === "" || t === "-" || t === "." || t === "-.") return 0;
  const n = parseFloat(t);
  return Number.isFinite(n) ? n : 0;
}

export function normalizeNumField(name: string, val: unknown): string {
  if (
    name !== "quantity" &&
    name !== "cost_price" &&
    name !== "markup_percent"
  ) {
    return String(val ?? "");
  }
  const s = String(val == null ? "" : val)
    .trim()
    .replace(/\s/g, "")
    .replace(",", ".");
  if (s === "" || s === "-" || s === "." || s === "-.") return "0";
  return s;
}

export function recalcSellAndTotals(fields: {
  quantity: string;
  cost_price: string;
  markup_percent: string;
}): {
  sell: number;
  tCost: number;
  tPrice: number;
} {
  const q = parseNum(fields.quantity);
  const cp = parseNum(fields.cost_price);
  const m = parseNum(fields.markup_percent);
  const sell = cp * (1 + m / 100);
  return {
    sell,
    tCost: q * cp,
    tPrice: q * sell,
  };
}

export function isZeroLikeInput(val: string | undefined | null): boolean {
  if (val === null || val === undefined) return true;
  const t = String(val).replace(/\s/g, "").replace(",", ".");
  if (t === "" || t === "-" || t === "." || t === "-.") return true;
  const n = parseFloat(t);
  return Number.isFinite(n) && n === 0;
}
