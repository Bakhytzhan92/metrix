import type { ScheduleRow, SuccChoice, ZoomMode } from "./types";

export const ESTIMATE_SECTION_H = 38;
export const TASK_ROW_H = 58;
export const ITEM_ROW_H = 30;
export const HEAD_H = 36;
export const HSCROLL_H = 14;

export const PX_PER_DAY: Record<ZoomMode, number> = {
  day: 28,
  week: 10,
  month: 4,
};

export const LEFT_COL_DEFAULTS = [36, 220, 72, 108, 44, 88, 96, 140];
export const LEFT_COL_MINS = [28, 120, 48, 90, 36, 64, 72, 96];

/** Каталог групп для колонки «После» (из payload или из строк графика). */
export function buildSuccCatalog(
  rows: ScheduleRow[],
  catalog?: SuccChoice[],
): SuccChoice[] {
  if (catalog && catalog.length > 0) return catalog;
  const sectionNames = new Map<number, string>();
  for (const r of rows) {
    if (r.kind === "estimate_section") {
      sectionNames.set(r.section_id, r.name);
    }
  }
  return rows
    .filter(
      (r): r is ScheduleRow & { item_id: number } =>
        r.kind === "task" && r.item_id != null,
    )
    .map((r) => ({
      id: r.item_id,
      label: (r.name || "—").slice(0, 140),
      section_id: r.section_id,
      section_name: sectionNames.get(r.section_id) || "—",
    }));
}

export function rowHeight(row: ScheduleRow): number {
  if (row.kind === "estimate_section") return ESTIMATE_SECTION_H;
  if (row.kind === "task") return TASK_ROW_H;
  return ITEM_ROW_H;
}

export const SCHEDULE_MIN_YEAR = 1990;
export const SCHEDULE_MAX_YEAR = 2100;
/** Максимальный диапазон шкалы Gantt (защита от «зависания» при ошибочных датах). */
export const SCHEDULE_MAX_RANGE_DAYS = 366 * 5;

export function isScheduleYearAllowed(year: number): boolean {
  return (
    Number.isFinite(year) &&
    year >= SCHEDULE_MIN_YEAR &&
    year <= SCHEDULE_MAX_YEAR
  );
}

export function isValidScheduleDateString(
  s: string | null | undefined,
): boolean {
  if (!s) return false;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(s))) return false;
  const d = parseYMD(s);
  return d != null;
}

export function parseYMD(s: string | null | undefined): Date | null {
  if (!s) return null;
  const p = String(s).split("-");
  if (p.length !== 3) return null;
  const y = Number(p[0]);
  const m = Number(p[1]);
  const d = Number(p[2]);
  if (!y || !m || !d) return null;
  if (!isScheduleYearAllowed(y)) return null;
  const dt = new Date(Date.UTC(y, m - 1, d));
  if (isNaN(dt.getTime())) return null;
  if (
    dt.getUTCFullYear() !== y ||
    dt.getUTCMonth() !== m - 1 ||
    dt.getUTCDate() !== d
  ) {
    return null;
  }
  return dt;
}

export function formatYMD(d: Date | null): string {
  if (!d || isNaN(d.getTime())) return "";
  return (
    d.getUTCFullYear() +
    "-" +
    String(d.getUTCMonth() + 1).padStart(2, "0") +
    "-" +
    String(d.getUTCDate()).padStart(2, "0")
  );
}

export function addDays(d: Date, n: number): Date {
  return new Date(d.getTime() + n * 86400000);
}

export function daysBetween(a: Date, b: Date): number {
  return Math.round((b.getTime() - a.getTime()) / 86400000);
}

export function cmpTime(a: Date | null, b: Date | null): number {
  if (!a || !b) return 0;
  return a.getTime() - b.getTime();
}

export type DateRange = { start: Date; end: Date };

export function computeRange(rows: ScheduleRow[], today: string): DateRange {
  let minD: Date | null = null;
  let maxD: Date | null = null;
  const t = parseYMD(today);
  rows.forEach((r) => {
    if (r.kind !== "task") return;
    const s = r.schedule_start ? parseYMD(r.schedule_start) : null;
    const e = r.schedule_end ? parseYMD(r.schedule_end) : null;
    if (s) minD = minD ? (cmpTime(s, minD) < 0 ? s : minD) : s;
    if (e) maxD = maxD ? (cmpTime(e, maxD) > 0 ? e : maxD) : e;
  });
  const base = t || new Date();
  if (!minD || !maxD) {
    return { start: addDays(base, -7), end: addDays(base, 90) };
  }
  if (daysBetween(minD, maxD) > SCHEDULE_MAX_RANGE_DAYS) {
    return { start: addDays(base, -30), end: addDays(base, 180) };
  }
  return { start: addDays(minD, -7), end: addDays(maxD, 14) };
}

export function totalDays(range: DateRange): number {
  return Math.max(1, daysBetween(range.start, range.end) + 1);
}

export function timelineWidth(range: DateRange, zoom: ZoomMode): number {
  return totalDays(range) * (PX_PER_DAY[zoom] || 28);
}

export function dayOffset(range: DateRange, d: Date): number {
  return daysBetween(range.start, d);
}

export function pxPerDay(zoom: ZoomMode): number {
  return PX_PER_DAY[zoom] || 28;
}

export function recomputeSuccessorIds(rows: ScheduleRow[]): void {
  const firstByPred: Record<number, number> = {};
  rows.forEach((r) => {
    if (r.kind === "task" && r.predecessor_id && r.item_id) {
      const p = r.predecessor_id;
      if (firstByPred[p] == null) firstByPred[p] = r.item_id;
    }
  });
  rows.forEach((r) => {
    if (r.kind === "task" && r.item_id) {
      const sid = firstByPred[r.item_id];
      r.successor_id = sid != null ? sid : null;
    }
  });
}

export type HeadCell = { width: number; label: string };

export function buildHeadCells(range: DateRange, zoom: ZoomMode): HeadCell[] {
  const ppd = pxPerDay(zoom);
  const cells: HeadCell[] = [];
  const end = range.end;

  if (zoom === "month") {
    let d = new Date(
      Date.UTC(range.start.getUTCFullYear(), range.start.getUTCMonth(), 1),
    );
    while (d.getTime() <= end.getTime()) {
      const y = d.getUTCFullYear();
      const mo = d.getUTCMonth();
      const daysInMonth = new Date(Date.UTC(y, mo + 1, 0)).getUTCDate();
      let monthStart = new Date(Date.UTC(y, mo, 1));
      let monthEnd = new Date(Date.UTC(y, mo, daysInMonth));
      if (monthStart.getTime() < range.start.getTime())
        monthStart = new Date(range.start.getTime());
      if (monthEnd.getTime() > range.end.getTime())
        monthEnd = new Date(range.end.getTime());
      const w = (daysBetween(monthStart, monthEnd) + 1) * ppd;
      cells.push({
        width: w,
        label: d.toLocaleString("ru", {
          month: "short",
          year: "2-digit",
          timeZone: "UTC",
        }),
      });
      d = new Date(Date.UTC(y, mo + 1, 1));
    }
    return cells;
  }

  if (zoom === "week") {
    let d = new Date(range.start.getTime());
    while (d.getTime() <= end.getTime()) {
      const weekEnd = addDays(d, 6);
      const we =
        weekEnd.getTime() > end.getTime()
          ? new Date(end.getTime())
          : weekEnd;
      const ws = new Date(Math.max(d.getTime(), range.start.getTime()));
      const ww = (daysBetween(ws, we) + 1) * ppd;
      cells.push({
        width: ww,
        label: `${formatYMD(d).slice(5)} — ${formatYMD(we).slice(5)}`,
      });
      d = addDays(we, 1);
    }
    return cells;
  }

  let d = new Date(range.start.getTime());
  while (d.getTime() <= end.getTime()) {
    cells.push({ width: ppd, label: String(d.getUTCDate()) });
    d = addDays(d, 1);
  }
  return cells;
}

export function barGeometry(
  range: DateRange,
  zoom: ZoomMode,
  start: string,
  end: string,
): { left: number; width: number } | null {
  const s = parseYMD(start);
  const e = parseYMD(end);
  if (!s || !e) return null;
  const ppd = pxPerDay(zoom);
  const left = dayOffset(range, s) * ppd;
  let width = (daysBetween(s, e) + 1) * ppd - 4;
  if (width < 6) width = 6;
  return { left, width };
}

export function formatMoneyRub(val: string | number | undefined): string {
  if (val == null || val === "") return "";
  const n = Number(String(val).replace(/\s/g, "").replace(",", "."));
  if (!Number.isFinite(n)) return String(val);
  return (
    new Intl.NumberFormat("ru-RU", {
      maximumFractionDigits: 0,
    }).format(n) + " ₸"
  );
}

export function taskSummaryLine(row: ScheduleRow): string {
  if (row.item_count != null && row.item_count > 0) {
    return `${row.item_count} поз.`;
  }
  return "";
}
