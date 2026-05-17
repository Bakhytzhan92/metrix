import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";

type Meta = {
  ok: boolean;
  can_edit: boolean;
  show_prices: boolean;
  status_choices: { value: string; label: string }[];
  warehouses: { id: number; name: string; project_id: number | null }[];
  projects: { id: number; name: string }[];
  users: { id: number; username: string; label: string }[];
};

type Item = {
  id: number;
  name: string;
  category: string;
  inventory_number: string;
  serial_number: string;
  status: string;
  status_display: string;
  warehouse_id: number;
  warehouse_name: string;
  project_id: number | null;
  responsible_user_id: number | null;
  assigned_to_id: number | null;
  purchase_price?: string;
  purchase_date: string | null;
  warranty_until: string | null;
  description: string;
  comment: string;
  image_url: string | null;
  qr_url: string | null;
  issued_at: string | null;
  return_due_at: string | null;
};

function csrf(): string {
  const m = document.cookie.match(/csrftoken=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

async function api<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(init?.headers as Record<string, string>),
  };
  const method = (init?.method || "GET").toUpperCase();
  if (method !== "GET" && method !== "HEAD") {
    headers["X-CSRFToken"] = csrf();
  }
  const res = await fetch(path, {
    ...init,
    headers,
    credentials: "same-origin",
  });
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    return (await res.json()) as T;
  }
  throw new Error(await res.text());
}

const statusColor: Record<string, string> = {
  free: "bg-emerald-500",
  in_use: "bg-sky-500",
  issued: "bg-violet-500",
  repair: "bg-amber-500",
  written_off: "bg-red-600",
  lost: "bg-rose-900",
};

function Card({
  item,
  showPrices,
  onOpen,
}: {
  item: Item;
  showPrices: boolean;
  onOpen: (i: Item) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `item-${item.id}`,
    data: { item },
  });
  const style = transform
    ? { transform: `translate3d(${transform.x}px,${transform.y}px,0)` }
    : undefined;
  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`rounded-lg border border-slate-200 bg-white p-3 shadow-sm hover:shadow-md ${
        isDragging ? "opacity-60" : ""
      }`}
    >
      <div className="flex gap-2">
        <button
          type="button"
          className="cursor-grab touch-none select-none px-0.5 text-slate-400 hover:text-slate-600"
          title="Перетащить"
          {...listeners}
          {...attributes}
        >
          ⣿
        </button>
        <div
          className={`h-10 w-1 rounded-full shrink-0 ${statusColor[item.status] || "bg-slate-300"}`}
        />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-slate-900">{item.name}</p>
          <p className="text-xs text-slate-500">{item.inventory_number || "—"}</p>
          {showPrices && item.purchase_price !== undefined && (
            <p className="text-xs font-medium text-slate-700">{item.purchase_price} ₸</p>
          )}
        </div>
        <button
          type="button"
          className="shrink-0 text-xs font-medium text-indigo-600 hover:text-indigo-800"
          onClick={() => onOpen(item)}
        >
          →
        </button>
      </div>
    </div>
  );
}

function ColumnDrop({
  wh,
  children,
}: {
  wh: { id: number; name: string };
  children: React.ReactNode;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: `wh-${wh.id}` });
  return (
    <div
      ref={setNodeRef}
      className={`flex w-72 shrink-0 flex-col rounded-xl border bg-slate-50/80 p-3 ${
        isOver ? "border-emerald-400 ring-2 ring-emerald-100" : "border-slate-200"
      }`}
    >
      <h3 className="mb-3 flex items-center gap-2 border-b border-slate-200 pb-2 text-sm font-semibold text-slate-800">
        <span className="text-slate-400">▣</span>
        {wh.name}
      </h3>
      <div className="flex flex-1 flex-col gap-2 overflow-y-auto">{children}</div>
    </div>
  );
}

function ToastHost({ msgs }: { msgs: string[] }) {
  if (!msgs.length) return null;
  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2">
      {msgs.map((m, i) => (
        <div
          key={i}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white shadow-lg"
        >
          {m}
        </div>
      ))}
    </div>
  );
}

function App() {
  const [tab, setTab] = useState<"board" | "list" | "history">("board");
  const [meta, setMeta] = useState<Meta | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [q, setQ] = useState("");
  const [whFilter, setWhFilter] = useState("");
  const [stFilter, setStFilter] = useState("");
  const [toasts, setToasts] = useState<string[]>([]);
  const [activeDrag, setActiveDrag] = useState<Item | null>(null);
  const [modal, setModal] = useState<"add" | "detail" | null>(null);
  const [selected, setSelected] = useState<Item | null>(null);
  const [detailHist, setDetailHist] = useState<any[]>([]);
  const [form, setForm] = useState({
    name: "",
    warehouse_id: "",
    project_id: "",
    responsible_user_id: "",
    serial_number: "",
    purchase_price: "",
    purchase_date: "",
    warranty_until: "",
    description: "",
    comment: "",
    status: "free",
  });

  const pushToast = useCallback((m: string) => {
    setToasts((t) => [...t, m]);
    setTimeout(() => setToasts((t) => t.slice(1)), 3200);
  }, []);

  const reloadItems = useCallback(async () => {
    const qs = new URLSearchParams();
    if (q) qs.set("q", q);
    if (whFilter) qs.set("warehouse", whFilter);
    if (stFilter) qs.set("status", stFilter);
    const data = await api<{ ok: boolean; items: Item[] }>(
      `/api/inventory/items/?${qs}`,
    );
    if (data.ok) setItems(data.items);
  }, [q, whFilter, stFilter]);

  const reloadHistory = useCallback(async () => {
    const data = await api<{ ok: boolean; entries: any[] }>("/api/inventory/history/");
    if (data.ok) setHistory(data.entries);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const m = await api<Meta>("/api/inventory/meta/");
        if (m.ok) setMeta(m);
      } catch (e) {
        pushToast("Не удалось загрузить настройки");
      }
    })();
  }, [pushToast]);

  useEffect(() => {
    reloadItems().catch(() => pushToast("Ошибка списка"));
  }, [reloadItems, pushToast]);

  useEffect(() => {
    if (tab === "history") reloadHistory().catch(() => {});
  }, [tab, reloadHistory]);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  const byWarehouse = useMemo(() => {
    const map = new Map<number, Item[]>();
    for (const it of items) {
      const arr = map.get(it.warehouse_id) || [];
      arr.push(it);
      map.set(it.warehouse_id, arr);
    }
    return map;
  }, [items]);

  const onDragEnd = async (e: DragEndEvent) => {
    setActiveDrag(null);
    const over = e.over;
    const active = e.active;
    if (!over || !active.id.toString().startsWith("item-")) return;
    const overId = over.id.toString();
    if (!overId.startsWith("wh-")) return;
    const toWh = parseInt(overId.slice(3), 10);
    const itemId = parseInt(active.id.toString().slice(5), 10);
    const it = items.find((i) => i.id === itemId);
    if (!it || it.warehouse_id === toWh) return;
    try {
      const r = await api<{ ok: boolean }>(`/api/inventory/items/${itemId}/move/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to_warehouse_id: toWh, comment: "Перетаскивание" }),
      });
      if (r.ok) {
        pushToast("Перемещено");
        reloadItems();
      }
    } catch {
      pushToast("Ошибка перемещения");
    }
  };

  const openDetail = async (it: Item) => {
    setSelected(it);
    setModal("detail");
    try {
      const d = await api<{ ok: boolean; history: any[] }>(`/api/inventory/items/${it.id}/`);
      if (d.ok) setDetailHist(d.history);
    } catch {
      setDetailHist([]);
    }
  };

  const saveNewItem = async () => {
    if (!form.name.trim() || !form.warehouse_id) {
      pushToast("Укажите название и склад");
      return;
    }
    try {
      const body = {
        name: form.name.trim(),
        warehouse_id: parseInt(form.warehouse_id, 10),
        project_id: form.project_id ? parseInt(form.project_id, 10) : null,
        responsible_user_id: form.responsible_user_id
          ? parseInt(form.responsible_user_id, 10)
          : null,
        serial_number: form.serial_number,
        purchase_price: form.purchase_price || "0",
        purchase_date: form.purchase_date || null,
        warranty_until: form.warranty_until || null,
        description: form.description,
        comment: form.comment,
        status: form.status,
      };
      const r = await api<{ ok: boolean }>("/api/inventory/items/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (r.ok) {
        pushToast("Инвентарь добавлен");
        setModal(null);
        setForm({
          name: "",
          warehouse_id: form.warehouse_id,
          project_id: "",
          responsible_user_id: "",
          serial_number: "",
          purchase_price: "",
          purchase_date: "",
          warranty_until: "",
          description: "",
          comment: "",
          status: "free",
        });
        reloadItems();
      }
    } catch {
      pushToast("Ошибка сохранения");
    }
  };

  if (!meta?.ok) {
    return (
      <div className="flex h-64 items-center justify-center text-slate-500">
        Загрузка…
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1600px] space-y-4 px-4 pb-12">
      <div className="flex flex-col gap-3 border-b border-slate-200 pb-4 pt-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            Инвентарь
          </h1>
          <p className="text-sm text-slate-500">
            Оборудование и инструмент. Материалы (сыпучие, расходники) — в проекте, вкладка «Материалы».
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {meta.can_edit && (
            <>
              <button
                type="button"
                onClick={async () => {
                  const name = window.prompt("Название склада");
                  if (!name?.trim()) return;
                  try {
                    const r = await api<{ ok: boolean }>("/api/inventory/warehouses/", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ name: name.trim() }),
                    });
                    if (r.ok) {
                      pushToast("Склад создан");
                      const m = await api<Meta>("/api/inventory/meta/");
                      if (m.ok) setMeta(m);
                      reloadItems();
                    }
                  } catch {
                    pushToast("Ошибка");
                  }
                }}
                className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-800 shadow-sm hover:bg-slate-50"
              >
                Создать склад
              </button>
              <button
                type="button"
                onClick={() => setModal("add")}
                className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-emerald-700"
              >
                + Инвентарь
              </button>
            </>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3 rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-100">
        <input
          className="min-w-[200px] flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
          placeholder="Поиск…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
          value={whFilter}
          onChange={(e) => setWhFilter(e.target.value)}
        >
          <option value="">Все склады</option>
          {meta.warehouses.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
        <select
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
          value={stFilter}
          onChange={(e) => setStFilter(e.target.value)}
        >
          <option value="">Все статусы</option>
          {meta.status_choices.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900"
          onClick={() => reloadItems()}
        >
          Обновить
        </button>
      </div>

      <div className="flex gap-2 border-b border-slate-200 text-sm">
        {(
          [
            ["board", "Склады"],
            ["list", "Инвентарь"],
            ["history", "История"],
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            type="button"
            onClick={() => setTab(k)}
            className={`border-b-2 px-3 py-2 font-medium ${
              tab === k
                ? "border-emerald-600 text-emerald-800"
                : "border-transparent text-slate-600 hover:text-slate-900"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "board" && (
        <DndContext
          sensors={sensors}
          onDragStart={(ev) => {
            const id = ev.active.id.toString();
            if (id.startsWith("item-")) {
              const iid = parseInt(id.slice(5), 10);
              setActiveDrag(items.find((i) => i.id === iid) || null);
            }
          }}
          onDragEnd={onDragEnd}
        >
          <div className="flex gap-4 overflow-x-auto pb-6">
            {meta.warehouses.map((wh) => (
              <ColumnDrop key={wh.id} wh={wh}>
                {(byWarehouse.get(wh.id) || []).map((it) => (
                  <Card
                    key={it.id}
                    item={it}
                    showPrices={meta.show_prices}
                    onOpen={openDetail}
                  />
                ))}
              </ColumnDrop>
            ))}
          </div>
          <DragOverlay>
            {activeDrag ? (
              <div className="rounded-lg border border-emerald-300 bg-white p-3 opacity-90 shadow-xl">
                <p className="text-sm font-medium">{activeDrag.name}</p>
              </div>
            ) : null}
          </DragOverlay>
        </DndContext>
      )}

      {tab === "list" && (
        <div className="overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-slate-100">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50">
              <tr>
                <th className="px-4 py-2">№</th>
                <th className="px-4 py-2">Наименование</th>
                <th className="px-4 py-2">Статус</th>
                <th className="px-4 py-2">Склад</th>
                {meta.show_prices && <th className="px-4 py-2">Стоимость</th>}
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr
                  key={it.id}
                  className="cursor-pointer border-b border-slate-100 hover:bg-slate-50"
                  onClick={() => openDetail(it)}
                >
                  <td className="px-4 py-2 font-mono text-xs">{it.inventory_number}</td>
                  <td className="px-4 py-2 font-medium text-slate-900">{it.name}</td>
                  <td className="px-4 py-2">{it.status_display}</td>
                  <td className="px-4 py-2 text-slate-600">{it.warehouse_name}</td>
                  {meta.show_prices && (
                    <td className="px-4 py-2">{it.purchase_price} ₸</td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "history" && (
        <div className="overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-slate-100">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b bg-slate-50">
              <tr>
                <th className="px-4 py-2">Когда</th>
                <th className="px-4 py-2">Позиция</th>
                <th className="px-4 py-2">Действие</th>
                <th className="px-4 py-2">Кто</th>
              </tr>
            </thead>
            <tbody>
              {history.map((h) => (
                <tr key={h.id} className="border-b border-slate-100">
                  <td className="whitespace-nowrap px-4 py-2 text-slate-600">
                    {h.created_at?.replace("T", " ").slice(0, 16)}
                  </td>
                  <td className="px-4 py-2">{h.item_name}</td>
                  <td className="px-4 py-2">{h.action_display}</td>
                  <td className="px-4 py-2 text-slate-600">{h.username || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modal === "add" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-6 shadow-xl">
            <h2 className="mb-4 text-lg font-semibold">Новая единица</h2>
            <div className="grid gap-3">
              <input
                className="rounded-lg border px-3 py-2 text-sm"
                placeholder="Название *"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
              <select
                className="rounded-lg border px-3 py-2 text-sm"
                value={form.warehouse_id}
                onChange={(e) => setForm({ ...form, warehouse_id: e.target.value })}
              >
                <option value="">Склад *</option>
                {meta.warehouses.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
              </select>
              <select
                className="rounded-lg border px-3 py-2 text-sm"
                value={form.project_id}
                onChange={(e) => setForm({ ...form, project_id: e.target.value })}
              >
                <option value="">Проект</option>
                {meta.projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <select
                className="rounded-lg border px-3 py-2 text-sm"
                value={form.responsible_user_id}
                onChange={(e) =>
                  setForm({ ...form, responsible_user_id: e.target.value })
                }
              >
                <option value="">Ответственный</option>
                {meta.users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.label}
                  </option>
                ))}
              </select>
              <input
                className="rounded-lg border px-3 py-2 text-sm"
                placeholder="Серийный номер"
                value={form.serial_number}
                onChange={(e) => setForm({ ...form, serial_number: e.target.value })}
              />
              {meta.show_prices && (
                <input
                  className="rounded-lg border px-3 py-2 text-sm"
                  placeholder="Стоимость"
                  value={form.purchase_price}
                  onChange={(e) => setForm({ ...form, purchase_price: e.target.value })}
                />
              )}
              <input
                type="date"
                className="rounded-lg border px-3 py-2 text-sm"
                value={form.purchase_date}
                onChange={(e) => setForm({ ...form, purchase_date: e.target.value })}
              />
              <input
                type="date"
                className="rounded-lg border px-3 py-2 text-sm"
                value={form.warranty_until}
                onChange={(e) => setForm({ ...form, warranty_until: e.target.value })}
              />
              <textarea
                className="rounded-lg border px-3 py-2 text-sm"
                placeholder="Описание"
                rows={2}
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
              />
              <textarea
                className="rounded-lg border px-3 py-2 text-sm"
                placeholder="Комментарий"
                rows={2}
                value={form.comment}
                onChange={(e) => setForm({ ...form, comment: e.target.value })}
              />
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-lg border px-4 py-2 text-sm"
                onClick={() => setModal(null)}
              >
                Отмена
              </button>
              <button
                type="button"
                className="rounded-lg bg-emerald-600 px-4 py-2 text-sm text-white"
                onClick={saveNewItem}
              >
                Сохранить
              </button>
            </div>
          </div>
        </div>
      )}

      {modal === "detail" && selected && (
        <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/30">
          <div className="h-full w-full max-w-md overflow-y-auto bg-white p-6 shadow-2xl">
            <div className="mb-4 flex items-start justify-between">
              <h2 className="text-lg font-semibold leading-snug">{selected.name}</h2>
              <button
                type="button"
                className="text-slate-500 hover:text-slate-800"
                onClick={() => setModal(null)}
              >
                ✕
              </button>
            </div>
            <p className="text-sm text-slate-500">
              {selected.inventory_number} · {selected.status_display}
            </p>
            {selected.image_url && (
              <img
                src={selected.image_url}
                alt=""
                className="mt-3 max-h-40 rounded-lg object-cover"
              />
            )}
            {selected.qr_url && (
              <div className="mt-3 flex items-center gap-3">
                <img src={selected.qr_url} alt="QR" className="h-24 w-24" />
                <a
                  className="text-sm text-emerald-600 underline"
                  href={`/api/inventory/items/${selected.id}/qr/`}
                  download
                >
                  Скачать QR
                </a>
              </div>
            )}
            <div className="mt-4 space-y-2 text-sm">
              <p>
                <span className="text-slate-500">Склад:</span> {selected.warehouse_name}
              </p>
              {meta.show_prices && (
                <p>
                  <span className="text-slate-500">Стоимость:</span>{" "}
                  {selected.purchase_price} ₸
                </p>
              )}
            </div>
            {meta.can_edit && (
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  className="rounded border border-amber-200 px-2 py-1 text-xs text-amber-800"
                  onClick={async () => {
                    await api(`/api/inventory/items/${selected.id}/repair/`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({}),
                    });
                    pushToast("В ремонте");
                    reloadItems();
                  }}
                >
                  Ремонт
                </button>
                <button
                  type="button"
                  className="rounded border border-red-200 px-2 py-1 text-xs text-red-700"
                  onClick={async () => {
                    if (!window.confirm("Списать?")) return;
                    await api(`/api/inventory/items/${selected.id}/writeoff/`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({}),
                    });
                    pushToast("Списано");
                    reloadItems();
                    setModal(null);
                  }}
                >
                  Списать
                </button>
              </div>
            )}
            <h3 className="mt-6 text-sm font-semibold">История</h3>
            <ul className="mt-2 space-y-2 text-xs text-slate-600">
              {detailHist.map((lg) => (
                <li key={lg.id}>
                  {lg.created_at?.slice(0, 16)} — {lg.action_display}{" "}
                  {lg.description}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <ToastHost msgs={toasts} />
    </div>
  );
}

const rootEl = document.getElementById("inventory-erp-root");
if (rootEl) {
  createRoot(rootEl).render(<App />);
}
