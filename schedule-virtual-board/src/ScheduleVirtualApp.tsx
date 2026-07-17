import React, {
  forwardRef,
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  VariableSizeList as List,
  type ListChildComponentProps,
} from "react-window";

import {
  ESTIMATE_SECTION_H,
  HEAD_H,
  HSCROLL_H,
  ITEM_ROW_H,
  LEFT_COL_DEFAULTS,
  LEFT_COL_MINS,
  addDays,
  barGeometry,
  buildHeadCells,
  buildSuccCatalog,
  cmpTime,
  computeRange,
  dayOffset,
  daysBetween,
  formatYMD,
  isValidScheduleDateString,
  parseYMD,
  pxPerDay,
  recomputeSuccessorIds,
  rowHeight,
  timelineWidth,
} from "./gantt";
import type {
  ScheduleRow,
  ScheduleVirtualPayload,
  ZoomMode,
} from "./types";

const LEFT_HEADERS = [
  "№",
  "Наименование",
  "Кол-во",
  "Начало",
  "Дни",
  "Статус",
  "Отв.",
  "После",
];

function apiUrl(template: string, itemId: number): string {
  return template.replace("__ID__", String(itemId));
}

function leftTotalWidth(widths: number[]): number {
  return widths.reduce((a, b) => a + b, 0);
}

function groupSuccChoices(
  choices: ScheduleRow["succ_choices"],
): Array<{ key: string; label: string; items: NonNullable<ScheduleRow["succ_choices"]> }> {
  const out: Array<{
    key: string;
    label: string;
    items: NonNullable<ScheduleRow["succ_choices"]>;
  }> = [];
  const idx = new Map<number, number>();
  for (const c of choices || []) {
    const sid = c.section_id ?? 0;
    if (!idx.has(sid)) {
      idx.set(sid, out.length);
      out.push({
        key: String(sid),
        label: c.section_name || "—",
        items: [],
      });
    }
    out[idx.get(sid)!].items.push(c);
  }
  return out;
}

/** Левая таблица фиксирована; горизонтально скроллится только Gantt (react-window ломает sticky). */
function SplitRowShell({
  viewportW,
  leftW,
  timelineW,
  scrollLeft,
  height,
  className,
  left,
  gantt,
}: {
  viewportW: number;
  leftW: number;
  timelineW: number;
  scrollLeft: number;
  height: number;
  className?: string;
  left: React.ReactNode;
  gantt: React.ReactNode;
}) {
  const ganttPaneW = Math.max(0, viewportW - leftW);
  return (
    <div
      className={className}
      style={{
        position: "relative",
        width: viewportW,
        height,
        overflow: "hidden",
        boxSizing: "border-box",
      }}
    >
      <div
        className="absolute left-0 top-0 h-full z-[2] border-r border-slate-200 bg-inherit"
        style={{ width: leftW }}
      >
        {left}
      </div>
      <div
        className="h-full overflow-hidden"
        style={{ marginLeft: leftW, width: ganttPaneW }}
      >
        <div
          style={{
            width: timelineW,
            height: "100%",
            transform: `translateX(-${scrollLeft}px)`,
            position: "relative",
          }}
        >
          {gantt}
        </div>
      </div>
    </div>
  );
}

function statusBarClass(status: string | undefined): string {
  switch (status) {
    case "in_progress":
      return "sched-status-in_progress";
    case "completed":
      return "sched-status-completed";
    case "overdue":
      return "sched-status-overdue";
    case "paused":
      return "sched-status-paused";
    default:
      return "sched-status-planned";
  }
}

const EstimateSectionRow = memo(function EstimateSectionRow({
  row,
  colWidths,
  leftW,
  viewportW,
  timelineW,
  scrollLeft,
}: {
  row: ScheduleRow;
  colWidths: number[];
  leftW: number;
  viewportW: number;
  timelineW: number;
  scrollLeft: number;
}) {
  return (
    <SplitRowShell
      viewportW={viewportW}
      leftW={leftW}
      timelineW={timelineW}
      scrollLeft={scrollLeft}
      height={ESTIMATE_SECTION_H}
      className="border-b border-slate-200 bg-slate-200/80 text-xs font-bold uppercase tracking-wide text-slate-800"
      left={
        <div className="flex items-center px-2 h-full bg-inherit truncate">
          {row.name}
        </div>
      }
      gantt={<div className="h-full bg-slate-100/50" />}
    />
  );
});

const ItemRow = memo(function ItemRow({
  row,
  colWidths,
  leftW,
  viewportW,
  timelineW,
  scrollLeft,
  range,
  zoom,
  statusChoices,
  assignees,
  succCatalog,
  onSave,
}: {
  row: ScheduleRow;
  colWidths: number[];
  leftW: number;
  viewportW: number;
  timelineW: number;
  scrollLeft: number;
  range: ReturnType<typeof computeRange>;
  zoom: ZoomMode;
  statusChoices: ScheduleVirtualPayload["status_choices"];
  assignees: ScheduleVirtualPayload["assignees"];
  succCatalog: ScheduleVirtualPayload["succ_catalog"];
  onSave: (itemId: number, body: Record<string, unknown>) => void;
}) {
  const itemId = row.item_id!;
  const qty =
    row.quantity != null && String(row.quantity) !== ""
      ? `${row.quantity}${row.unit ? ` ${row.unit}` : ""}`
      : "";
  const bar =
    row.schedule_start && row.schedule_end
      ? barGeometry(range, zoom, row.schedule_start, row.schedule_end)
      : null;
  const succGroups = useMemo(() => {
    const choices = succCatalog.filter((c) => c.id !== itemId);
    return groupSuccChoices(choices);
  }, [succCatalog, itemId]);
  const dragRef = useRef<{
    mode: "drag" | "resize";
    startX: number;
    origStart: Date;
    origEnd: Date;
  } | null>(null);
  const [startDraft, setStartDraft] = useState(row.schedule_start || "");

  useEffect(() => {
    setStartDraft(row.schedule_start || "");
  }, [row.schedule_start]);

  const commitStartDate = useCallback(
    (raw: string) => {
      const v = raw.trim();
      const prev = row.schedule_start || "";
      if (v === prev) return;
      if (v && !isValidScheduleDateString(v)) {
        setStartDraft(prev);
        return;
      }
      const dur =
        row.duration_days && row.duration_days >= 1 ? row.duration_days : 1;
      onSave(itemId, {
        schedule_start: v || null,
        ...(v ? { duration_days: dur } : { schedule_end: null }),
      });
    },
    [onSave, row.duration_days, row.schedule_start, itemId],
  );

  useEffect(() => {
    function onMove(ev: MouseEvent) {
      const st = dragRef.current;
      if (!st) return;
      const dx = ev.clientX - st.startX;
      const dd = Math.round(dx / pxPerDay(zoom));
      const barEl = document.querySelector(
        `.sched-vbar[data-item-id="${itemId}"]`,
      ) as HTMLElement | null;
      if (!barEl) return;
      if (st.mode === "drag") {
        const ns = addDays(st.origStart, dd);
        const ne = addDays(st.origEnd, dd);
        if (
          ns.getTime() < range.start.getTime() ||
          ne.getTime() > range.end.getTime()
        )
          return;
        barEl.style.left = `${dayOffset(range, ns) * pxPerDay(zoom)}px`;
      } else {
        let ne2 = addDays(st.origEnd, dd);
        if (cmpTime(ne2, st.origStart) < 0)
          ne2 = new Date(st.origStart.getTime());
        const w =
          (daysBetween(st.origStart, ne2) + 1) * pxPerDay(zoom) - 4;
        barEl.style.width = `${Math.max(6, w)}px`;
      }
    }
    function onUp(ev: MouseEvent) {
      const st = dragRef.current;
      if (!st) return;
      const dx = ev.clientX - st.startX;
      const dd = Math.round(dx / pxPerDay(zoom));
      if (st.mode === "drag") {
        onSave(itemId, {
          schedule_start: formatYMD(addDays(st.origStart, dd)),
          schedule_end: formatYMD(addDays(st.origEnd, dd)),
        });
      } else {
        let ne3 = addDays(st.origEnd, dd);
        if (cmpTime(ne3, st.origStart) < 0)
          ne3 = new Date(st.origStart.getTime());
        onSave(itemId, { schedule_end: formatYMD(ne3) });
      }
      dragRef.current = null;
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [onSave, range, itemId, zoom]);

  const onBarMouseDown = (ev: React.MouseEvent) => {
    const rz = (ev.target as HTMLElement).closest(".sched-bar-resize");
    const s = parseYMD(row.schedule_start);
    const e = parseYMD(row.schedule_end);
    if (!s || !e) {
      if (!rz) {
        const t = parseYMD(new Date().toISOString().slice(0, 10));
        onSave(itemId, {
          schedule_start: formatYMD(t),
          duration_days: 1,
        });
      }
      return;
    }
    ev.preventDefault();
    dragRef.current = rz
      ? { mode: "resize", startX: ev.clientX, origStart: s, origEnd: e }
      : { mode: "drag", startX: ev.clientX, origStart: s, origEnd: e };
  };

  return (
    <SplitRowShell
      viewportW={viewportW}
      leftW={leftW}
      timelineW={timelineW}
      scrollLeft={scrollLeft}
      height={ITEM_ROW_H}
      className="border-b border-slate-100 bg-white text-[11px] text-slate-800"
      left={
        <div className="flex items-stretch h-full bg-white">
          <Cell w={colWidths[0]} className="flex items-center justify-center tabular-nums text-slate-500">
            {row.number || ""}
          </Cell>
          <Cell w={colWidths[1]} className="flex items-center pl-1 min-w-0">
            <div className="truncate" title={row.name}>
              {row.name}
            </div>
          </Cell>
          <Cell w={colWidths[2]} className="flex items-center truncate tabular-nums text-slate-600">
            {qty}
          </Cell>
          <Cell w={colWidths[3]} className="flex items-center">
            <input
              type="date"
              className="sched-input-xs w-full min-w-0 box-border text-[11px] px-1 py-0.5 border border-slate-300 rounded bg-white"
              value={startDraft}
              min="1990-01-01"
              max="2100-12-31"
              onChange={(e) => setStartDraft(e.target.value)}
              onBlur={(e) => commitStartDate(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") e.currentTarget.blur();
              }}
            />
          </Cell>
          <Cell w={colWidths[4]} className="flex items-center">
            <input
              type="number"
              min={1}
              className="sched-input-xs w-full min-w-0 box-border text-[11px] px-1 py-0.5 border border-slate-300 rounded text-right bg-white"
              defaultValue={
                row.duration_days != null && row.duration_days >= 1
                  ? String(row.duration_days)
                  : ""
              }
              placeholder="—"
              onChange={(e) => {
                let d = parseInt(e.target.value, 10);
                if (!d || d < 1) d = 1;
                e.target.value = String(d);
                onSave(itemId, { duration_days: d });
              }}
            />
          </Cell>
          <Cell w={colWidths[5]} className="flex items-center">
            <select
              className="sched-input-xs w-full min-w-0 box-border text-[10px] px-0.5 py-0.5 border border-slate-300 rounded bg-white"
              defaultValue={row.status || "planned"}
              onChange={(e) =>
                onSave(itemId, { schedule_status: e.target.value })
              }
            >
              {statusChoices.map(([val, label]) => (
                <option key={val} value={val}>
                  {label}
                </option>
              ))}
            </select>
          </Cell>
          <Cell w={colWidths[6]} className="flex items-center">
            <select
              className="sched-input-xs w-full min-w-0 box-border text-[10px] px-0.5 py-0.5 border border-slate-300 rounded bg-white"
              defaultValue={
                row.assignee_id != null ? String(row.assignee_id) : ""
              }
              onChange={(e) =>
                onSave(itemId, {
                  schedule_assignee_id:
                    e.target.value === "" ? null : Number(e.target.value),
                })
              }
            >
              <option value="">—</option>
              {assignees.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.username}
                </option>
              ))}
            </select>
          </Cell>
          <Cell w={colWidths[7]} className="flex items-center">
            <select
              className="sched-input-xs w-full min-w-0 box-border text-[10px] px-0.5 py-0.5 border border-slate-300 rounded bg-white"
              defaultValue={
                row.successor_id != null ? String(row.successor_id) : ""
              }
              title="Позиция начнётся после выбранной"
              onChange={(e) =>
                onSave(itemId, {
                  schedule_successor_id:
                    e.target.value === "" ? null : Number(e.target.value),
                })
              }
            >
              <option value="">—</option>
              {succGroups.map((g) => (
                <React.Fragment key={g.key}>
                  <option disabled value={`__sec_${g.key}`}>
                    ── {g.label} ──
                  </option>
                  {g.items.map((po) => (
                    <option key={po.id} value={String(po.id)}>
                      {po.label}
                    </option>
                  ))}
                </React.Fragment>
              ))}
            </select>
          </Cell>
        </div>
      }
      gantt={
        <>
          {bar && (
            <div
              className={`sched-vbar sched-bar absolute top-1/2 -translate-y-1/2 h-[26px] rounded-md flex items-center px-1.5 text-[10px] overflow-hidden whitespace-nowrap cursor-grab active:cursor-grabbing box-border border-2 ${statusBarClass(row.status)}`}
              style={{ left: bar.left, width: bar.width, minWidth: 8 }}
              data-item-id={itemId}
              onMouseDown={onBarMouseDown}
            >
              <span className="truncate">{row.name}</span>
              <div className="sched-bar-resize absolute right-[-4px] top-0 w-2.5 h-full cursor-ew-resize z-[3]" />
            </div>
          )}
        </>
      }
    />
  );
});

function Cell({
  w,
  className,
  children,
  title,
}: {
  w: number;
  className?: string;
  children?: React.ReactNode;
  title?: string;
}) {
  return (
    <div
      className={`px-1 box-border overflow-hidden ${className || ""}`}
      style={{ width: w, flexShrink: 0 }}
      title={title}
    >
      {children}
    </div>
  );
}

export function ScheduleVirtualApp({
  payload,
}: {
  payload: ScheduleVirtualPayload;
}) {
  const [rows, setRows] = useState<ScheduleRow[]>(() =>
    JSON.parse(JSON.stringify(payload.rows)),
  );
  const [zoom, setZoom] = useState<ZoomMode>("day");
  const [colWidths] = useState<number[]>(() => {
    try {
      const saved = JSON.parse(
        localStorage.getItem(`sched-col-widths-${payload.project_id}`) ||
          "null",
      );
      if (Array.isArray(saved) && saved.length === LEFT_COL_DEFAULTS.length) {
        return saved.map((w, i) =>
          Math.max(
            LEFT_COL_MINS[i],
            Number.isFinite(Number(w)) ? Number(w) : LEFT_COL_DEFAULTS[i],
          ),
        );
      }
    } catch {
      /* ignore */
    }
    return [...LEFT_COL_DEFAULTS];
  });
  const [scrollTop, setScrollTop] = useState(0);
  const [scrollLeft, setScrollLeft] = useState(0);
  const listOuterRef = useRef<HTMLDivElement | null>(null);
  const hScrollRef = useRef<HTMLDivElement | null>(null);
  const listRef = useRef<List>(null);
  const shellRef = useRef<HTMLDivElement | null>(null);
  const [listHeight, setListHeight] = useState(420);
  const [viewportW, setViewportW] = useState(800);

  const succCatalog = useMemo(
    () => buildSuccCatalog(payload.rows, payload.succ_catalog),
    [payload.rows, payload.succ_catalog],
  );

  const visibleRows = useMemo(
    () => rows.filter((row) => row.kind !== "task"),
    [rows],
  );

  const range = useMemo(
    () => computeRange(rows, payload.today),
    [rows, payload.today],
  );
  const timelineW = useMemo(
    () => timelineWidth(range, zoom),
    [range, zoom],
  );
  const headCells = useMemo(
    () => buildHeadCells(range, zoom),
    [range, zoom],
  );
  const leftW = leftTotalWidth(colWidths);

  const getItemSize = useCallback(
    (index: number) => rowHeight(visibleRows[index]),
    [visibleRows],
  );

  useEffect(() => {
    listRef.current?.resetAfterIndex(0);
  }, [visibleRows, zoom]);

  useEffect(() => {
    const el = shellRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      setListHeight(Math.max(200, el.clientHeight - HEAD_H - HSCROLL_H));
      setViewportW(el.clientWidth);
    });
    ro.observe(el);
    setListHeight(Math.max(200, el.clientHeight - HEAD_H - HSCROLL_H));
    setViewportW(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    function onZoom(ev: Event) {
      const z = (ev as CustomEvent<string>).detail as ZoomMode;
      if (z === "day" || z === "week" || z === "month") setZoom(z);
    }
    window.addEventListener("metrix-schedule-zoom", onZoom);
    return () => window.removeEventListener("metrix-schedule-zoom", onZoom);
  }, []);

  useEffect(() => {
    function onGotoToday() {
      const hs = hScrollRef.current;
      if (!hs) return;
      const td = parseYMD(payload.today);
      if (!td) return;
      const off = dayOffset(range, td) * pxPerDay(zoom);
      const ganttPaneW = Math.max(0, viewportW - leftW);
      hs.scrollLeft = Math.max(0, off - ganttPaneW / 2);
    }
    const btn = document.getElementById("sched-goto-today");
    btn?.addEventListener("click", onGotoToday);
    return () => btn?.removeEventListener("click", onGotoToday);
  }, [payload.today, range, zoom, viewportW, leftW]);

  const saveItem = useCallback(
    (itemId: number, body: Record<string, unknown>) => {
      fetch(apiUrl(payload.api_url_template, itemId), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": payload.csrf_token,
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify(body),
        credentials: "same-origin",
      })
        .then((r) => r.json().then((j) => ({ r, j })))
        .then(({ r, j }) => {
          if (!r.ok || !j.ok) {
            alert(j.error || j.errors || "Ошибка");
            return;
          }
          setRows((prev) => {
            const next = JSON.parse(JSON.stringify(prev)) as ScheduleRow[];
            type P = {
              id: number;
              schedule_start?: string | null;
              schedule_end?: string | null;
              duration_days?: number | null;
              schedule_status?: string;
              schedule_assignee_id?: number | null;
              schedule_predecessor_id?: number | null;
            };
            const merge = (p: P) => {
              next.forEach((row) => {
                if (row.kind === "item" && row.item_id === p.id) {
                  if (p.schedule_start !== undefined)
                    row.schedule_start = p.schedule_start;
                  if (p.schedule_end !== undefined)
                    row.schedule_end = p.schedule_end;
                  if (p.duration_days !== undefined)
                    row.duration_days = p.duration_days;
                  if (p.schedule_status) row.status = p.schedule_status;
                  if (p.schedule_assignee_id !== undefined)
                    row.assignee_id = p.schedule_assignee_id;
                  if (p.schedule_predecessor_id !== undefined)
                    row.predecessor_id = p.schedule_predecessor_id;
                }
              });
            };
            if (j.item) merge(j.item);
            if (j.schedule_links_updated) {
              (j.schedule_links_updated as P[]).forEach(merge);
            }
            recomputeSuccessorIds(next);
            return next;
          });
        })
        .catch(() => alert("Сеть"));
    },
    [payload.api_url_template, payload.csrf_token],
  );

  const positionRowIndex = useMemo(() => {
    const m: Record<number, number> = {};
    visibleRows.forEach((r, i) => {
      if (r.kind === "item" && r.item_id) {
        m[r.item_id] = i;
      }
    });
    return m;
  }, [visibleRows]);

  const depPaths = useMemo(() => {
    const paths: string[] = [];
    let offsetY = 0;
    visibleRows.forEach((r, index) => {
      const h = rowHeight(r);
      if (r.kind !== "item" || !r.predecessor_id || !r.item_id) {
        offsetY += h;
        return;
      }
      if (!r.schedule_start || !r.schedule_end) {
        offsetY += h;
        return;
      }
      const pi = positionRowIndex[r.predecessor_id];
      if (pi === undefined) {
        offsetY += h;
        return;
      }
      const pred = visibleRows[pi];
      if (
        pred.kind !== "item" ||
        !pred.schedule_start ||
        !pred.schedule_end
      ) {
        offsetY += h;
        return;
      }
      const fromBar = barGeometry(
        range,
        zoom,
        pred.schedule_start,
        pred.schedule_end,
      );
      const toBar = barGeometry(
        range,
        zoom,
        r.schedule_start,
        r.schedule_end,
      );
      if (!fromBar || !toBar) {
        offsetY += h;
        return;
      }
      let fy = 0;
      for (let j = 0; j < pi; j++) fy += rowHeight(visibleRows[j]);
      fy += rowHeight(pred) / 2;
      let ty = 0;
      for (let j = 0; j < index; j++) ty += rowHeight(visibleRows[j]);
      ty += h / 2;
      const fx = fromBar.left + fromBar.width;
      const tx = toBar.left;
      let midx = fx + Math.max(28, Math.min(80, (tx - fx) / 2));
      if (tx <= fx + 4) midx = fx + 36;
      const tipX = Math.max(tx + 1, tx - 3);
      paths.push(
        `M ${fx} ${fy} L ${midx} ${fy} L ${midx} ${ty} L ${tipX} ${ty}`,
      );
      offsetY += h;
    });
    return paths;
  }, [visibleRows, positionRowIndex, range, zoom]);

  const totalContentHeight = useMemo(
    () => visibleRows.reduce((acc, r) => acc + rowHeight(r), 0),
    [visibleRows],
  );

  const OuterElement = useMemo(
    () =>
      forwardRef<HTMLDivElement, React.HTMLProps<HTMLDivElement>>(
        function Outer(props, ref) {
          const { style, onScroll, ...rest } = props;
          return (
            <div
              ref={(node) => {
                listOuterRef.current = node;
                if (typeof ref === "function") ref(node);
                else if (ref) ref.current = node;
              }}
              {...rest}
              style={{ ...style, overflowY: "auto", overflowX: "hidden" }}
              onScroll={(e) => {
                onScroll?.(e);
                setScrollTop(e.currentTarget.scrollTop);
              }}
            />
          );
        },
      ),
    [],
  );

  const InnerElement = useMemo(
    () =>
      forwardRef<HTMLDivElement, React.HTMLProps<HTMLDivElement>>(
        function Inner(props, ref) {
          const { style, ...rest } = props;
          return (
            <div
              ref={ref}
              {...rest}
              style={{
                ...style,
                width: viewportW,
                position: "relative",
              }}
            />
          );
        },
      ),
    [viewportW],
  );

  const Row = useCallback(
    ({ index, style }: ListChildComponentProps) => {
      const row = visibleRows[index];
      const key =
        row.kind === "item"
          ? `i-${row.item_id}-${row.schedule_start}-${row.duration_days}-${row.status}`
          : `${row.kind}-${row.section_id}-${index}`;
      return (
        <div style={style} key={key}>
          {row.kind === "estimate_section" && (
            <EstimateSectionRow
              row={row}
              colWidths={colWidths}
              leftW={leftW}
              viewportW={viewportW}
              timelineW={timelineW}
              scrollLeft={scrollLeft}
            />
          )}
          {row.kind === "item" && (
            <ItemRow
              row={row}
              colWidths={colWidths}
              leftW={leftW}
              viewportW={viewportW}
              timelineW={timelineW}
              scrollLeft={scrollLeft}
              range={range}
              zoom={zoom}
              statusChoices={payload.status_choices}
              assignees={payload.assignees}
              succCatalog={succCatalog}
              onSave={saveItem}
            />
          )}
        </div>
      );
    },
    [
      visibleRows,
      colWidths,
      leftW,
      viewportW,
      scrollLeft,
      timelineW,
      range,
      zoom,
      payload.status_choices,
      payload.assignees,
      succCatalog,
      saveItem,
    ],
  );

  const todayLineLeft = useMemo(() => {
    const td = parseYMD(payload.today);
    if (!td) return null;
    if (cmpTime(td, range.start) < 0 || cmpTime(td, range.end) > 0)
      return null;
    return dayOffset(range, td) * pxPerDay(zoom) + pxPerDay(zoom) / 2;
  }, [payload.today, range, zoom]);

  return (
    <div
      ref={shellRef}
      className="sched-virtual-shell flex flex-col min-h-[420px] max-h-[calc(100vh-220px)] border border-slate-200 rounded-2xl overflow-hidden bg-white shadow-sm"
    >
      <div
        className="flex shrink-0 border-b border-slate-200 bg-slate-50"
        style={{ height: HEAD_H, width: viewportW }}
      >
        <div
          className="flex shrink-0 text-xs font-semibold text-slate-700 border-r border-slate-200 bg-slate-50 relative z-[3]"
          style={{ width: leftW }}
        >
          {LEFT_HEADERS.map((h, i) => (
            <div
              key={h}
              className="px-1 flex items-center overflow-hidden whitespace-nowrap border-r border-slate-200 last:border-r-0"
              style={{ width: colWidths[i] }}
              title={h}
            >
              {h}
            </div>
          ))}
        </div>
        <div
          className="h-full overflow-hidden shrink-0"
          style={{ width: Math.max(0, viewportW - leftW) }}
        >
          <div
            className="flex h-full"
            style={{
              width: timelineW,
              transform: `translateX(-${scrollLeft}px)`,
            }}
          >
            {headCells.map((c, i) => (
              <div
                key={i}
                className="sched-timeline-head-cell shrink-0 border-r border-slate-200 text-[11px] text-slate-500 flex items-center justify-center px-0.5 bg-slate-50"
                style={{ width: c.width }}
              >
                {c.label}
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="relative flex-1 min-h-0 overflow-hidden">
        <List
          ref={listRef}
          height={listHeight}
          width={viewportW}
          itemCount={visibleRows.length}
          itemSize={getItemSize}
          estimatedItemSize={ITEM_ROW_H}
          outerElementType={OuterElement}
          innerElementType={InnerElement}
        >
          {Row}
        </List>
        <div
          className="pointer-events-none absolute top-0 overflow-hidden z-[5]"
          style={{
            left: leftW,
            width: Math.max(0, viewportW - leftW),
            height: listHeight,
          }}
        >
          {todayLineLeft != null && (
            <div
              className="absolute top-0 bottom-0 w-0.5 bg-red-500"
              style={{ left: todayLineLeft - scrollLeft }}
            />
          )}
          <svg
            className="absolute top-0 left-0"
            width={timelineW}
            height={totalContentHeight}
            style={{
              transform: `translate(${-scrollLeft}px, ${-scrollTop}px)`,
            }}
          >
            <defs>
              <marker
                id="sched-v-dep-arrow"
                markerWidth="10"
                markerHeight="10"
                refX="9"
                refY="3"
                orient="auto"
                markerUnits="strokeWidth"
              >
                <path d="M0,0 L0,6 L9,3 z" fill="#475569" />
              </marker>
            </defs>
            {depPaths.map((d, i) => (
              <path
                key={i}
                d={d}
                fill="none"
                stroke="#475569"
                strokeWidth={2}
                strokeLinecap="square"
                markerEnd="url(#sched-v-dep-arrow)"
                opacity={0.92}
              />
            ))}
          </svg>
        </div>
      </div>
      <div
        ref={hScrollRef}
        className="shrink-0 overflow-x-auto overflow-y-hidden border-t border-slate-200 bg-slate-50"
        style={{ height: HSCROLL_H, marginLeft: leftW }}
        onScroll={(e) => setScrollLeft(e.currentTarget.scrollLeft)}
        aria-label="Горизонтальная прокрутка графика"
      >
        <div style={{ width: timelineW, height: 1 }} />
      </div>
    </div>
  );
}
