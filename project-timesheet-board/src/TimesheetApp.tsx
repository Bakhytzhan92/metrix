import React, {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { FixedSizeList as List, type ListChildComponentProps } from "react-window";

import type {
  ChangeLog,
  Employee,
  EmployeeFormData,
  MonthPayload,
  StatusCode,
  StatusMeta,
} from "./types";

const ROW_H = 44;
const LEFT_W = 180;
const MIN_CELL_W = 20;
const HEAD_H = 40;
const GRID_LINE = "#cbd5e1";

/** Ширина одной ячейки дня: растягиваем на всю доступную ширину. */
function fitCellWidth(paneW: number, days: number): number {
  if (paneW <= 0 || days <= 0) return MIN_CELL_W;
  const fitted = paneW / days;
  return fitted >= MIN_CELL_W ? fitted : MIN_CELL_W;
}

const DEFAULT_STATUSES: StatusMeta[] = [
  { code: "present", short: "Я", label: "Явка", color: "#22c55e" },
  { code: "off", short: "В", label: "Выходной", color: "#94a3b8" },
  { code: "vacation", short: "О", label: "Отпуск", color: "#6366f1" },
  { code: "absent", short: "Н", label: "Неявка", color: "#ef4444" },
  { code: "half", short: "П", label: "Полдня", color: "#f59e0b" },
];

function entryKey(employeeId: number, day: number, year: number, month: number) {
  const d = String(day).padStart(2, "0");
  const m = String(month).padStart(2, "0");
  return `${employeeId}:${year}-${m}-${d}`;
}

function statusStyle(code: string, meta: StatusMeta[]): React.CSSProperties {
  const m = meta.find((s) => s.code === code);
  if (!m) return { background: "#fff" };
  return {
    background: `${m.color}22`,
    color: "#0f172a",
    fontWeight: 600,
  };
}

const DayCell = memo(function DayCell({
  employeeId,
  day,
  year,
  month,
  status,
  statusMeta,
  canEdit,
  brush,
  onPick,
  cellW,
  stretch,
}: {
  employeeId: number;
  day: number;
  year: number;
  month: number;
  status: string;
  statusMeta: StatusMeta[];
  canEdit: boolean;
  brush: StatusCode | null;
  onPick: (employeeId: number, day: number, status: StatusCode) => void;
  cellW?: number;
  stretch?: boolean;
}) {
  const sm = statusMeta.find((s) => s.code === status);
  const label = sm?.short || "";

  return (
    <button
      type="button"
      disabled={!canEdit}
      className={`text-xs flex items-center justify-center transition-colors hover:brightness-95 disabled:cursor-default touch-manipulation box-border ${stretch ? "flex-1 min-w-0 w-full" : "shrink-0"}`}
      style={{
        ...(stretch ? {} : { width: cellW }),
        height: ROW_H,
        borderRight: `1px solid ${GRID_LINE}`,
        ...statusStyle(status, statusMeta),
      }}
      title={sm?.label || "Пусто"}
      onClick={() => {
        if (!canEdit) return;
        if (brush) {
          onPick(employeeId, day, brush);
          return;
        }
        const codes = statusMeta.map((s) => s.code).filter(Boolean) as StatusCode[];
        const idx = codes.indexOf(status as StatusCode);
        const next = codes[(idx + 1) % codes.length] || "present";
        onPick(employeeId, day, next);
      }}
    >
      {label}
    </button>
  );
});

const EmployeeRow = memo(function EmployeeRow({
  employee,
  days,
  year,
  month,
  entries,
  statusMeta,
  canEdit,
  brush,
  scrollLeft,
  viewportW,
  cellW,
  stretch,
  onPick,
  onEdit,
}: {
  employee: Employee;
  days: number;
  year: number;
  month: number;
  entries: Record<string, string>;
  statusMeta: StatusMeta[];
  canEdit: boolean;
  brush: StatusCode | null;
  scrollLeft: number;
  viewportW: number;
  cellW: number;
  stretch: boolean;
  onPick: (employeeId: number, day: number, status: StatusCode) => void;
  onEdit: (employee: Employee) => void;
}) {
  const timelineW = stretch ? undefined : days * cellW;
  const paneW = Math.max(0, viewportW - LEFT_W);
  return (
    <div
      className="flex box-border bg-white w-full"
      style={{
        height: ROW_H,
        borderBottom: `1px solid ${GRID_LINE}`,
      }}
    >
      <div
        className="shrink-0 px-1 flex items-center gap-0.5 bg-white z-[2] box-border"
        style={{
          width: LEFT_W,
          height: ROW_H,
          borderRight: `1px solid ${GRID_LINE}`,
        }}
      >
        {canEdit && (
          <button
            type="button"
            className="shrink-0 w-6 h-6 rounded text-slate-400 hover:text-violet-700 hover:bg-violet-50 text-xs"
            title="Редактировать"
            onClick={() => onEdit(employee)}
          >
            ✎
          </button>
        )}
        <button
          type="button"
          className="min-w-0 flex-1 text-left px-1 flex flex-col justify-center disabled:cursor-default"
          disabled={!canEdit}
          onClick={() => canEdit && onEdit(employee)}
          title={`${employee.full_name}\n${employee.position}`}
        >
          <div className="truncate text-xs font-semibold text-slate-900">
            {employee.full_name}
          </div>
          <div className="truncate text-[10px] text-slate-500">
            {employee.position || "—"}
          </div>
        </button>
      </div>
      <div
        className={`overflow-hidden ${stretch ? "flex flex-1 min-w-0" : ""}`}
        style={stretch ? undefined : { width: paneW, height: ROW_H }}
      >
        <div
          className={`flex h-full ${stretch ? "w-full" : ""}`}
          style={
            stretch
              ? undefined
              : {
                  width: timelineW,
                  transform: `translateX(-${scrollLeft}px)`,
                }
          }
        >
          {Array.from({ length: days }, (_, i) => i + 1).map((day) =>
            stretch ? (
              <DayCell
                key={day}
                employeeId={employee.id}
                day={day}
                year={year}
                month={month}
                status={entries[entryKey(employee.id, day, year, month)] || ""}
                statusMeta={statusMeta}
                canEdit={canEdit}
                brush={brush}
                onPick={onPick}
                stretch
              />
            ) : (
              <DayCell
                key={day}
                employeeId={employee.id}
                day={day}
                year={year}
                month={month}
                status={entries[entryKey(employee.id, day, year, month)] || ""}
                statusMeta={statusMeta}
                canEdit={canEdit}
                brush={brush}
                onPick={onPick}
                cellW={cellW}
              />
            ),
          )}
        </div>
      </div>
    </div>
  );
});

const EMPTY_EMPLOYEE_FORM: EmployeeFormData = {
  full_name: "",
  position: "",
  status: "active",
};

function EmployeeModal({
  mode,
  initial,
  saving,
  onClose,
  onSave,
  onRemove,
}: {
  mode: "create" | "edit";
  initial: EmployeeFormData;
  saving: boolean;
  onClose: () => void;
  onSave: (data: EmployeeFormData) => void;
  onRemove?: () => void;
}) {
  const [form, setForm] = useState<EmployeeFormData>(initial);

  useEffect(() => {
    setForm(initial);
  }, [initial]);

  const set = (key: keyof EmployeeFormData, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="fixed inset-0 z-[120] flex items-end sm:items-center justify-center p-0 sm:p-4">
      <button
        type="button"
        className="absolute inset-0 bg-slate-900/45"
        aria-label="Закрыть"
        onClick={onClose}
      />
      <div className="relative w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl bg-white shadow-xl border border-slate-200 p-4 sm:p-5 max-h-[90vh] overflow-y-auto">
        <h3 className="text-base font-semibold text-slate-900">
          {mode === "create" ? "Новый сотрудник" : "Карточка сотрудника"}
        </h3>
        <p className="text-xs text-slate-500 mt-1">
          Изменения сохраняются сразу на сервере.
        </p>
        <div className="mt-4 space-y-3">
          <div>
            <label className="block text-[10px] uppercase tracking-wide text-slate-500 mb-1">
              ФИО *
            </label>
            <input
              value={form.full_name}
              onChange={(e) => set("full_name", e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              placeholder="Иванов Иван Иванович"
              autoFocus
            />
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-wide text-slate-500 mb-1">
              Должность
            </label>
            <input
              value={form.position}
              onChange={(e) => set("position", e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              placeholder="Монтажник"
            />
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-wide text-slate-500 mb-1">
              Статус
            </label>
            <select
              value={form.status}
              onChange={(e) => set("status", e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="active">Активен</option>
              <option value="inactive">Неактивен</option>
            </select>
          </div>
        </div>
        <div className="mt-5 flex flex-wrap gap-2 justify-between">
          <div>
            {mode === "edit" && onRemove && (
              <button
                type="button"
                disabled={saving}
                className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium text-red-700 hover:bg-red-100 disabled:opacity-50"
                onClick={onRemove}
              >
                Убрать с объекта
              </button>
            )}
          </div>
          <div className="flex gap-2 ml-auto">
            <button
              type="button"
              disabled={saving}
              className="rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-600 hover:bg-slate-50"
              onClick={onClose}
            >
              Отмена
            </button>
            <button
              type="button"
              disabled={saving || !form.full_name.trim()}
              className="rounded-lg bg-violet-600 px-4 py-2 text-xs font-medium text-white hover:bg-violet-700 disabled:opacity-50"
              onClick={() => onSave(form)}
            >
              {saving ? "Сохранение…" : "Сохранить"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function TimesheetApp({
  apiBase,
  csrfToken,
}: {
  apiBase: string;
  csrfToken: string;
}) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [payload, setPayload] = useState<MonthPayload | null>(null);
  const [entries, setEntries] = useState<Record<string, string>>({});
  const [brush, setBrush] = useState<StatusCode | null>("present");
  const [scrollLeft, setScrollLeft] = useState(0);
  const [logs, setLogs] = useState<ChangeLog[]>([]);
  const [showLogs, setShowLogs] = useState(false);
  const [employeeModal, setEmployeeModal] = useState<null | "create" | Employee>(null);
  const [employeeSaving, setEmployeeSaving] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const shellRef = useRef<HTMLDivElement>(null);
  const hScrollRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<List>(null);
  const [listH, setListH] = useState(400);
  const [viewportW, setViewportW] = useState(0);
  const saveQueue = useRef<Map<string, StatusCode>>(new Map());
  const saveTimer = useRef<number | null>(null);

  const statusMeta = payload?.statuses?.length ? payload.statuses : DEFAULT_STATUSES;
  const employees = payload?.employees || [];
  const days = payload?.days_in_month || 31;
  const canEdit = payload?.can_edit ?? false;
  const analytics = payload?.analytics;

  const monthValue = `${year}-${String(month).padStart(2, "0")}`;

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const q = new URLSearchParams({
        year: String(year),
        month: String(month),
      });
      const r = await fetch(`${apiBase}/?${q}`, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const j = (await r.json()) as MonthPayload;
      if (!r.ok || !j.ok) throw new Error("load failed");
      setPayload(j);
      setEntries(j.entries || {});
    } catch {
      setError("Не удалось загрузить табель");
    } finally {
      setLoading(false);
    }
  }, [apiBase, year, month]);

  const loadLogs = useCallback(async () => {
    try {
      const r = await fetch(`${apiBase}/logs/?limit=80`, {
        credentials: "same-origin",
      });
      const j = await r.json();
      if (j.ok) setLogs(j.logs || []);
    } catch {
      /* ignore */
    }
  }, [apiBase]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (showLogs) loadLogs();
  }, [showLogs, loadLogs]);

  useEffect(() => {
    const root = rootRef.current;
    const shell = shellRef.current;
    if (!root) return;

    const measure = () => {
      const w = root.clientWidth;
      if (w > 0) setViewportW(w);
      if (shell) {
        setListH(Math.max(200, shell.clientHeight - HEAD_H - 8));
      }
    };

    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(root);
    if (shell) ro.observe(shell);
    window.addEventListener("resize", measure);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [loading, payload, employees.length]);

  const flushSaves = useCallback(async () => {
    const batch = Array.from(saveQueue.current.entries());
    saveQueue.current.clear();
    if (!batch.length) return;
    const updates = batch.map(([key, status]) => {
      const [eid, date] = key.split(":");
      return { employee_id: Number(eid), date, status };
    });
    try {
      await fetch(`${apiBase}/bulk/`, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ updates }),
      });
      loadLogs();
    } catch {
      setError("Ошибка сохранения");
    }
  }, [apiBase, csrfToken, loadLogs]);

  const queueSave = useCallback(
    (employeeId: number, day: number, status: StatusCode) => {
      const key = entryKey(employeeId, day, year, month);
      const fullDate = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      saveQueue.current.set(`${employeeId}:${fullDate}`, status);
      setEntries((prev) => ({ ...prev, [key]: status }));
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
      saveTimer.current = window.setTimeout(() => {
        flushSaves();
      }, 350);
    },
    [year, month, flushSaves],
  );

  const onPick = useCallback(
    (employeeId: number, day: number, status: StatusCode) => {
      queueSave(employeeId, day, status);
    },
    [queueSave],
  );

  const employeeFormInitial = useMemo((): EmployeeFormData => {
    if (employeeModal && employeeModal !== "create") {
      return {
        full_name: employeeModal.full_name,
        position: employeeModal.position,
        status: employeeModal.status === "inactive" ? "inactive" : "active",
      };
    }
    return { ...EMPTY_EMPLOYEE_FORM };
  }, [employeeModal]);

  const saveEmployee = useCallback(
    async (data: EmployeeFormData) => {
      setEmployeeSaving(true);
      setError("");
      try {
        const isEdit = employeeModal && employeeModal !== "create";
        const url = isEdit
          ? `${apiBase}/employees/${employeeModal.id}/`
          : `${apiBase}/employees/`;
        const r = await fetch(url, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken,
            "X-Requested-With": "XMLHttpRequest",
          },
          body: JSON.stringify(data),
        });
        const j = await r.json();
        if (!r.ok || !j.ok) {
          if (j.error === "duplicate_name") {
            throw new Error("Сотрудник с таким ФИО уже есть");
          }
          throw new Error("save failed");
        }
        setEmployeeModal(null);
        await load();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Не удалось сохранить сотрудника");
      } finally {
        setEmployeeSaving(false);
      }
    },
    [apiBase, csrfToken, employeeModal, load],
  );

  const removeEmployee = useCallback(async () => {
    if (!employeeModal || employeeModal === "create") return;
    if (!window.confirm(`Убрать «${employeeModal.full_name}» с объекта?`)) return;
    setEmployeeSaving(true);
    setError("");
    try {
      const r = await fetch(`${apiBase}/employees/${employeeModal.id}/remove/`, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "X-CSRFToken": csrfToken,
          "X-Requested-With": "XMLHttpRequest",
        },
      });
      const j = await r.json();
      if (!r.ok || !j.ok) throw new Error("remove failed");
      setEmployeeModal(null);
      await load();
    } catch {
      setError("Не удалось убрать сотрудника с объекта");
    } finally {
      setEmployeeSaving(false);
    }
  }, [apiBase, csrfToken, employeeModal, load]);

  const onEditEmployee = useCallback((employee: Employee) => {
    setEmployeeModal(employee);
  }, []);

  const paneW = Math.max(0, viewportW - LEFT_W);
  const cellW = fitCellWidth(paneW, days);
  const stretch = paneW > 0 && paneW / days >= MIN_CELL_W;
  const timelineW = days * cellW;
  const needsHScroll = !stretch;
  const gridW = viewportW > 0 ? viewportW : undefined;

  const Row = useCallback(
    ({ index, style }: ListChildComponentProps) => {
      const emp = employees[index];
      return (
        <div style={style}>
          <EmployeeRow
            employee={emp}
            days={days}
            year={year}
            month={month}
            entries={entries}
            statusMeta={statusMeta}
            canEdit={canEdit}
            brush={brush}
            scrollLeft={scrollLeft}
            viewportW={viewportW}
            cellW={cellW}
            stretch={stretch}
            onPick={onPick}
            onEdit={onEditEmployee}
          />
        </div>
      );
    },
    [
      employees,
      days,
      year,
      month,
      entries,
      statusMeta,
      canEdit,
      brush,
      scrollLeft,
      viewportW,
      cellW,
      stretch,
      onPick,
      onEditEmployee,
    ],
  );

  const weekdayLabels = useMemo(() => {
    return Array.from({ length: days }, (_, i) => {
      const d = new Date(year, month - 1, i + 1);
      return ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"][d.getDay()];
    });
  }, [days, year, month]);

  if (loading && !payload) {
    return (
      <div
        ref={rootRef}
        className="flex items-center justify-center w-full h-48 text-sm text-slate-500 min-h-[480px]"
      >
        Загрузка табеля…
      </div>
    );
  }

  return (
    <div
      ref={rootRef}
      className="flex flex-col w-full h-full min-h-[480px] bg-gradient-to-b from-violet-50/40 to-white"
    >
      {/* Toolbar */}
      <div className="p-3 sm:p-4 border-b border-slate-200 space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-[10px] uppercase tracking-wide text-slate-500 mb-1">
              Месяц
            </label>
            <input
              type="month"
              value={monthValue}
              onChange={(e) => {
                const [y, m] = e.target.value.split("-");
                if (y && m) {
                  setYear(Number(y));
                  setMonth(Number(m));
                }
              }}
              className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            />
          </div>
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-[10px] uppercase text-slate-500 mr-1">Кисть:</span>
            {statusMeta.map((s) => (
              <button
                key={s.code}
                type="button"
                disabled={!canEdit}
                className={`px-2 py-1 rounded-md text-xs font-bold border transition-all touch-manipulation ${
                  brush === s.code
                    ? "ring-2 ring-violet-500 border-violet-400"
                    : "border-slate-200"
                }`}
                style={{ background: `${s.color}33` }}
                onClick={() =>
                  setBrush((prev) => (prev === s.code ? null : (s.code as StatusCode)))
                }
                title={s.label}
              >
                {s.short}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2 ml-auto">
            {canEdit && (
              <button
                type="button"
                className="rounded-lg border border-violet-300 bg-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-700"
                onClick={() => setEmployeeModal("create")}
              >
                + Сотрудник
              </button>
            )}
            <a
              href={`${apiBase}/export/?year=${year}&month=${month}`}
              className="rounded-lg border border-violet-200 bg-violet-50 px-3 py-1.5 text-xs font-medium text-violet-800 hover:bg-violet-100"
            >
              Экспорт Excel
            </a>
            {canEdit && (
              <label className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 cursor-pointer">
                Импорт сотрудников
                <input
                  type="file"
                  accept=".xlsx,.xls"
                  className="hidden"
                  onChange={async (e) => {
                    const f = e.target.files?.[0];
                    if (!f) return;
                    const fd = new FormData();
                    fd.append("file", f);
                    await fetch(`${apiBase}/import-employees/`, {
                      method: "POST",
                      credentials: "same-origin",
                      headers: {
                        "X-CSRFToken": csrfToken,
                        "X-Requested-With": "XMLHttpRequest",
                      },
                      body: fd,
                    });
                    e.target.value = "";
                    load();
                  }}
                />
              </label>
            )}
            <button
              type="button"
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
              onClick={() => setShowLogs((v) => !v)}
            >
              Журнал
            </button>
          </div>
        </div>

        {analytics && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div className="rounded-xl border border-slate-200 bg-white px-3 py-2">
              <div className="text-[10px] text-slate-500">Всего работников</div>
              <div className="text-lg font-semibold tabular-nums">{analytics.total_workers}</div>
            </div>
            <div className="rounded-xl border border-emerald-100 bg-emerald-50/60 px-3 py-2">
              <div className="text-[10px] text-emerald-800">Сегодня на объекте</div>
              <div className="text-lg font-semibold tabular-nums text-emerald-900">
                {analytics.on_site_today}
              </div>
            </div>
            <div className="rounded-xl border border-red-100 bg-red-50/60 px-3 py-2">
              <div className="text-[10px] text-red-800">Отсутствуют</div>
              <div className="text-lg font-semibold tabular-nums text-red-900">
                {analytics.absent_today}
              </div>
            </div>
            <div className="rounded-xl border border-violet-100 bg-violet-50/60 px-3 py-2">
              <div className="text-[10px] text-violet-800">Посещаемость</div>
              <div className="text-lg font-semibold tabular-nums text-violet-900">
                {analytics.attendance_pct}%
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        {showLogs && (
          <div className="max-h-40 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 text-xs">
            <table className="min-w-full">
              <thead className="bg-slate-100 sticky top-0">
                <tr>
                  <th className="px-2 py-1 text-left">Когда</th>
                  <th className="px-2 py-1 text-left">Кто</th>
                  <th className="px-2 py-1 text-left">Сотрудник</th>
                  <th className="px-2 py-1 text-left">Дата</th>
                  <th className="px-2 py-1 text-left">Изм.</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((lg) => (
                  <tr key={lg.id} className="border-t border-slate-200">
                    <td className="px-2 py-1 whitespace-nowrap">{lg.edited_at.slice(0, 16).replace("T", " ")}</td>
                    <td className="px-2 py-1">{lg.edited_by || "—"}</td>
                    <td className="px-2 py-1">{lg.employee_name}</td>
                    <td className="px-2 py-1">{lg.date}</td>
                    <td className="px-2 py-1">
                      {lg.old_short || "—"} → {lg.new_short || "—"}
                    </td>
                  </tr>
                ))}
                {!logs.length && (
                  <tr>
                    <td colSpan={5} className="px-2 py-3 text-slate-500 text-center">
                      Изменений пока нет
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Grid */}
      <div ref={shellRef} className="flex-1 min-h-0 flex flex-col w-full">
        {!employees.length ? (
          <div className="p-8 text-center text-sm text-slate-500 space-y-3">
            <p>Нет сотрудников на объекте.</p>
            {canEdit ? (
              <button
                type="button"
                className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700"
                onClick={() => setEmployeeModal("create")}
              >
                Добавить сотрудника
              </button>
            ) : (
              <p className="text-xs">Импортируйте список из Excel или попросите прораба добавить работников.</p>
            )}
          </div>
        ) : (
          <>
            <div
              className="flex shrink-0 bg-slate-50 w-full box-border"
              style={{
                height: HEAD_H,
                borderBottom: `1px solid ${GRID_LINE}`,
              }}
            >
              <div
                className="shrink-0 px-2 flex items-center text-xs font-semibold text-slate-700 bg-slate-50 box-border"
                style={{
                  width: LEFT_W,
                  borderRight: `1px solid ${GRID_LINE}`,
                }}
              >
                ФИО
              </div>
              <div
                className={`overflow-hidden ${stretch ? "flex flex-1 min-w-0" : ""}`}
                style={stretch ? undefined : { width: paneW }}
              >
                <div
                  className={`flex h-full ${stretch ? "w-full" : ""}`}
                  style={
                    stretch
                      ? undefined
                      : {
                          width: timelineW,
                          transform: `translateX(-${scrollLeft}px)`,
                        }
                  }
                >
                  {Array.from({ length: days }, (_, i) => i + 1).map((day) =>
                    stretch ? (
                      <div
                        key={day}
                        className="flex-1 min-w-0 flex flex-col items-center justify-center text-[10px] text-slate-600 box-border"
                        style={{
                          height: HEAD_H,
                          borderRight: `1px solid ${GRID_LINE}`,
                        }}
                        title={weekdayLabels[day - 1]}
                      >
                        <span className="font-semibold">{day}</span>
                        <span className="text-[9px] text-slate-400">{weekdayLabels[day - 1]}</span>
                      </div>
                    ) : (
                      <div
                        key={day}
                        className="shrink-0 flex flex-col items-center justify-center text-[10px] text-slate-600 box-border"
                        style={{
                          width: cellW,
                          height: HEAD_H,
                          borderRight: `1px solid ${GRID_LINE}`,
                        }}
                        title={weekdayLabels[day - 1]}
                      >
                        <span className="font-semibold">{day}</span>
                        <span className="text-[9px] text-slate-400">{weekdayLabels[day - 1]}</span>
                      </div>
                    ),
                  )}
                </div>
              </div>
            </div>
            <div className="flex-1 min-h-0 w-full">
              {gridW ? (
              <List
                ref={listRef}
                height={listH}
                width={gridW}
                itemCount={employees.length}
                itemSize={ROW_H}
                overscanCount={8}
              >
                {Row}
              </List>
              ) : null}
            </div>
            <div
              ref={hScrollRef}
              className="shrink-0 overflow-x-auto overflow-y-hidden border-t border-slate-200 bg-slate-50"
              style={{ height: needsHScroll ? 16 : 0, marginLeft: LEFT_W }}
              onScroll={(e) => setScrollLeft(e.currentTarget.scrollLeft)}
            >
              <div style={{ width: timelineW, height: 1 }} />
            </div>
          </>
        )}
      </div>

      {employeeModal && (
        <EmployeeModal
          mode={employeeModal === "create" ? "create" : "edit"}
          initial={employeeFormInitial}
          saving={employeeSaving}
          onClose={() => !employeeSaving && setEmployeeModal(null)}
          onSave={saveEmployee}
          onRemove={employeeModal !== "create" ? removeEmployee : undefined}
        />
      )}
    </div>
  );
}
