import React, { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

type Meta = {
  ok: boolean;
  can_edit: boolean;
  warehouses: { id: number; name: string }[];
  categories: { value: string; label: string }[];
  writeoff_reasons: { value: string; label: string }[];
  schedule_phases: { id: number; label: string }[];
};

type StockRow = {
  stock_id: number;
  material_id: number;
  name: string;
  category_display: string;
  unit: string;
  quantity: string;
  price: string;
  total_value: string;
  warehouse_id: number;
  warehouse_name: string;
  status_display: string;
};

type HistRow = {
  id: number;
  date: string;
  movement_type_display: string;
  material_name: string;
  quantity: string;
  unit: string;
  warehouse_from: string | null;
  warehouse_to: string | null;
  comment: string;
  username: string | null;
  writeoff_reason_display: string;
  schedule_phase_label: string | null;
};

type CatMaterial = { id: number; name: string; unit: string; category: string };

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

function fieldCls() {
  return "mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm";
}

function App({ projectId, apiBase }: { projectId: number; apiBase: string }) {
  const base = apiBase || `/api/project/${projectId}/materials`;
  const [mainTab, setMainTab] = useState<"inventory" | "materials" | "history">("inventory");
  const [meta, setMeta] = useState<Meta | null>(null);
  const [metaError, setMetaError] = useState(false);
  const [catalog, setCatalog] = useState<CatMaterial[]>([]);
  const [stocks, setStocks] = useState<StockRow[]>([]);
  const [history, setHistory] = useState<HistRow[]>([]);
  const [toasts, setToasts] = useState<string[]>([]);
  const push = useCallback((m: string) => {
    setToasts((t) => [...t, m]);
    setTimeout(() => setToasts((t) => t.slice(1)), 3200);
  }, []);

  const [q, setQ] = useState("");
  const [wh, setWh] = useState("");
  const [cat, setCat] = useState("");
  const [sort, setSort] = useState("name");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [histType, setHistType] = useState("");

  const [modal, setModal] = useState<
    null | "add" | "in" | "out" | "tr" | "wo"
  >(null);

  useEffect(() => {
    const h = (e: Event) => {
      const d = (e as CustomEvent).detail as "inventory" | "materials" | "history";
      setMainTab(d);
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
      push("Не удалось загрузить настройки материалов");
    }
  }, [base, push]);

  const loadCatalog = useCallback(async () => {
    try {
      const d = await api<{ ok: boolean; materials: CatMaterial[] }>(`${base}/catalog/`);
      if (d.ok) setCatalog(d.materials);
    } catch {
      /* ignore */
    }
  }, [base]);

  const loadStocks = useCallback(async () => {
    const qs = new URLSearchParams();
    if (q.trim()) qs.set("q", q.trim());
    if (wh) qs.set("warehouse", wh);
    if (cat) qs.set("category", cat);
    qs.set("sort", sort);
    qs.set("order", order);
    try {
      const d = await api<{ ok: boolean; stocks: StockRow[] }>(`${base}/stocks/?${qs}`);
      if (d.ok) setStocks(d.stocks);
    } catch {
      push("Ошибка загрузки остатков");
    }
  }, [base, q, wh, cat, sort, order, push]);

  const loadHistory = useCallback(async () => {
    const qs = new URLSearchParams();
    if (histType) qs.set("movement_type", histType);
    try {
      const d = await api<{ ok: boolean; entries: HistRow[] }>(`${base}/history/?${qs}`);
      if (d.ok) setHistory(d.entries);
    } catch {
      push("Ошибка истории");
    }
  }, [base, histType, push]);

  useEffect(() => {
    loadMeta();
    loadCatalog();
  }, [loadMeta, loadCatalog]);

  useEffect(() => {
    if (mainTab === "materials") loadStocks();
  }, [mainTab, loadStocks]);

  useEffect(() => {
    if (mainTab === "history") loadHistory();
  }, [mainTab, loadHistory]);

  if (mainTab === "inventory") return null;

  if (metaError) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-8 text-center text-amber-900 text-sm">
        <p className="font-medium">Материалы не загрузились</p>
        <p className="mt-2 text-amber-800">
          Обновите страницу. Если снова так — проверьте право «Склады: просмотр» и переменную{' '}
          <code className="rounded bg-amber-100 px-1">DJANGO_CSRF_TRUSTED_ORIGINS</code> для вашего домена.
        </p>
      </div>
    );
  }

  if (!meta?.ok) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-slate-500">
        Загрузка модуля материалов…
      </div>
    );
  }

  async function postJson(url: string, body: object) {
    await api(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  return (
    <div className="space-y-4">
      {mainTab === "materials" && (
        <>
          <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm ring-1 ring-slate-100 md:flex-row md:flex-wrap md:items-end">
            <div className="min-w-[180px] flex-1">
              <label className="text-xs font-medium text-slate-500">Поиск</label>
              <input
                className={fieldCls()}
                placeholder="Наименование…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && loadStocks()}
              />
            </div>
            <div className="min-w-[140px]">
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
            <div className="min-w-[140px]">
              <label className="text-xs font-medium text-slate-500">Категория</label>
              <select className={fieldCls()} value={cat} onChange={(e) => setCat(e.target.value)}>
                <option value="">Все</option>
                {meta.categories.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="min-w-[120px]">
              <label className="text-xs font-medium text-slate-500">Сортировка</label>
              <select className={fieldCls()} value={sort} onChange={(e) => setSort(e.target.value)}>
                <option value="name">Наименование</option>
                <option value="category">Категория</option>
                <option value="quantity">Остаток</option>
                <option value="price">Цена</option>
                <option value="total">Стоимость</option>
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
                  onClick={() => setModal("add")}
                  className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700"
                >
                  + Материал
                </button>
                <button
                  type="button"
                  onClick={() => setModal("in")}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
                >
                  Приход
                </button>
                <button
                  type="button"
                  onClick={() => setModal("out")}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
                >
                  Расход
                </button>
                <button
                  type="button"
                  onClick={() => setModal("tr")}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
                >
                  Перемещение
                </button>
                <button
                  type="button"
                  onClick={() => setModal("wo")}
                  className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-800 hover:bg-red-100"
                >
                  Списание
                </button>
              </div>
            )}
          </div>

          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm ring-1 ring-slate-100">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-slate-100 bg-slate-50/80">
                <tr>
                  <th className="px-4 py-3 font-semibold text-slate-700">Наименование</th>
                  <th className="px-4 py-3 font-semibold text-slate-700">Категория</th>
                  <th className="px-4 py-3 font-semibold text-slate-700">Остаток</th>
                  <th className="px-4 py-3 font-semibold text-slate-700">Ед.</th>
                  <th className="px-4 py-3 font-semibold text-slate-700">Цена</th>
                  <th className="px-4 py-3 font-semibold text-slate-700">Стоимость</th>
                  <th className="px-4 py-3 font-semibold text-slate-700">Склад</th>
                  <th className="px-4 py-3 font-semibold text-slate-700">Статус</th>
                </tr>
              </thead>
              <tbody>
                {stocks.map((r) => (
                  <tr key={r.stock_id} className="border-b border-slate-50 hover:bg-slate-50/60">
                    <td className="px-4 py-2.5 font-medium text-slate-900">{r.name}</td>
                    <td className="px-4 py-2.5 text-slate-600">{r.category_display}</td>
                    <td className="px-4 py-2.5 tabular-nums">{r.quantity}</td>
                    <td className="px-4 py-2.5 text-slate-500">{r.unit}</td>
                    <td className="px-4 py-2.5 tabular-nums">{r.price} ₸</td>
                    <td className="px-4 py-2.5 tabular-nums font-medium text-slate-800">
                      {r.total_value} ₸
                    </td>
                    <td className="px-4 py-2.5 text-slate-600">{r.warehouse_name}</td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                          r.status_display === "В наличии"
                            ? "bg-emerald-50 text-emerald-800"
                            : "bg-slate-100 text-slate-600"
                        }`}
                      >
                        {r.status_display}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!stocks.length && (
              <p className="p-8 text-center text-slate-500">Нет строк для отображения</p>
            )}
          </div>
        </>
      )}

      {mainTab === "history" && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-end gap-2 rounded-xl border border-slate-200 bg-white p-4">
            <div>
              <label className="text-xs font-medium text-slate-500">Тип операции</label>
              <select
                className={fieldCls()}
                value={histType}
                onChange={(e) => setHistType(e.target.value)}
              >
                <option value="">Все</option>
                <option value="incoming">Поступление</option>
                <option value="outgoing">Расход на объект</option>
                <option value="transfer">Перемещение</option>
                <option value="writeoff">Списание</option>
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
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b bg-slate-50">
                <tr>
                  <th className="px-4 py-2">Дата</th>
                  <th className="px-4 py-2">Тип</th>
                  <th className="px-4 py-2">Материал</th>
                  <th className="px-4 py-2">Кол-во</th>
                  <th className="px-4 py-2">Склады</th>
                  <th className="px-4 py-2">Этап</th>
                  <th className="px-4 py-2">Пользователь</th>
                  <th className="px-4 py-2">Комментарий</th>
                </tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.id} className="border-b border-slate-100">
                    <td className="whitespace-nowrap px-4 py-2 text-slate-600">{h.date}</td>
                    <td className="px-4 py-2">{h.movement_type_display}</td>
                    <td className="px-4 py-2 font-medium">{h.material_name}</td>
                    <td className="px-4 py-2 tabular-nums">
                      {h.quantity} {h.unit}
                    </td>
                    <td className="px-4 py-2 text-xs text-slate-600">
                      {h.warehouse_from || "—"} → {h.warehouse_to || "—"}
                    </td>
                    <td className="px-4 py-2 text-xs">{h.schedule_phase_label || "—"}</td>
                    <td className="px-4 py-2 text-xs text-slate-500">{h.username || "—"}</td>
                    <td className="max-w-xs truncate px-4 py-2 text-xs text-slate-500">
                      {h.comment}
                      {h.writeoff_reason_display
                        ? ` · ${h.writeoff_reason_display}`
                        : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!history.length && (
              <p className="p-6 text-center text-slate-500">Записей нет</p>
            )}
          </div>
        </div>
      )}

      {modal === "add" && meta.can_edit && (
        <AddMaterialModal
          meta={meta}
          onClose={() => setModal(null)}
          onSave={async (payload) => {
            await postJson(`${base}/create/`, payload);
            push("Материал добавлен");
            setModal(null);
            loadCatalog();
            loadStocks();
          }}
          onError={(e) => push(e.message)}
        />
      )}
      {modal === "in" && meta.can_edit && (
        <OpModal
          title="Приход"
          meta={meta}
          catalog={catalog}
          onClose={() => setModal(null)}
          onSubmit={async (payload) => {
            await postJson(`${base}/incoming/`, payload);
            push("Приход проведён");
            setModal(null);
            loadStocks();
            loadHistory();
          }}
          onError={(e) => push(e.message)}
          showPrice
          showSupplier
          showDate
        />
      )}
      {modal === "out" && meta.can_edit && (
        <OutgoingModal
          meta={meta}
          catalog={catalog}
          projectId={projectId}
          onClose={() => setModal(null)}
          onSubmit={async (payload) => {
            await postJson(`${base}/outgoing/`, payload);
            push("Расход проведён");
            setModal(null);
            loadStocks();
            loadHistory();
          }}
          onError={(e) => push(e.message)}
        />
      )}
      {modal === "tr" && meta.can_edit && (
        <TransferModal
          meta={meta}
          catalog={catalog}
          onClose={() => setModal(null)}
          onSubmit={async (payload) => {
            await postJson(`${base}/transfer/`, payload);
            push("Перемещение выполнено");
            setModal(null);
            loadStocks();
            loadHistory();
          }}
          onError={(e) => push(e.message)}
        />
      )}
      {modal === "wo" && meta.can_edit && (
        <WriteoffModal
          meta={meta}
          catalog={catalog}
          onClose={() => setModal(null)}
          onSubmit={async (payload) => {
            await postJson(`${base}/writeoff/`, payload);
            push("Списание проведено");
            setModal(null);
            loadStocks();
            loadHistory();
          }}
          onError={(e) => push(e.message)}
        />
      )}

      <ToastHost msgs={toasts} />
    </div>
  );
}

function AddMaterialModal({
  meta,
  onClose,
  onSave,
  onError,
}: {
  meta: Meta;
  onClose: () => void;
  onSave: (p: Record<string, unknown>) => Promise<void>;
  onError: (e: Error) => void;
}) {
  const [name, setName] = useState("");
  const [unit, setUnit] = useState("шт");
  const [price, setPrice] = useState("");
  const [initialQty, setInitialQty] = useState("");
  const [warehouseId, setWarehouseId] = useState(String(meta.warehouses[0]?.id || ""));
  const [supplier, setSupplier] = useState("");
  const [description, setDescription] = useState("");
  const [pending, setPending] = useState(false);

  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center bg-slate-900/40 p-4">
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-6 shadow-2xl">
        <h3 className="text-lg font-semibold text-slate-900">Добавить материал</h3>
        <div className="mt-4 grid gap-3">
          <div>
            <label className="text-xs font-medium text-slate-500">Наименование *</label>
            <input className={fieldCls()} value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Ед. измерения</label>
            <input className={fieldCls()} value={unit} onChange={(e) => setUnit(e.target.value)} />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Цена за ед.</label>
            <input className={fieldCls()} value={price} onChange={(e) => setPrice(e.target.value)} type="number" step="0.01" />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Начальный остаток</label>
            <input className={fieldCls()} value={initialQty} onChange={(e) => setInitialQty(e.target.value)} type="number" step="0.0001" />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Склад *</label>
            <select className={fieldCls()} value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}>
              {meta.warehouses.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Поставщик</label>
            <input className={fieldCls()} value={supplier} onChange={(e) => setSupplier(e.target.value)} />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500">Описание</label>
            <textarea className={fieldCls()} rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className="rounded-lg border border-slate-200 px-4 py-2 text-sm" onClick={onClose}>
            Отмена
          </button>
          <button
            type="button"
            disabled={pending}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            onClick={async () => {
              if (!name.trim()) {
                onError(new Error("Укажите наименование"));
                return;
              }
              setPending(true);
              try {
                await onSave({
                  name: name.trim(),
                  category: "material",
                  unit: unit.trim(),
                  unit_price: price,
                  initial_quantity: initialQty || "0",
                  warehouse_id: parseInt(warehouseId, 10),
                  supplier: supplier.trim(),
                  description: description.trim(),
                });
              } catch (e) {
                onError(e instanceof Error ? e : new Error("Ошибка"));
              } finally {
                setPending(false);
              }
            }}
          >
            Сохранить
          </button>
        </div>
      </div>
    </div>
  );
}

function OpModal({
  title,
  meta,
  catalog,
  onClose,
  onSubmit,
  onError,
  showPrice,
  showSupplier,
  showDate,
}: {
  title: string;
  meta: Meta;
  catalog: CatMaterial[];
  onClose: () => void;
  onSubmit: (p: Record<string, unknown>) => Promise<void>;
  onError: (e: Error) => void;
  showPrice?: boolean;
  showSupplier?: boolean;
  showDate?: boolean;
}) {
  const [materialId, setMaterialId] = useState("");
  const [warehouseId, setWarehouseId] = useState(String(meta.warehouses[0]?.id || ""));
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [supplier, setSupplier] = useState("");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [comment, setComment] = useState("");
  const [pending, setPending] = useState(false);

  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center bg-slate-900/40 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
        <h3 className="text-lg font-semibold">{title}</h3>
        <div className="mt-4 grid gap-3">
          <div>
            <label className="text-xs text-slate-500">Материал</label>
            <select className={fieldCls()} value={materialId} onChange={(e) => setMaterialId(e.target.value)}>
              <option value="">—</option>
              {catalog.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500">Склад</label>
            <select className={fieldCls()} value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}>
              {meta.warehouses.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500">Количество</label>
            <input className={fieldCls()} value={quantity} onChange={(e) => setQuantity(e.target.value)} type="number" step="0.0001" />
          </div>
          {showPrice && (
            <div>
              <label className="text-xs text-slate-500">Цена за ед.</label>
              <input className={fieldCls()} value={price} onChange={(e) => setPrice(e.target.value)} type="number" step="0.01" />
            </div>
          )}
          {showSupplier && (
            <div>
              <label className="text-xs text-slate-500">Поставщик</label>
              <input className={fieldCls()} value={supplier} onChange={(e) => setSupplier(e.target.value)} />
            </div>
          )}
          {showDate && (
            <div>
              <label className="text-xs text-slate-500">Дата</label>
              <input className={fieldCls()} type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </div>
          )}
          <div>
            <label className="text-xs text-slate-500">Комментарий</label>
            <input className={fieldCls()} value={comment} onChange={(e) => setComment(e.target.value)} />
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className="rounded-lg border px-4 py-2 text-sm" onClick={onClose}>
            Отмена
          </button>
          <button
            type="button"
            disabled={pending}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-50"
            onClick={async () => {
              if (!materialId || !quantity) {
                onError(new Error("Заполните материал и количество"));
                return;
              }
              setPending(true);
              try {
                const p: Record<string, unknown> = {
                  material_id: parseInt(materialId, 10),
                  warehouse_id: parseInt(warehouseId, 10),
                  quantity,
                  comment: comment.trim(),
                };
                if (showPrice) p.price = price || "0";
                if (showSupplier) p.supplier = supplier.trim();
                if (showDate) p.date = date;
                await onSubmit(p);
              } catch (e) {
                onError(e instanceof Error ? e : new Error("Ошибка"));
              } finally {
                setPending(false);
              }
            }}
          >
            Провести
          </button>
        </div>
      </div>
    </div>
  );
}

function OutgoingModal({
  meta,
  catalog,
  projectId,
  onClose,
  onSubmit,
  onError,
}: {
  meta: Meta;
  catalog: CatMaterial[];
  projectId: number;
  onClose: () => void;
  onSubmit: (p: Record<string, unknown>) => Promise<void>;
  onError: (e: Error) => void;
}) {
  const [materialId, setMaterialId] = useState("");
  const [warehouseId, setWarehouseId] = useState(String(meta.warehouses[0]?.id || ""));
  const [quantity, setQuantity] = useState("");
  const [phaseId, setPhaseId] = useState("");
  const [comment, setComment] = useState("");
  const [pending, setPending] = useState(false);

  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center bg-slate-900/40 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
        <h3 className="text-lg font-semibold">Расход на объект</h3>
        <p className="text-xs text-slate-500">Объект: проект #{projectId}</p>
        <div className="mt-4 grid gap-3">
          <div>
            <label className="text-xs text-slate-500">Материал</label>
            <select className={fieldCls()} value={materialId} onChange={(e) => setMaterialId(e.target.value)}>
              <option value="">—</option>
              {catalog.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500">Склад</label>
            <select className={fieldCls()} value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}>
              {meta.warehouses.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500">Количество</label>
            <input className={fieldCls()} value={quantity} onChange={(e) => setQuantity(e.target.value)} type="number" step="0.0001" />
          </div>
          <div>
            <label className="text-xs text-slate-500">Этап работ</label>
            <select className={fieldCls()} value={phaseId} onChange={(e) => setPhaseId(e.target.value)}>
              <option value="">—</option>
              {meta.schedule_phases.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500">Комментарий</label>
            <input className={fieldCls()} value={comment} onChange={(e) => setComment(e.target.value)} />
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className="rounded-lg border px-4 py-2 text-sm" onClick={onClose}>
            Отмена
          </button>
          <button
            type="button"
            disabled={pending}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white"
            onClick={async () => {
              if (!materialId || !quantity) {
                onError(new Error("Заполните поля"));
                return;
              }
              setPending(true);
              try {
                await onSubmit({
                  material_id: parseInt(materialId, 10),
                  warehouse_id: parseInt(warehouseId, 10),
                  quantity,
                  schedule_phase_id: phaseId ? parseInt(phaseId, 10) : null,
                  comment: comment.trim(),
                });
              } catch (e) {
                onError(e instanceof Error ? e : new Error("Ошибка"));
              } finally {
                setPending(false);
              }
            }}
          >
            Провести
          </button>
        </div>
      </div>
    </div>
  );
}

function TransferModal({
  meta,
  catalog,
  onClose,
  onSubmit,
  onError,
}: {
  meta: Meta;
  catalog: CatMaterial[];
  onClose: () => void;
  onSubmit: (p: Record<string, unknown>) => Promise<void>;
  onError: (e: Error) => void;
}) {
  const [materialId, setMaterialId] = useState("");
  const [fromId, setFromId] = useState(String(meta.warehouses[0]?.id || ""));
  const [toId, setToId] = useState(String(meta.warehouses[1]?.id || meta.warehouses[0]?.id || ""));
  const [quantity, setQuantity] = useState("");
  const [comment, setComment] = useState("");
  const [pending, setPending] = useState(false);

  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center bg-slate-900/40 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
        <h3 className="text-lg font-semibold">Перемещение</h3>
        <div className="mt-4 grid gap-3">
          <div>
            <label className="text-xs text-slate-500">Материал</label>
            <select className={fieldCls()} value={materialId} onChange={(e) => setMaterialId(e.target.value)}>
              <option value="">—</option>
              {catalog.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500">Откуда</label>
            <select className={fieldCls()} value={fromId} onChange={(e) => setFromId(e.target.value)}>
              {meta.warehouses.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500">Куда</label>
            <select className={fieldCls()} value={toId} onChange={(e) => setToId(e.target.value)}>
              {meta.warehouses.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500">Количество</label>
            <input className={fieldCls()} value={quantity} onChange={(e) => setQuantity(e.target.value)} type="number" step="0.0001" />
          </div>
          <div>
            <label className="text-xs text-slate-500">Комментарий</label>
            <input className={fieldCls()} value={comment} onChange={(e) => setComment(e.target.value)} />
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className="rounded-lg border px-4 py-2 text-sm" onClick={onClose}>
            Отмена
          </button>
          <button
            type="button"
            disabled={pending}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white"
            onClick={async () => {
              if (!materialId || !quantity) {
                onError(new Error("Заполните поля"));
                return;
              }
              setPending(true);
              try {
                await onSubmit({
                  material_id: parseInt(materialId, 10),
                  warehouse_from_id: parseInt(fromId, 10),
                  warehouse_to_id: parseInt(toId, 10),
                  quantity,
                  comment: comment.trim(),
                });
              } catch (e) {
                onError(e instanceof Error ? e : new Error("Ошибка"));
              } finally {
                setPending(false);
              }
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
  catalog,
  onClose,
  onSubmit,
  onError,
}: {
  meta: Meta;
  catalog: CatMaterial[];
  onClose: () => void;
  onSubmit: (p: Record<string, unknown>) => Promise<void>;
  onError: (e: Error) => void;
}) {
  const [materialId, setMaterialId] = useState("");
  const [warehouseId, setWarehouseId] = useState(String(meta.warehouses[0]?.id || ""));
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState(meta.writeoff_reasons[0]?.value || "used");
  const [comment, setComment] = useState("");
  const [pending, setPending] = useState(false);

  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center bg-slate-900/40 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
        <h3 className="text-lg font-semibold">Списание</h3>
        <div className="mt-4 grid gap-3">
          <div>
            <label className="text-xs text-slate-500">Материал</label>
            <select className={fieldCls()} value={materialId} onChange={(e) => setMaterialId(e.target.value)}>
              <option value="">—</option>
              {catalog.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500">Склад</label>
            <select className={fieldCls()} value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}>
              {meta.warehouses.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500">Количество</label>
            <input className={fieldCls()} value={quantity} onChange={(e) => setQuantity(e.target.value)} type="number" step="0.0001" />
          </div>
          <div>
            <label className="text-xs text-slate-500">Причина</label>
            <select className={fieldCls()} value={reason} onChange={(e) => setReason(e.target.value)}>
              {meta.writeoff_reasons.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500">Комментарий</label>
            <input className={fieldCls()} value={comment} onChange={(e) => setComment(e.target.value)} />
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className="rounded-lg border px-4 py-2 text-sm" onClick={onClose}>
            Отмена
          </button>
          <button
            type="button"
            disabled={pending}
            className="rounded-lg bg-red-600 px-4 py-2 text-sm text-white"
            onClick={async () => {
              if (!materialId || !quantity) {
                onError(new Error("Заполните поля"));
                return;
              }
              setPending(true);
              try {
                await onSubmit({
                  material_id: parseInt(materialId, 10),
                  warehouse_id: parseInt(warehouseId, 10),
                  quantity,
                  writeoff_reason: reason,
                  comment: comment.trim(),
                });
              } catch (e) {
                onError(e instanceof Error ? e : new Error("Ошибка"));
              } finally {
                setPending(false);
              }
            }}
          >
            Списать
          </button>
        </div>
      </div>
    </div>
  );
}

const el = document.getElementById("project-materials-root");
if (el) {
  const pid = parseInt(el.dataset.projectId || "0", 10);
  const apiBase = (el.dataset.apiBase || "").trim();
  if (pid) createRoot(el).render(<App projectId={pid} apiBase={apiBase} />);
}
