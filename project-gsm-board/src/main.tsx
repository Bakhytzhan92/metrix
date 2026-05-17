import React, { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

type FuelTypeRow = { id: number; code: string; name: string; unit: string };
type WarehouseOpt = { id: number; name: string };
type EquipmentRow = {
  id: number;
  name: string;
  display: string;
  fuel_type_id: number | null;
  status: string;
  project_id: number | null;
  consumption_norm_liters: string;
  consumption_norm_mode: string;
  tank_l: string;
  engine_hours: string;
};
type ProjectOpt = { id: number; name: string };

type FuelCard = {
  fuel_type_id: number;
  code: string;
  name: string;
  unit: string;
  balance: string;
  avg_price: string;
  month_out: string;
  warehouse_hint: string;
  last_issue_date: string;
  last_writeoff_date: string;
  low_balance: boolean;
};

type Meta = {
  ok: boolean;
  can_edit: boolean;
  warehouses: WarehouseOpt[];
  fuel_types: FuelTypeRow[];
  equipment: EquipmentRow[];
  projects: ProjectOpt[];
  fuel_cards?: FuelCard[];
  fuel_alerts?: string[];
  recipient_types: { value: string; label: string }[];
  writeoff_reasons: { value: string; label: string }[];
  movement_types: { value: string; label: string }[];
};

type StockRow = {
  stock_id: number;
  fuel_type_id: number;
  fuel_name: string;
  unit: string;
  quantity: string;
  price: string;
  total_value: string;
  warehouse_id: number;
  warehouse_name: string;
};

type HistEntry = {
  id: number;
  date: string;
  operation_display: string;
  fuel_name: string;
  unit: string;
  quantity: string;
  total: string;
  warehouse_name: string;
  username: string | null;
  comment: string;
  document_number: string;
  supplier: string;
  recipient_display: string;
  issued_to_name: string;
  equipment_name: string;
  equipment_label: string;
  driver_name: string;
  contractor_name: string;
  target_project_name: string;
  writeoff_reason_display: string;
};

type AnalyticsRow = { key: string; label: string; quantity: string };

function csrf(): string {
  const m = document.cookie.match(/csrftoken=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(init?.headers as Record<string, string>),
  };
  const method = (init?.method || "GET").toUpperCase();
  if (method !== "GET" && method !== "HEAD") headers["X-CSRFToken"] = csrf();
  const res = await fetch(path, { ...init, headers, credentials: "same-origin" });
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    const body = (await res.json()) as T & { error?: string };
    if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
    return body as T;
  }
  throw new Error(await res.text());
}

function fieldCls() {
  return "mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm";
}

/** Parses quantity strings from API (may contain spaces as thousands separators). */
function parseQtyString(s: string): number {
  const t = s.replace(/\s/g, "").replace(",", ".");
  const n = parseFloat(t);
  return Number.isFinite(n) ? n : 0;
}

function ToastHost({ msgs }: { msgs: string[] }) {
  if (!msgs.length) return null;
  return (
    <div className="fixed bottom-4 right-4 z-[200] flex max-w-sm flex-col gap-2">
      {msgs.map((m, i) => (
        <div
          key={i}
          className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-800 shadow-lg"
        >
          {m}
        </div>
      ))}
    </div>
  );
}

function App({ projectId, apiBase }: { projectId: number; apiBase: string }) {
  const base = apiBase || `/api/project/${projectId}/gsm`;
  const [mainVisible, setMainVisible] = useState(false);
  const [innerTab, setInnerTab] = useState<"stocks" | "journal" | "analytics">("stocks");
  const [meta, setMeta] = useState<Meta | null>(null);
  const [metaError, setMetaError] = useState(false);
  const [stocks, setStocks] = useState<StockRow[]>([]);
  const [history, setHistory] = useState<HistEntry[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsRow[]>([]);
  const [toasts, setToasts] = useState<string[]>([]);
  const push = useCallback((m: string) => {
    setToasts((t) => [...t, m]);
    setTimeout(() => setToasts((t) => t.slice(1)), 3200);
  }, []);

  const [q, setQ] = useState("");
  const [wh, setWh] = useState("");
  const [ft, setFt] = useState("");
  const [sort, setSort] = useState("fuel");
  const [order, setOrder] = useState<"asc" | "desc">("asc");

  const [histType, setHistType] = useState("");
  const [histFrom, setHistFrom] = useState("");
  const [histTo, setHistTo] = useState("");
  const [histEquip, setHistEquip] = useState("");
  const [histFuel, setHistFuel] = useState("");
  const [histProj, setHistProj] = useState("");

  const [anGroup, setAnGroup] = useState<"project" | "equipment" | "employee" | "contractor">("project");
  const [anFrom, setAnFrom] = useState("");
  const [anTo, setAnTo] = useState("");
  const [tsGran, setTsGran] = useState<"day" | "month">("day");
  const [tsPoints, setTsPoints] = useState<{ key: string; quantity: string }[]>([]);

  const [modal, setModal] = useState<null | "in" | "issue" | "wo" | "ftype">(null);

  useEffect(() => {
    const h = (e: Event) => {
      const d = (e as CustomEvent).detail as string;
      setMainVisible(d === "gsm");
    };
    document.addEventListener("warehouse-main-tab", h);
    return () => document.removeEventListener("warehouse-main-tab", h);
  }, []);

  const loadMeta = useCallback(async () => {
    setMetaError(false);
    try {
      const m = await api<Meta>(`${base}/meta/`);
      if (m.ok) setMeta(m);
      else setMetaError(true);
    } catch {
      setMetaError(true);
      push("Не удалось загрузить ГСМ");
    }
  }, [base, push]);

  const loadStocks = useCallback(async () => {
    const qs = new URLSearchParams();
    if (q.trim()) qs.set("q", q.trim());
    if (wh) qs.set("warehouse", wh);
    if (ft) qs.set("fuel_type", ft);
    qs.set("sort", sort);
    qs.set("order", order);
    try {
      const d = await api<{ ok: boolean; stocks: StockRow[] }>(`${base}/stocks/?${qs}`);
      if (d.ok) setStocks(d.stocks);
    } catch {
      push("Ошибка остатков ГСМ");
    }
  }, [base, q, wh, ft, sort, order, push]);

  const loadHistory = useCallback(async () => {
    const qs = new URLSearchParams();
    if (histType) qs.set("movement_type", histType);
    if (histFrom) qs.set("date_from", histFrom);
    if (histTo) qs.set("date_to", histTo);
    if (histEquip) qs.set("equipment_id", histEquip);
    if (histFuel) qs.set("fuel_type_id", histFuel);
    if (histProj) qs.set("project_id", histProj);
    try {
      const d = await api<{ ok: boolean; entries: HistEntry[] }>(`${base}/history/?${qs}`);
      if (d.ok) setHistory(d.entries);
    } catch {
      push("Ошибка журнала ГСМ");
    }
  }, [base, histType, histFrom, histTo, histEquip, histFuel, histProj, push]);

  const loadTimeseries = useCallback(async () => {
    const qs = new URLSearchParams();
    qs.set("granularity", tsGran);
    if (anFrom) qs.set("date_from", anFrom);
    if (anTo) qs.set("date_to", anTo);
    try {
      const d = await api<{ ok: boolean; points: { key: string; quantity: string }[] }>(
        `${base}/timeseries/?${qs}`,
      );
      if (d.ok) setTsPoints(d.points);
    } catch {
      /* ignore */
    }
  }, [base, tsGran, anFrom, anTo]);

  const loadAnalytics = useCallback(async () => {
    const qs = new URLSearchParams();
    qs.set("group_by", anGroup);
    if (anFrom) qs.set("date_from", anFrom);
    if (anTo) qs.set("date_to", anTo);
    try {
      const d = await api<{ ok: boolean; rows: AnalyticsRow[] }>(`${base}/analytics/?${qs}`);
      if (d.ok) setAnalytics(d.rows);
    } catch {
      push("Ошибка аналитики");
    }
  }, [base, anGroup, anFrom, anTo, push]);

  useEffect(() => {
    if (!mainVisible) return;
    loadMeta();
  }, [mainVisible, loadMeta]);

  useEffect(() => {
    if (!mainVisible || !meta?.ok) return;
    if (innerTab === "stocks") loadStocks();
  }, [mainVisible, meta?.ok, innerTab, loadStocks]);

  useEffect(() => {
    if (!mainVisible || !meta?.ok) return;
    if (innerTab === "journal") loadHistory();
  }, [mainVisible, meta?.ok, innerTab, loadHistory]);

  useEffect(() => {
    if (!mainVisible || !meta?.ok) return;
    if (innerTab === "analytics") {
      loadAnalytics();
      loadTimeseries();
    }
  }, [mainVisible, meta?.ok, innerTab, anGroup, anFrom, anTo, tsGran, loadAnalytics, loadTimeseries]);

  if (!mainVisible) return null;

  if (metaError) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-8 text-center text-sm text-amber-900">
        <p className="font-medium">ГСМ не загрузились</p>
        <p className="mt-2 text-amber-800">Обновите страницу или проверьте права «Склады: просмотр».</p>
      </div>
    );
  }

  if (!meta?.ok) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-slate-500">
        Загрузка модуля ГСМ…
      </div>
    );
  }

  async function postJson<T extends { ok?: boolean } = { ok: boolean }>(
    url: string,
    body: object,
  ): Promise<T> {
    return api<T>(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">
        Учёт топлива отдельно от материалов и инвентаря. Остатки по складам проекта.
      </p>

      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {(
          [
            ["stocks", "Остатки"],
            ["journal", "Журнал"],
            ["analytics", "Аналитика"],
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            type="button"
            onClick={() => setInnerTab(k)}
            className={
              innerTab === k
                ? "-mb-px rounded-t-md border border-b-0 border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-indigo-700"
                : "rounded-t-md border border-transparent px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            }
          >
            {label}
          </button>
        ))}
      </div>

      {innerTab === "stocks" && (
        <>
          <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm md:flex-row md:flex-wrap md:items-end">
            <div className="min-w-[160px] flex-1">
              <label className="text-xs font-medium text-slate-500">Поиск</label>
              <input
                className={fieldCls()}
                placeholder="Вид топлива…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && loadStocks()}
              />
            </div>
            <div className="min-w-[130px]">
              <label className="text-xs font-medium text-slate-500">Склад</label>
              <select className={fieldCls()} value={wh} onChange={(e) => setWh(e.target.value)}>
                <option value="">Все</option>
                {meta.warehouses.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="min-w-[130px]">
              <label className="text-xs font-medium text-slate-500">Топливо</label>
              <select className={fieldCls()} value={ft} onChange={(e) => setFt(e.target.value)}>
                <option value="">Все</option>
                {meta.fuel_types.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="min-w-[120px]">
              <label className="text-xs font-medium text-slate-500">Сортировка</label>
              <select className={fieldCls()} value={sort} onChange={(e) => setSort(e.target.value)}>
                <option value="fuel">Вид топлива</option>
                <option value="quantity">Остаток</option>
                <option value="price">Цена</option>
                <option value="total">Сумма</option>
                <option value="warehouse">Склад</option>
              </select>
            </div>
            <div className="min-w-[100px]">
              <label className="text-xs font-medium text-slate-500">Порядок</label>
              <select
                className={fieldCls()}
                value={order}
                onChange={(e) => setOrder(e.target.value as "asc" | "desc")}
              >
                <option value="asc">По возр.</option>
                <option value="desc">По убыв.</option>
              </select>
            </div>
            <button
              type="button"
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
              onClick={() => loadStocks()}
            >
              Применить
            </button>
            {meta.can_edit && (
              <div className="flex flex-wrap gap-2 md:ml-auto">
                <button
                  type="button"
                  onClick={() => setModal("in")}
                  className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700"
                >
                  Приход ГСМ
                </button>
                <button
                  type="button"
                  onClick={() => setModal("issue")}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
                >
                  Выдать ГСМ
                </button>
                <button
                  type="button"
                  onClick={() => setModal("wo")}
                  className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-800 hover:bg-red-100"
                >
                  Списание
                </button>
                <button
                  type="button"
                  onClick={() => setModal("ftype")}
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
                >
                  + вид топлива
                </button>
              </div>
            )}
          </div>

          {!!meta.fuel_alerts?.length && (
            <div className="space-y-2 rounded-xl border border-amber-200 bg-amber-50/90 p-4 text-sm text-amber-950">
              <p className="font-semibold text-amber-900">Внимание по остаткам</p>
              <ul className="list-inside list-disc space-y-1">
                {meta.fuel_alerts.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            </div>
          )}

          {!!meta.fuel_cards?.length && (
            <div>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium text-slate-800">Сводка по видам топлива</p>
                <a
                  href="/equipment/"
                  className="text-sm font-medium text-indigo-600 hover:text-indigo-800"
                >
                  Справочник проектной техники →
                </a>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {meta.fuel_cards.map((c) => (
                  <div
                    key={c.fuel_type_id}
                    className={`rounded-xl border bg-white p-4 shadow-sm ${
                      c.low_balance ? "border-amber-300 ring-1 ring-amber-200" : "border-slate-200"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-base font-semibold text-slate-900">{c.name}</p>
                        <p className="text-xs text-slate-500">{c.warehouse_hint || "Склад: —"}</p>
                      </div>
                      {c.low_balance && (
                        <span className="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900">
                          мало
                        </span>
                      )}
                    </div>
                    <dl className="mt-3 space-y-1.5 text-sm">
                      <div className="flex justify-between gap-2">
                        <dt className="text-slate-500">Остаток</dt>
                        <dd className="font-medium tabular-nums text-slate-900">
                          {c.balance} {c.unit}
                        </dd>
                      </div>
                      <div className="flex justify-between gap-2">
                        <dt className="text-slate-500">Средняя цена</dt>
                        <dd className="tabular-nums text-slate-800">{c.avg_price} ₸</dd>
                      </div>
                      <div className="flex justify-between gap-2">
                        <dt className="text-slate-500">Расход за месяц</dt>
                        <dd className="tabular-nums text-slate-800">
                          {c.month_out} {c.unit}
                        </dd>
                      </div>
                      <div className="flex justify-between gap-2 text-xs text-slate-500">
                        <dt>Посл. выдача</dt>
                        <dd>{c.last_issue_date || "—"}</dd>
                      </div>
                      <div className="flex justify-between gap-2 text-xs text-slate-500">
                        <dt>Посл. списание</dt>
                        <dd>{c.last_writeoff_date || "—"}</dd>
                      </div>
                    </dl>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-slate-100 bg-slate-50/80">
                <tr>
                  <th className="px-4 py-3 font-semibold text-slate-700">Вид топлива</th>
                  <th className="px-4 py-3 font-semibold text-slate-700">Остаток</th>
                  <th className="px-4 py-3 font-semibold text-slate-700">Ед.</th>
                  <th className="px-4 py-3 font-semibold text-slate-700">Цена</th>
                  <th className="px-4 py-3 font-semibold text-slate-700">Сумма</th>
                  <th className="px-4 py-3 font-semibold text-slate-700">Склад</th>
                </tr>
              </thead>
              <tbody>
                {stocks.map((r) => (
                  <tr key={r.stock_id} className="border-b border-slate-50 hover:bg-slate-50/60">
                    <td className="px-4 py-2.5 font-medium text-slate-900">{r.fuel_name}</td>
                    <td className="px-4 py-2.5 tabular-nums">{r.quantity}</td>
                    <td className="px-4 py-2.5 text-slate-500">{r.unit}</td>
                    <td className="px-4 py-2.5 tabular-nums">{r.price} ₸</td>
                    <td className="px-4 py-2.5 tabular-nums font-medium text-slate-800">
                      {r.total_value} ₸
                    </td>
                    <td className="px-4 py-2.5 text-slate-600">{r.warehouse_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!stocks.length && (
              <p className="p-8 text-center text-slate-500">Нет остатков. Оформите приход ГСМ.</p>
            )}
          </div>
        </>
      )}

      {innerTab === "journal" && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-end gap-2 rounded-xl border border-slate-200 bg-white p-4">
            <div className="min-w-[140px]">
              <label className="text-xs font-medium text-slate-500">Операция</label>
              <select className={fieldCls()} value={histType} onChange={(e) => setHistType(e.target.value)}>
                <option value="">Все</option>
                {meta.movement_types.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500">С</label>
              <input
                type="date"
                className={fieldCls()}
                value={histFrom}
                onChange={(e) => setHistFrom(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500">По</label>
              <input
                type="date"
                className={fieldCls()}
                value={histTo}
                onChange={(e) => setHistTo(e.target.value)}
              />
            </div>
            <div className="min-w-[200px]">
              <label className="text-xs font-medium text-slate-500">Техника</label>
              <select className={fieldCls()} value={histEquip} onChange={(e) => setHistEquip(e.target.value)}>
                <option value="">Все</option>
                {meta.equipment.map((eq) => (
                  <option key={eq.id} value={eq.id}>
                    {eq.display || eq.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="min-w-[160px]">
              <label className="text-xs font-medium text-slate-500">Топливо</label>
              <select className={fieldCls()} value={histFuel} onChange={(e) => setHistFuel(e.target.value)}>
                <option value="">Все</option>
                {meta.fuel_types.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="min-w-[180px]">
              <label className="text-xs font-medium text-slate-500">Объект</label>
              <select className={fieldCls()} value={histProj} onChange={(e) => setHistProj(e.target.value)}>
                <option value="">Все</option>
                {meta.projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
            <button
              type="button"
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white"
              onClick={() => loadHistory()}
            >
              Обновить
            </button>
          </div>
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b bg-slate-50">
                <tr>
                  <th className="px-4 py-2">Дата</th>
                  <th className="px-4 py-2">Операция</th>
                  <th className="px-4 py-2">Топливо</th>
                  <th className="px-4 py-2">Кол-во</th>
                  <th className="px-4 py-2">Сумма</th>
                  <th className="px-4 py-2">Техника</th>
                  <th className="px-4 py-2">Водитель / кому</th>
                  <th className="px-4 py-2">Склад</th>
                  <th className="px-4 py-2">Пользователь</th>
                  <th className="px-4 py-2">Комментарий</th>
                </tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.id} className="border-b border-slate-100">
                    <td className="whitespace-nowrap px-4 py-2 text-slate-600">{h.date}</td>
                    <td className="px-4 py-2">{h.operation_display}</td>
                    <td className="px-4 py-2 font-medium">
                      {h.fuel_name} ({h.unit})
                    </td>
                    <td className="px-4 py-2 tabular-nums">{h.quantity}</td>
                    <td className="px-4 py-2 tabular-nums">{h.total} ₸</td>
                    <td className="max-w-[160px] px-4 py-2 text-xs text-slate-700">
                      {h.equipment_label || h.equipment_name || "—"}
                    </td>
                    <td className="max-w-[140px] px-4 py-2 text-xs text-slate-600">
                      {h.driver_name || h.issued_to_name || "—"}
                    </td>
                    <td className="px-4 py-2 text-xs text-slate-600">{h.warehouse_name}</td>
                    <td className="px-4 py-2 text-xs text-slate-500">{h.username || "—"}</td>
                    <td className="max-w-xs px-4 py-2 text-xs text-slate-500">
                      {h.comment}
                      {h.document_number ? ` · № ${h.document_number}` : ""}
                      {h.supplier ? ` · ${h.supplier}` : ""}
                      {h.recipient_display ? ` · ${h.recipient_display}` : ""}
                      {h.target_project_name ? ` · ${h.target_project_name}` : ""}
                      {h.contractor_name ? ` · ${h.contractor_name}` : ""}
                      {h.writeoff_reason_display ? ` · ${h.writeoff_reason_display}` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!history.length && <p className="p-6 text-center text-slate-500">Записей нет</p>}
          </div>
        </div>
      )}

      {innerTab === "analytics" && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-end gap-2 rounded-xl border border-slate-200 bg-white p-4">
            <div className="min-w-[180px]">
              <label className="text-xs font-medium text-slate-500">Группировка расхода</label>
              <select
                className={fieldCls()}
                value={anGroup}
                onChange={(e) =>
                  setAnGroup(e.target.value as "project" | "equipment" | "employee" | "contractor")
                }
              >
                <option value="project">По объекту</option>
                <option value="equipment">По технике</option>
                <option value="employee">По сотруднику</option>
                <option value="contractor">По подрядчику</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500">Период с</label>
              <input
                type="date"
                className={fieldCls()}
                value={anFrom}
                onChange={(e) => setAnFrom(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500">По</label>
              <input
                type="date"
                className={fieldCls()}
                value={anTo}
                onChange={(e) => setAnTo(e.target.value)}
              />
            </div>
            <div className="min-w-[140px]">
              <label className="text-xs font-medium text-slate-500">График по</label>
              <select
                className={fieldCls()}
                value={tsGran}
                onChange={(e) => setTsGran(e.target.value as "day" | "month")}
              >
                <option value="day">Дням</option>
                <option value="month">Месяцам</option>
              </select>
            </div>
            <button
              type="button"
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white"
              onClick={() => {
                void loadAnalytics();
                void loadTimeseries();
              }}
            >
              Рассчитать
            </button>
          </div>
          <p className="text-xs text-slate-500">
            Учитываются выдачи и списания. Единицы — как в карточке вида топлива (л, м³).
          </p>

          {tsPoints.length > 0 && (
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <p className="text-sm font-medium text-slate-900">Расход по периоду (выдача + списание)</p>
              <div className="mt-4 flex h-40 items-stretch gap-1 overflow-x-auto pb-1 pt-1">
                {(() => {
                  const vals = tsPoints.map((p) => parseQtyString(p.quantity));
                  const mx = Math.max(...vals, 1);
                  const plotH = 128;
                  return tsPoints.map((p, i) => {
                    const v = vals[i];
                    const barH = Math.max(4, Math.round((v / mx) * plotH));
                    return (
                      <div
                        key={p.key + String(i)}
                        className="flex min-w-[18px] flex-1 flex-col items-center justify-end gap-1"
                      >
                        <div
                          className="w-full max-w-[32px] rounded-t bg-indigo-500/90"
                          style={{ height: barH }}
                          title={`${p.key}: ${p.quantity}`}
                        />
                        <span className="max-w-[52px] truncate text-center text-[10px] text-slate-500" title={p.key}>
                          {p.key.length > 5 ? p.key.slice(5) : p.key}
                        </span>
                      </div>
                    );
                  });
                })()}
              </div>
            </div>
          )}

          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b bg-slate-50">
                <tr>
                  <th className="px-4 py-2">Показатель</th>
                  <th className="px-4 py-2 text-right">Количество</th>
                </tr>
              </thead>
              <tbody>
                {analytics.map((r) => (
                  <tr key={r.key + r.label} className="border-b border-slate-100">
                    <td className="px-4 py-2 font-medium text-slate-900">{r.label}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{r.quantity}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!analytics.length && (
              <p className="p-6 text-center text-slate-500">Нет данных за выбранный период</p>
            )}
          </div>
        </div>
      )}

      {modal === "in" && meta.can_edit && (
        <IncomingModal
          meta={meta}
          onClose={() => setModal(null)}
            onSubmit={async (payload) => {
            await postJson(`${base}/incoming/`, payload);
            push("Приход ГСМ проведён");
            setModal(null);
            loadMeta();
            loadStocks();
            loadHistory();
          }}
          onError={(e) => push(e.message)}
        />
      )}
      {modal === "issue" && meta.can_edit && (
        <IssueModal
          meta={meta}
          onClose={() => setModal(null)}
          onSubmit={async (payload) => {
            const r = await postJson<{ ok: boolean; norm_warning?: string }>(`${base}/issue/`, payload);
            if (r.norm_warning) push(r.norm_warning);
            push("Выдача ГСМ проведена");
            setModal(null);
            loadMeta();
            loadStocks();
            loadHistory();
          }}
          onError={(e) => push(e.message)}
        />
      )}
      {modal === "wo" && meta.can_edit && (
        <WriteoffModal
          meta={meta}
          onClose={() => setModal(null)}
          onSubmit={async (payload) => {
            await postJson(`${base}/writeoff/`, payload);
            push("Списание ГСМ проведено");
            setModal(null);
            loadMeta();
            loadStocks();
            loadHistory();
          }}
          onError={(e) => push(e.message)}
        />
      )}
      {modal === "ftype" && meta.can_edit && (
        <AddFuelTypeModal
          onClose={() => setModal(null)}
          onSubmit={async (payload) => {
            const r = await api<{ ok: boolean; fuel_type: FuelTypeRow }>(`${base}/fuel-type/create/`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload),
            });
            if (r.ok && r.fuel_type) {
              setMeta((m) =>
                m
                  ? { ...m, fuel_types: [...m.fuel_types, r.fuel_type].sort((a, b) => a.code.localeCompare(b.code)) }
                  : m,
              );
              push("Вид топлива добавлен");
            }
            setModal(null);
          }}
          onError={(e) => push(e.message)}
        />
      )}

      <ToastHost msgs={toasts} />
    </div>
  );
}

function IncomingModal({
  meta,
  onClose,
  onSubmit,
  onError,
}: {
  meta: Meta;
  onClose: () => void;
  onSubmit: (p: Record<string, unknown>) => Promise<void>;
  onError: (e: Error) => void;
}) {
  const [fuelTypeId, setFuelTypeId] = useState(String(meta.fuel_types[0]?.id || ""));
  const [warehouseId, setWarehouseId] = useState(String(meta.warehouses[0]?.id || ""));
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [supplier, setSupplier] = useState("");
  const [docNo, setDocNo] = useState("");
  const [dt, setDt] = useState(() => new Date().toISOString().slice(0, 10));
  const [comment, setComment] = useState("");
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <button type="button" className="absolute inset-0 bg-slate-900/50" aria-label="Закрыть" onClick={onClose} />
      <div className="relative max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-6 shadow-xl">
        <h3 className="text-lg font-semibold text-slate-900">Приход ГСМ</h3>
        <div className="mt-4 space-y-3">
          <div>
            <label className="text-xs font-medium text-slate-500">Вид топлива</label>
            <select className={fieldCls()} value={fuelTypeId} onChange={(e) => setFuelTypeId(e.target.value)}>
              {meta.fuel_types.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.unit})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Склад</label>
            <select className={fieldCls()} value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}>
              {meta.warehouses.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs font-medium text-slate-500">Количество</label>
              <input className={fieldCls()} value={quantity} onChange={(e) => setQuantity(e.target.value)} />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500">Цена за ед., ₸</label>
              <input className={fieldCls()} value={price} onChange={(e) => setPrice(e.target.value)} />
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Поставщик</label>
            <input className={fieldCls()} value={supplier} onChange={(e) => setSupplier(e.target.value)} />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Номер документа</label>
            <input className={fieldCls()} value={docNo} onChange={(e) => setDocNo(e.target.value)} />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Дата</label>
            <input type="date" className={fieldCls()} value={dt} onChange={(e) => setDt(e.target.value)} />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Комментарий</label>
            <input className={fieldCls()} value={comment} onChange={(e) => setComment(e.target.value)} />
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className="rounded-lg border border-slate-200 px-4 py-2 text-sm" onClick={onClose}>
            Отмена
          </button>
          <button
            type="button"
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white"
            onClick={() =>
              onSubmit({
                fuel_type_id: parseInt(fuelTypeId, 10),
                warehouse_id: parseInt(warehouseId, 10),
                quantity,
                price,
                supplier,
                document_number: docNo,
                date: dt,
                comment,
              }).catch((e: unknown) => onError(e instanceof Error ? e : new Error(String(e))))
            }
          >
            Провести
          </button>
        </div>
      </div>
    </div>
  );
}

function IssueModal({
  meta,
  onClose,
  onSubmit,
  onError,
}: {
  meta: Meta;
  onClose: () => void;
  onSubmit: (p: Record<string, unknown>) => Promise<void>;
  onError: (e: Error) => void;
}) {
  const [dt, setDt] = useState(() => new Date().toISOString().slice(0, 10));
  const [recipientType, setRecipientType] = useState(meta.recipient_types[0]?.value || "equipment");
  const [fuelTypeId, setFuelTypeId] = useState(String(meta.fuel_types[0]?.id || ""));
  const [warehouseId, setWarehouseId] = useState(String(meta.warehouses[0]?.id || ""));
  const [quantity, setQuantity] = useState("");
  const [issuedTo, setIssuedTo] = useState("");
  const [driverName, setDriverName] = useState("");
  const [equipmentId, setEquipmentId] = useState("");
  const [workHours, setWorkHours] = useState("");
  const [targetProjectId, setTargetProjectId] = useState("");
  const [contractor, setContractor] = useState("");
  const [comment, setComment] = useState("");
  const [price, setPrice] = useState("");

  const isEquipRcpt = recipientType === "equipment";

  useEffect(() => {
    if (!equipmentId) return;
    const eq = meta.equipment.find((e) => String(e.id) === equipmentId);
    if (eq?.fuel_type_id) setFuelTypeId(String(eq.fuel_type_id));
  }, [equipmentId, meta.equipment]);

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <button type="button" className="absolute inset-0 bg-slate-900/50" aria-label="Закрыть" onClick={onClose} />
      <div className="relative max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-2xl bg-white p-6 shadow-xl">
        <h3 className="text-lg font-semibold text-slate-900">Выдать ГСМ</h3>
        <div className="mt-4 space-y-3">
          <div>
            <label className="text-xs font-medium text-slate-500">Дата</label>
            <input type="date" className={fieldCls()} value={dt} onChange={(e) => setDt(e.target.value)} />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Кому (тип)</label>
            <select
              className={fieldCls()}
              value={recipientType}
              onChange={(e) => {
                setRecipientType(e.target.value);
                setEquipmentId("");
                setWorkHours("");
              }}
            >
              {meta.recipient_types.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>

          {isEquipRcpt && (
            <div>
              <label className="text-xs font-medium text-slate-500">Техника из справочника</label>
              <select className={fieldCls()} value={equipmentId} onChange={(e) => setEquipmentId(e.target.value)}>
                <option value="">— выберите единицу техники —</option>
                {meta.equipment.map((eq) => (
                  <option key={eq.id} value={eq.id}>
                    {eq.display || eq.name}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-slate-500">
                Ведение справочника:{" "}
                <a href="/equipment/" className="font-medium text-indigo-600 hover:text-indigo-800">
                  Компания → Справочники → Проектная техника
                </a>
                .
              </p>
            </div>
          )}

          {isEquipRcpt && (
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs font-medium text-slate-500">Водитель / ответственный</label>
                <input className={fieldCls()} value={driverName} onChange={(e) => setDriverName(e.target.value)} />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-500">
                  Моточасы (для контроля нормы, опционально)
                </label>
                <input className={fieldCls()} value={workHours} onChange={(e) => setWorkHours(e.target.value)} />
              </div>
            </div>
          )}

          {!isEquipRcpt && (
            <div>
              <label className="text-xs font-medium text-slate-500">Кому выдано (ФИО / название)</label>
              <input className={fieldCls()} value={issuedTo} onChange={(e) => setIssuedTo(e.target.value)} />
            </div>
          )}

          <div>
            <label className="text-xs font-medium text-slate-500">Объект</label>
            <select
              className={fieldCls()}
              value={targetProjectId}
              onChange={(e) => setTargetProjectId(e.target.value)}
            >
              <option value="">—</option>
              {meta.projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-xs font-medium text-slate-500">Вид топлива</label>
            <select className={fieldCls()} value={fuelTypeId} onChange={(e) => setFuelTypeId(e.target.value)}>
              {meta.fuel_types.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Склад</label>
            <select className={fieldCls()} value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}>
              {meta.warehouses.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Количество</label>
            <input className={fieldCls()} value={quantity} onChange={(e) => setQuantity(e.target.value)} />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Цена за ед. (необяз., иначе средняя)</label>
            <input className={fieldCls()} value={price} onChange={(e) => setPrice(e.target.value)} />
          </div>
          {recipientType === "contractor" && (
            <div>
              <label className="text-xs font-medium text-slate-500">Подрядчик</label>
              <input className={fieldCls()} value={contractor} onChange={(e) => setContractor(e.target.value)} />
            </div>
          )}
          <div>
            <label className="text-xs font-medium text-slate-500">Комментарий</label>
            <input className={fieldCls()} value={comment} onChange={(e) => setComment(e.target.value)} />
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className="rounded-lg border border-slate-200 px-4 py-2 text-sm" onClick={onClose}>
            Отмена
          </button>
          <button
            type="button"
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white"
            onClick={() => {
              if (isEquipRcpt && !equipmentId) {
                onError(new Error("Выберите технику из справочника"));
                return;
              }
              const p: Record<string, unknown> = {
                fuel_type_id: parseInt(fuelTypeId, 10),
                warehouse_id: parseInt(warehouseId, 10),
                quantity,
                recipient_type: recipientType,
                issued_to_name: isEquipRcpt ? "" : issuedTo,
                driver_name: isEquipRcpt ? driverName : "",
                equipment_name: "",
                target_project_id: targetProjectId ? parseInt(targetProjectId, 10) : null,
                contractor_name: contractor,
                date: dt,
                comment,
              };
              if (equipmentId) p.equipment_id = parseInt(equipmentId, 10);
              if (price.trim()) p.price = price;
              if (isEquipRcpt && workHours.trim()) p.work_hours = workHours;
              onSubmit(p).catch((e: unknown) => onError(e instanceof Error ? e : new Error(String(e))));
            }}
          >
            Провести
          </button>
        </div>
      </div>
    </div>
  );
}

function WriteoffModal({
  meta,
  onClose,
  onSubmit,
  onError,
}: {
  meta: Meta;
  onClose: () => void;
  onSubmit: (p: Record<string, unknown>) => Promise<void>;
  onError: (e: Error) => void;
}) {
  const [fuelTypeId, setFuelTypeId] = useState(String(meta.fuel_types[0]?.id || ""));
  const [warehouseId, setWarehouseId] = useState(String(meta.warehouses[0]?.id || ""));
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState(meta.writeoff_reasons[0]?.value || "machinery");
  const [dt, setDt] = useState(() => new Date().toISOString().slice(0, 10));
  const [comment, setComment] = useState("");
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <button type="button" className="absolute inset-0 bg-slate-900/50" aria-label="Закрыть" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <h3 className="text-lg font-semibold text-slate-900">Списание ГСМ</h3>
        <div className="mt-4 space-y-3">
          <div>
            <label className="text-xs font-medium text-slate-500">Вид топлива</label>
            <select className={fieldCls()} value={fuelTypeId} onChange={(e) => setFuelTypeId(e.target.value)}>
              {meta.fuel_types.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Склад</label>
            <select className={fieldCls()} value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}>
              {meta.warehouses.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Количество</label>
            <input className={fieldCls()} value={quantity} onChange={(e) => setQuantity(e.target.value)} />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Причина</label>
            <select className={fieldCls()} value={reason} onChange={(e) => setReason(e.target.value)}>
              {meta.writeoff_reasons.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Дата</label>
            <input type="date" className={fieldCls()} value={dt} onChange={(e) => setDt(e.target.value)} />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Комментарий</label>
            <input className={fieldCls()} value={comment} onChange={(e) => setComment(e.target.value)} />
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className="rounded-lg border border-slate-200 px-4 py-2 text-sm" onClick={onClose}>
            Отмена
          </button>
          <button
            type="button"
            className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white"
            onClick={() =>
              onSubmit({
                fuel_type_id: parseInt(fuelTypeId, 10),
                warehouse_id: parseInt(warehouseId, 10),
                quantity,
                writeoff_reason: reason,
                date: dt,
                comment,
              }).catch((e: unknown) => onError(e instanceof Error ? e : new Error(String(e))))
            }
          >
            Списать
          </button>
        </div>
      </div>
    </div>
  );
}

function AddFuelTypeModal({
  onClose,
  onSubmit,
  onError,
}: {
  onClose: () => void;
  onSubmit: (p: { name: string; unit: string }) => Promise<void>;
  onError: (e: Error) => void;
}) {
  const [name, setName] = useState("");
  const [unit, setUnit] = useState("л");
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <button type="button" className="absolute inset-0 bg-slate-900/50" aria-label="Закрыть" onClick={onClose} />
      <div className="relative w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl">
        <h3 className="text-lg font-semibold text-slate-900">Новый вид топлива</h3>
        <div className="mt-4 space-y-3">
          <div>
            <label className="text-xs font-medium text-slate-500">Наименование</label>
            <input className={fieldCls()} value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Ед. изм.</label>
            <input className={fieldCls()} value={unit} onChange={(e) => setUnit(e.target.value)} />
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className="rounded-lg border px-4 py-2 text-sm" onClick={onClose}>
            Отмена
          </button>
          <button
            type="button"
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white"
            onClick={() =>
              onSubmit({ name: name.trim(), unit: unit.trim() || "л" }).catch((e: unknown) =>
                onError(e instanceof Error ? e : new Error(String(e))),
              )
            }
          >
            Добавить
          </button>
        </div>
      </div>
    </div>
  );
}

function mount() {
  const el = document.getElementById("project-gsm-root");
  if (!el) return;
  const projectId = Number(el.getAttribute("data-project-id") || "0");
  const apiBase = el.getAttribute("data-api-base") || "";
  const root = createRoot(el);
  root.render(<App projectId={projectId} apiBase={apiBase} />);
}

mount();
