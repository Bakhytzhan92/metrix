/** Pure helpers duplicated from Django template autosave/recalc UX */
export function fmt2(n: number): string {
  return (Math.round(n * 100) / 100).toFixed(2);
}

/** Суммы для отображения: 53881303.68 → «53 881 303,68». */
export function fmtMoney(n: number, decimals = 2): string {
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  const fixed = abs.toFixed(decimals);
  const [intPart, fracPart = ""] = fixed.split(".");
  const chunks: string[] = [];
  let rest = intPart;
  while (rest.length > 0) {
    chunks.push(rest.slice(-3));
    rest = rest.slice(0, -3);
  }
  const grouped = chunks.reverse().join(" ");
  return decimals > 0 ? `${sign}${grouped},${fracPart}` : `${sign}${grouped}`;
}

/** Цена заказчика за ед.: до 3 знаков после запятой. */
export function fmtSell(n: number): string {
  const v = Math.round(n * 1000) / 1000;
  let s = v.toFixed(3);
  if (s.includes(".")) s = s.replace(/0+$/, "").replace(/\.$/, "");
  return s;
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
    name !== "markup_percent" &&
    name !== "sell_price"
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

export function markupFromSell(cost_price: string, sell_price: string): number {
  const cp = parseNum(cost_price);
  const sp = parseNum(sell_price);
  if (cp <= 0) return 0;
  return (sp / cp - 1) * 100;
}

export function isZeroLikeInput(val: string | undefined | null): boolean {
  if (val === null || val === undefined) return true;
  const t = String(val).replace(/\s/g, "").replace(",", ".");
  if (t === "" || t === "-" || t === "." || t === "-.") return true;
  const n = parseFloat(t);
  return Number.isFinite(n) && n === 0;
}

/** Незавершённый ввод числа (пусто, «12.», «-») — не форматировать и не сохранять. */
export function isPartialNumericInput(val: string | undefined | null): boolean {
  if (val === null || val === undefined) return true;
  const t = String(val).trim().replace(/\s/g, "").replace(",", ".");
  if (t === "" || t === "-" || t === "." || t === "-." || t.endsWith(".")) {
    return true;
  }
  return false;
}

export type ItemRecalcField =
  | "quantity"
  | "cost_price"
  | "markup_percent"
  | "sell_price"
  | "type"
  | "name"
  | "unit";

export function applyItemRecalc(
  fields: {
    quantity: string;
    cost_price: string;
    markup_percent: string;
    sell_price: string;
  },
  changed: ItemRecalcField,
): {
  quantity: string;
  cost_price: string;
  markup_percent: string;
  sell_price: string;
  total_cost: string;
  total_price: string;
} {
  const q = parseNum(fields.quantity);
  const cp = parseNum(fields.cost_price);
  let markup = parseNum(fields.markup_percent);
  let sell = parseNum(fields.sell_price);

  if (changed === "sell_price") {
    sell = parseNum(fields.sell_price);
    const markupStr = isPartialNumericInput(fields.sell_price)
      ? fields.markup_percent
      : fmt2(markupFromSell(fields.cost_price, fields.sell_price));
    return {
      quantity: fields.quantity,
      cost_price: fields.cost_price,
      markup_percent: markupStr,
      sell_price: fields.sell_price,
      total_cost: fmtMoney(q * cp),
      total_price: fmtMoney(q * sell),
    };
  }

  if (changed === "markup_percent") {
    if (!isPartialNumericInput(fields.markup_percent)) {
      markup = parseNum(fields.markup_percent);
      sell = cp * (1 + markup / 100);
    }
    return {
      quantity: fields.quantity,
      cost_price: fields.cost_price,
      markup_percent: fields.markup_percent,
      sell_price: fmtSell(sell),
      total_cost: fmtMoney(q * cp),
      total_price: fmtMoney(q * sell),
    };
  }

  if (changed === "cost_price") {
    if (
      !isPartialNumericInput(fields.sell_price) &&
      parseNum(fields.sell_price) > 0 &&
      cp > 0
    ) {
      markup = markupFromSell(fields.cost_price, fields.sell_price);
      return {
        quantity: fields.quantity,
        cost_price: fields.cost_price,
        markup_percent: fmt2(markup),
        sell_price: fields.sell_price,
        total_cost: fmtMoney(q * cp),
        total_price: fmtMoney(q * parseNum(fields.sell_price)),
      };
    }
    markup = parseNum(fields.markup_percent);
    sell = cp * (1 + markup / 100);
  } else if (
    changed === "quantity" ||
    changed === "type" ||
    changed === "name" ||
    changed === "unit"
  ) {
    sell = parseNum(fields.sell_price);
    return {
      quantity: fields.quantity,
      cost_price: fields.cost_price,
      markup_percent: fields.markup_percent,
      sell_price: fields.sell_price,
      total_cost: fmtMoney(q * cp),
      total_price: fmtMoney(q * sell),
    };
  }

  return {
    quantity: fields.quantity,
    cost_price: fields.cost_price,
    markup_percent: fmt2(markup),
    sell_price: fmtSell(sell),
    total_cost: fmtMoney(q * cp),
    total_price: fmtMoney(q * sell),
  };
}
