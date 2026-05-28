import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  memo,
} from "react";
import {
  VariableSizeList as List,
  type ListChildComponentProps,
} from "react-window";

import {
  fmt2,
  isZeroLikeInput,
  normalizeNumField,
  parseNum,
  recalcSellAndTotals,
} from "./math";
import type { BootstrapItem, BootstrapSection, EstimateVirtualPayload } from "./types";

/** Фиксированная высота строки для react-window — задаёт высоту и поля «наименование» (flex-1). */
const ROW_H = 40;
const BANNER_H = 34;

/**
 * Колонки шапки и строк. У правых заголовков нельзя `min-w-0` без overflow — текст с nowrap накладывается.
 * Последний трек — действия (~5rem); «наименование» — один `fr`, без перекоса в 1.5fr.
 */
const GRID_TEMPLATE =
  "2.75rem 7rem minmax(11rem,1fr) 4rem 5rem 5rem 6.25rem 5rem 8.75rem 6.25rem 5rem";

type ItemState = {
  ordinal: number;
  type: string;
  name: string;
  unit: string;
  quantity: string;
  cost_price: string;
  markup_percent: string;
  sell_price: string;
  total_cost: string;
  total_price: string;
};

type ApiFns = {
  flushKeepalive: () => void;
  flushBeforeNavigate: () => Promise<boolean>;
  saveAllForce: () => Promise<boolean>;
};

const apiHolder: { current: ApiFns | null } = { current: null };

function getCsrf(payload: EstimateVirtualPayload): string {
  return payload.csrf_token || "";
}

function buildFormData(csrf: string, _id: number, st: ItemState): FormData {
  const fd = new FormData();
  fd.append("csrfmiddlewaretoken", csrf);
  fd.append("type", st.type);
  fd.append("name", st.name);
  fd.append("unit", st.unit);
  fd.append("quantity", normalizeNumField("quantity", st.quantity));
  fd.append("cost_price", normalizeNumField("cost_price", st.cost_price));
  fd.append(
    "markup_percent",
    normalizeNumField("markup_percent", st.markup_percent),
  );
  return fd;
}

const ItemRowInner = memo(
  function ItemRowInner({
    itemId,
    sectionId,
    state,
    supplyHref,
    onChange,
    onBlurCommit,
    scheduleDebouncedSave,
  }: {
    itemId: number;
    sectionId: number;
    state: ItemState;
    supplyHref: string;
    onChange: (id: number, patch: Partial<ItemState>) => void;
    onBlurCommit: (id: number) => void;
    scheduleDebouncedSave: (id: number) => void;
  }) {
    const formId = `estimate-row-${itemId}`;
    const taRef = useRef<HTMLTextAreaElement | null>(null);

    return (
      <>
        <div
          className="py-0 px-1 box-border flex items-center justify-center text-center tabular-nums text-slate-600 text-xs leading-none border-b border-slate-100 min-h-0 min-w-0 overflow-hidden"
          style={{ height: ROW_H }}
        >
          <span>{state.ordinal}</span>
        </div>
        <div
          className="py-0 px-0 box-border flex items-center min-h-0 min-w-0 overflow-hidden border-b border-slate-100"
          style={{ height: ROW_H }}
        >
          <select
            form={formId}
            name="type"
            className="w-full min-w-0 h-8 max-h-8 shrink-0 rounded border border-slate-200 px-1 py-0 text-xs leading-tight focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 box-border"
            value={state.type}
            onChange={(e) => {
              onChange(itemId, { type: e.target.value });
              scheduleDebouncedSave(itemId);
            }}
            onBlur={() => onBlurCommit(itemId)}
          >
            <option value="material">Материалы</option>
            <option value="labor">Работы</option>
            <option value="equipment">Механизмы</option>
            <option value="delivery">Доставка</option>
          </select>
        </div>
        <div
          className="py-0 px-0 box-border flex min-h-0 min-w-0 flex-col overflow-hidden border-b border-slate-100"
          style={{ height: ROW_H }}
        >
          <textarea
            ref={taRef}
            form={formId}
            rows={2}
            name="name"
            placeholder="Наименование"
            className="js-estimate-name-auto min-h-0 flex-1 basis-0 w-full resize-none overflow-y-auto rounded border border-slate-200 px-1 py-0.5 text-xs leading-snug text-slate-800 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 box-border"
            value={state.name}
            onInput={() => {
              onChange(itemId, { name: taRef.current?.value ?? "" });
              scheduleDebouncedSave(itemId);
            }}
            onChange={(e) => {
              onChange(itemId, { name: e.target.value });
              scheduleDebouncedSave(itemId);
            }}
            onBlur={() => onBlurCommit(itemId)}
          />
        </div>
        <div
          className="py-0 px-0 box-border flex items-center min-h-0 min-w-0 overflow-hidden border-b border-slate-100"
          style={{ height: ROW_H }}
        >
          <input
            form={formId}
            type="text"
            name="unit"
            className="w-full min-w-0 h-8 max-h-8 shrink-0 rounded border border-slate-200 px-1 py-0 text-xs leading-tight focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 box-border"
            value={state.unit}
            onChange={(e) => {
              onChange(itemId, { unit: e.target.value });
              scheduleDebouncedSave(itemId);
            }}
            onBlur={() => onBlurCommit(itemId)}
          />
        </div>
        <div
          className="py-0 px-0 box-border flex items-center justify-end min-h-0 min-w-0 overflow-hidden border-b border-slate-100"
          style={{ height: ROW_H }}
        >
          <input
            form={formId}
            type="text"
            name="quantity"
            inputMode="decimal"
            className="w-full min-w-0 max-w-[4.25rem] h-8 max-h-8 shrink-0 rounded border border-slate-200 px-1 py-0 text-xs text-right tabular-nums leading-tight focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 box-border"
            value={state.quantity}
            onFocus={(e) => {
              if (isZeroLikeInput(e.target.value)) e.target.value = "";
            }}
            onChange={(e) => {
              onChange(itemId, { quantity: e.target.value });
              scheduleDebouncedSave(itemId);
            }}
            onBlur={(e) => {
              if (String(e.target.value).trim() === "")
                onChange(itemId, { quantity: "0" });
              onBlurCommit(itemId);
            }}
          />
        </div>
        <div
          className="py-0 px-0 box-border flex items-center justify-end min-h-0 min-w-0 overflow-hidden border-b border-slate-100"
          style={{ height: ROW_H }}
        >
          <input
            form={formId}
            type="text"
            name="cost_price"
            inputMode="decimal"
            className="w-full min-w-0 max-w-[5.25rem] h-8 max-h-8 shrink-0 rounded border border-slate-200 px-1 py-0 text-xs text-right tabular-nums leading-tight focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 box-border"
            value={state.cost_price}
            onFocus={(e) => {
              if (isZeroLikeInput(e.target.value)) e.target.value = "";
            }}
            onChange={(e) => {
              onChange(itemId, { cost_price: e.target.value });
              scheduleDebouncedSave(itemId);
            }}
            onBlur={(e) => {
              if (String(e.target.value).trim() === "")
                onChange(itemId, { cost_price: "0" });
              onBlurCommit(itemId);
            }}
          />
        </div>
        <div
          className="py-0 px-1 box-border flex items-center justify-end text-right tabular-nums text-slate-700 text-xs leading-none whitespace-nowrap border-b border-slate-100 js-item-total-cost min-h-0 min-w-0 overflow-hidden"
          style={{ height: ROW_H }}
          data-item-id={itemId}
          data-section-id={sectionId}
        >
          {state.total_cost}
        </div>
        <div
          className="py-0 px-0 box-border flex items-center justify-end min-h-0 min-w-0 overflow-hidden border-b border-slate-100"
          style={{ height: ROW_H }}
        >
          <input
            form={formId}
            type="text"
            name="markup_percent"
            inputMode="decimal"
            className="w-full min-w-0 max-w-[4rem] h-8 max-h-8 shrink-0 rounded border border-slate-200 px-1 py-0 text-xs text-right tabular-nums leading-tight focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 box-border"
            value={state.markup_percent}
            onFocus={(e) => {
              if (isZeroLikeInput(e.target.value)) e.target.value = "";
            }}
            onChange={(e) => {
              onChange(itemId, { markup_percent: e.target.value });
              scheduleDebouncedSave(itemId);
            }}
            onBlur={(e) => {
              if (String(e.target.value).trim() === "")
                onChange(itemId, { markup_percent: "0" });
              onBlurCommit(itemId);
            }}
          />
        </div>
        <div
          className="py-0 px-1 box-border flex items-center justify-end text-right tabular-nums text-slate-700 text-xs leading-none whitespace-nowrap border-b border-slate-100 js-item-sell-price min-h-0 min-w-0 overflow-hidden"
          style={{ height: ROW_H }}
        >
          {state.sell_price}
        </div>
        <div
          className="py-0 px-1 box-border flex items-center justify-end tabular-nums font-medium text-slate-900 text-xs leading-none whitespace-nowrap border-b border-slate-100 js-item-total-price min-h-0 min-w-0 overflow-hidden"
          style={{ height: ROW_H }}
        >
          {state.total_price}
        </div>
        <div
          className="py-0 px-0 box-border flex flex-row flex-nowrap items-center justify-center gap-0 border-b border-slate-100 text-center min-h-0 min-w-0 overflow-hidden"
          style={{ height: ROW_H }}
        >
            <form
              id={formId}
              method="post"
              action=""
              className="hidden"
              aria-hidden="true"
            >
              <input
                type="hidden"
                name="csrfmiddlewaretoken"
                value=""
              />
            </form>
              <a
                href={supplyHref || "#"}
                data-supply-for={String(itemId)}
                className="inline-flex shrink-0 rounded-md p-1 text-slate-400 hover:bg-indigo-50 hover:text-indigo-600"
                title="Заявка в снабжение"
                aria-label="Заявка в снабжение"
              >
                <svg
                  className="h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={1.5}
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M2.25 3h1.386c.51 0 .955.343 1.087.835l.383 1.437M7.5 14.25a3 3 0 00-3 3h15.75m-12.75-3h11.218c1.121-2.3 2.1-4.684 2.924-7.138a60.114 60.114 0 00-16.536-1.84M7.5 14.25L5.106 18.5m2.106-4.25l5.25-5.25m0 0L18 9.75m-5.25 5.25L18 18"
                  />
                </svg>
              </a>
              <button
                type="button"
                className="js-estimate-row-delete-open inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-base font-light leading-none text-slate-400 hover:bg-red-50 hover:text-red-600"
                title="Удалить строку"
                aria-label="Удалить строку"
                data-delete-url=""
                data-item-name=""
              >
                ×
              </button>
        </div>
      </>
    );
  },
  function propsEqual(prev, next) {
    return (
      prev.itemId === next.itemId &&
      prev.sectionId === next.sectionId &&
      prev.supplyHref === next.supplyHref &&
      prev.state === next.state &&
      prev.onBlurCommit === next.onBlurCommit &&
      prev.scheduleDebouncedSave === next.scheduleDebouncedSave &&
      prev.onChange === next.onChange
    );
  },
);

type ListRowData = {
  sec: BootstrapSection;
  items: Record<number, ItemState>;
  csrf: string;
  onChange: (id: number, patch: Partial<ItemState>) => void;
  onBlurCommit: (id: number) => void;
  scheduleDebouncedSave: (id: number) => void;
};

const VirtualRow = memo(
  function VirtualRow({
    index,
    style,
    data,
  }: ListChildComponentProps<ListRowData>) {
    const row = data.sec.rows[index];
    const rootRef = useRef<HTMLDivElement | null>(null);
    useLayoutEffect(() => {
      if (!row || row.kind !== "item" || !rootRef.current) return;
      const itemRow = row;
      const root = rootRef.current;
      const form = root.querySelector<HTMLFormElement>(
        `form#estimate-row-${itemRow.id}`,
      );
      if (form) {
        form.action = itemRow.urls.save;
        const tok = form.querySelector<HTMLInputElement>(
          "[name=csrfmiddlewaretoken]",
        );
        if (tok) tok.value = data.csrf;
      }
      const supply = root.querySelector<HTMLAnchorElement>(
        `a[data-supply-for="${itemRow.id}"]`,
      );
      if (supply) supply.href = itemRow.urls.supply;
      const delBtn = root.querySelector<HTMLButtonElement>(
        ".js-estimate-row-delete-open",
      );
      if (delBtn) {
        delBtn.dataset.deleteUrl = itemRow.urls.delete;
        const st = data.items[itemRow.id];
        const nm = st?.name || "";
        delBtn.dataset.itemName = nm.length > 100 ? `${nm.slice(0, 97)}...` : nm;
      }
    }, [data.csrf, data.items, row]);

    if (!row) return <div style={style} />;

    if (row.kind === "banner") {
      return (
        <div
          style={{ ...style, boxSizing: "border-box", overflow: "hidden" }}
          className="estimate-subsection-banner border-y border-slate-200 bg-slate-100/90"
        >
          <div
            className="px-1 py-1.5 text-left text-xs font-semibold uppercase tracking-tight text-slate-900 h-full flex items-center"
            style={{ width: "100%" }}
          >
            {row.title}
          </div>
        </div>
      );
    }

    const st = data.items[row.id];
    if (!st) return <div style={style} />;

    return (
      <div
        ref={rootRef}
        style={{
          ...style,
          display: "grid",
          gridTemplateColumns: GRID_TEMPLATE,
          alignItems: "stretch",
          overflow: "hidden",
          boxSizing: "border-box",
        }}
        className="estimate-row hover:bg-slate-50/50 align-top odd:bg-white even:bg-slate-50/20 [&>div]:box-border [&>div]:border-r [&>div]:border-slate-200 [&>div:last-child]:border-r-0"
        data-estimate-form={`estimate-row-${row.id}`}
      >
        <ItemRowInner
          itemId={row.id}
          sectionId={data.sec.id}
          state={st}
          supplyHref={row.urls.supply}
          onChange={data.onChange}
          onBlurCommit={data.onBlurCommit}
          scheduleDebouncedSave={data.scheduleDebouncedSave}
        />
      </div>
    );
  },
);

function SectionBlock({
  sec,
  payload,
  items,
  setItems,
  sectionCosts,
  setSectionCosts,
  registerTimer,
  clearTimer,
  markDirty,
  isDirty,
  saveRowPromise,
  listHeights,
}: {
  sec: BootstrapSection;
  payload: EstimateVirtualPayload;
  items: Record<number, ItemState>;
  setItems: React.Dispatch<React.SetStateAction<Record<number, ItemState>>>;
  sectionCosts: { cost: string; price: string };
  setSectionCosts: React.Dispatch<
    React.SetStateAction<Record<number, { cost: string; price: string }>>
  >;
  registerTimer: (itemId: number, t: number) => void;
  clearTimer: (itemId: number) => void;
  markDirty: (itemId: number) => void;
  isDirty: (itemId: number) => boolean;
  saveRowPromise: (
    itemId: number,
    sectionId: number,
    opts?: { silent?: boolean; force?: boolean },
  ) => Promise<{ ok: boolean }>;
  listHeights: Record<number, number>;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [listW, setListW] = useState(960);
  const listH = listHeights[sec.id] ?? 520;

  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      setListW(Math.max(640, el.clientWidth));
    });
    ro.observe(el);
    setListW(Math.max(640, el.clientWidth));
    return () => ro.disconnect();
  }, [sec.id]);

  const sizes = useCallback(
    (index: number) =>
      sec.rows[index]?.kind === "banner" ? BANNER_H : ROW_H,
    [sec.rows],
  );

  const onChange = useCallback(
    (id: number, patch: Partial<ItemState>) => {
      markDirty(id);
      setItems((prev) => {
        const cur = prev[id];
        if (!cur) return prev;
        const next = { ...cur, ...patch };
        const r = recalcSellAndTotals({
          quantity: next.quantity,
          cost_price: next.cost_price,
          markup_percent: next.markup_percent,
        });
        next.sell_price = fmt2(r.sell);
        next.total_cost = fmt2(r.tCost);
        next.total_price = fmt2(r.tPrice);
        const n2 = { ...prev, [id]: next };
        let sumC = 0;
        let sumP = 0;
        for (const fr of sec.rows) {
          if (fr.kind !== "item") continue;
          const st = fr.id === id ? next : n2[fr.id];
          if (!st) continue;
          sumC += parseNum(st.total_cost);
          sumP += parseNum(st.total_price);
        }
        setSectionCosts((sc) => ({
          ...sc,
          [sec.id]: { cost: fmt2(sumC), price: fmt2(sumP) },
        }));
        return n2;
      });
    },
    [markDirty, sec.id, sec.rows, setItems, setSectionCosts],
  );

  const scheduleDebouncedSave = useCallback(
    (id: number) => {
      clearTimer(id);
      registerTimer(
        id,
        window.setTimeout(() => {
          clearTimer(id);
          void saveRowPromise(id, sec.id, { silent: false });
        }, 320),
      );
    },
    [clearTimer, registerTimer, saveRowPromise, sec.id],
  );

  const onBlurCommit = useCallback(
    (id: number) => {
      clearTimer(id);
      if (isDirty(id)) void saveRowPromise(id, sec.id, { silent: false });
    },
    [clearTimer, isDirty, saveRowPromise, sec.id],
  );

  const listData = useMemo<ListRowData>(
    () => ({
      sec,
      items,
      csrf: getCsrf(payload),
      onChange,
      onBlurCommit,
      scheduleDebouncedSave,
    }),
    [sec, items, payload, onChange, onBlurCommit, scheduleDebouncedSave],
  );

  const Row = VirtualRow;

  return (
    <div
      className="estimate-section group border-0"
      id={`section-${sec.id}`}
      data-section-order={sec.order}
    >
      <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 px-3 py-2.5 sm:px-4 bg-sky-100/95 backdrop-blur-sm border-b border-sky-200/80 text-sm">
        <div className="flex items-center gap-3 min-w-0">
          <span className="js-section-order-badge flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/80 text-sky-900 font-bold text-sm ring-1 ring-sky-200/80">
            {sec.displayBadge}
          </span>
          <div className="min-w-0">
            <span className="js-section-display-name font-semibold text-slate-900 block truncate">
              {sec.name}
            </span>
            <span className="text-xs text-slate-600">{sec.item_count} поз.</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-2 text-sm text-slate-600">
          <span className="whitespace-nowrap tabular-nums text-xs sm:text-sm">
            Себест.: <span className="js-section-cost">{sectionCosts.cost}</span>{" "}
            ₸
          </span>
          <span className="whitespace-nowrap tabular-nums text-xs sm:text-sm">
            Итого: <span className="js-section-price">{sectionCosts.price}</span>{" "}
            ₸
          </span>
          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <button
              type="button"
              className="js-estimate-section-edit-open inline-flex items-center rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50"
              data-section-id={String(sec.id)}
              data-section-name={sec.name}
              data-section-order={String(sec.order)}
              data-save-url={sec.save_url}
            >
              Редактировать раздел
            </button>
            <button
              type="button"
              className="js-estimate-section-delete-open inline-flex items-center rounded-lg border border-red-200 bg-red-50 px-2.5 py-1.5 text-xs font-medium text-red-800 hover:bg-red-100"
              data-delete-url={sec.delete_url}
              data-section-name={sec.name.slice(0, 120)}
            >
              Удалить раздел
            </button>
          </div>
        </div>
      </div>
      <div className="px-3 sm:px-4 pb-4 pt-2 bg-slate-50/30">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <form action={sec.quick_add_action} method="post" className="inline">
            <input type="hidden" name="csrfmiddlewaretoken" value={getCsrf(payload)} />
            <button
              type="submit"
              className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700"
            >
              + позиция
            </button>
          </form>
        </div>
        <div
          ref={containerRef}
          className="overflow-x-auto rounded-lg border border-slate-200 bg-white"
        >
          <div className="min-w-max w-full">
            <div
              className="sticky top-0 z-20 box-border grid bg-slate-50 border-b border-slate-200 text-xs font-medium text-slate-700 shadow-sm [&>div]:box-border [&>div]:border-r [&>div]:border-slate-200 [&>div:last-child]:border-r-0 [&>div]:min-w-0 [&>div]:overflow-hidden"
              style={{
                gridTemplateColumns: GRID_TEMPLATE,
                width: listW,
                minWidth: listW,
              }}
            >
              <div className="px-1 py-1 flex items-center justify-center min-w-0">
                <span className="min-w-0 block w-full truncate text-center">№</span>
              </div>
              <div className="px-1 py-1 flex items-center justify-start min-w-0">
                <span className="min-w-0 block truncate" title="Тип">Тип</span>
              </div>
              <div className="px-1 py-1 flex items-center justify-start min-w-0">
                <span className="min-w-0 block truncate" title="Наименование">Наименование</span>
              </div>
              <div className="px-1 py-1 flex items-center justify-start min-w-0">
                <span className="min-w-0 block truncate" title="Единица измерения">Ед.</span>
              </div>
              <div className="px-1 py-1 flex items-center justify-end min-w-0">
                <span className="min-w-0 block max-w-full truncate text-right" title="Количество">Кол-во</span>
              </div>
              <div className="px-1 py-1 flex items-center justify-end min-w-0">
                <span className="min-w-0 block max-w-full truncate text-right">Цена, ₸</span>
              </div>
              <div
                className="px-1 py-1 flex items-center justify-end min-w-0"
                title="Себестоимость по позиции"
              >
                <span className="min-w-0 block max-w-full truncate text-right">Себест., ₸</span>
              </div>
              <div className="px-1 py-1 flex items-center justify-end min-w-0">
                <span className="min-w-0 block max-w-full truncate text-right">Наценка %</span>
              </div>
              <div
                className="px-1 py-1 flex items-center justify-end min-w-0"
                title="Цена заказчика за единицу"
              >
                <span className="min-w-0 block max-w-full truncate text-right">Заказчик/ед., ₸</span>
              </div>
              <div className="px-1 py-1 flex items-center justify-end min-w-0">
                <span className="min-w-0 block max-w-full truncate text-right">Итого, ₸</span>
              </div>
              <div className="px-0 py-1 flex items-center justify-center" aria-hidden="true" />
            </div>
            {sec.rows.length === 0 ? (
              <div className="px-4 py-6 text-center text-sm text-slate-500">
                Позиций нет — нажмите «+ позиция», чтобы добавить строку.
              </div>
            ) : (
              <List
                height={listH}
                width={listW}
                itemCount={sec.rows.length}
                itemSize={sizes}
                overscanCount={8}
                itemData={listData}
              >
                {Row}
              </List>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function recalcProjectCardsFromSections(
  costs: Record<number, { cost: string; price: string }>,
) {
  let sumCost = 0;
  let sumPrice = 0;
  for (const v of Object.values(costs)) {
    sumCost += parseNum(v.cost);
    sumPrice += parseNum(v.price);
  }
  const firstCb = document.querySelector<HTMLInputElement>(
    ".js-estimate-vat-checkbox",
  );
  const vatOn = !!(firstCb && firstCb.checked);
  const vatAmt = vatOn ? sumPrice * 0.16 : 0;
  const clientTot = vatOn ? sumPrice * 1.16 : sumPrice;
  const setAll = (sel: string, text: string) => {
    document.querySelectorAll(sel).forEach((el) => {
      el.textContent = text;
    });
  };
  setAll(".js-project-total-cost", fmt2(sumCost));
  setAll(".js-project-total-markup", fmt2(sumPrice - sumCost));
  setAll(".js-project-subtotal-client", fmt2(sumPrice));
  setAll(".js-project-vat-amount", fmt2(vatAmt));
  setAll(".js-project-total-price", fmt2(clientTot));
  document.querySelectorAll(".js-vat-detail").forEach((el) => {
    el.classList.toggle("hidden", !vatOn);
  });
  document.querySelectorAll(".js-vat-hint").forEach((el) => {
    el.classList.toggle("hidden", !vatOn);
  });
  document.querySelectorAll(".js-vat-suffix").forEach((el) => {
    el.classList.toggle("hidden", !vatOn);
  });
}

export function EstimateVirtualApp({
  payload,
}: {
  payload: EstimateVirtualPayload;
}) {
  const initialItems = useMemo(() => {
    const m: Record<number, ItemState> = {};
    for (const sec of payload.sections) {
      for (const r of sec.rows) {
        if (r.kind !== "item") continue;
        m[r.id] = {
          ordinal: r.ordinal,
          type: r.type,
          name: r.name,
          unit: r.unit,
          quantity: r.quantity,
          cost_price: r.cost_price,
          markup_percent: r.markup_percent,
          sell_price: r.sell_price,
          total_cost: r.total_cost,
          total_price: r.total_price,
        };
      }
    }
    return m;
  }, [payload]);

  const [items, setItems] = useState<Record<number, ItemState>>(initialItems);

  const [sectionCosts, setSectionCosts] = useState<
    Record<number, { cost: string; price: string }>
  >(() => {
    const o: Record<number, { cost: string; price: string }> = {};
    for (const s of payload.sections) {
      o[s.id] = {
        cost: s.section_total_cost,
        price: s.section_total_price,
      };
    }
    return o;
  });

  const saveTimers = useRef<Map<number, number>>(new Map());
  const dirtyRef = useRef<Set<number>>(new Set());
  const itemsRef = useRef(items);
  itemsRef.current = items;

  const markDirty = useCallback((id: number) => {
    dirtyRef.current.add(id);
  }, []);

  const isDirty = useCallback((id: number) => dirtyRef.current.has(id), []);

  const registerTimer = useCallback((itemId: number, t: number) => {
    const prev = saveTimers.current.get(itemId);
    if (prev) window.clearTimeout(prev);
    saveTimers.current.set(itemId, t);
  }, []);

  const clearTimer = useCallback((itemId: number) => {
    const prev = saveTimers.current.get(itemId);
    if (prev) window.clearTimeout(prev);
    saveTimers.current.delete(itemId);
  }, []);

  const saveRowPromise = useCallback(
    async (
      itemId: number,
      sectionId: number,
      opts?: { silent?: boolean; force?: boolean },
    ) => {
      const silent = opts?.silent === true;
      const force = opts?.force === true;
      const item = itemsRef.current[itemId];
      if (!item) return { ok: true };
      if (!force && !dirtyRef.current.has(itemId))
        return { ok: true, skipped: true as const };

      const rowMeta = payload.sections
        .flatMap((s) => s.rows)
        .find((x): x is BootstrapItem => x.kind === "item" && x.id === itemId);
      const url = rowMeta?.urls.save;
      if (!url) return { ok: false };

      const fd = buildFormData(getCsrf(payload), itemId, item);
      const tok = String(fd.get("csrfmiddlewaretoken") || "");
      try {
        const res = await fetch(url, {
          method: "POST",
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRFToken": tok,
          },
          body: fd,
        });
        const ct = res.headers.get("content-type") || "";
        if (!ct.includes("application/json")) {
          if (!silent) window.alert("Сохранение: ответ не JSON.");
          return { ok: false };
        }
        const data = (await res.json()) as Record<string, unknown>;
        if (!res.ok || !data.ok) {
          if (!silent)
            window.alert(
              `Строка не сохранена: ${JSON.stringify(data.errors || data.error || {})}`,
            );
          return { ok: false };
        }
        dirtyRef.current.delete(itemId);
        const tcStr = String(data.total_cost ?? "");
        const tpStr = String(data.total_price ?? "");
        const spStr = String(data.sell_price ?? "");
        const secCost = String(data.section_total_cost ?? "");
        const secPrice = String(data.section_total_price ?? "");
        setItems((prev) => {
          const cur = prev[itemId];
          if (!cur) return prev;
          return {
            ...prev,
            [itemId]: {
              ...cur,
              total_cost: tcStr || cur.total_cost,
              total_price: tpStr || cur.total_price,
              sell_price: spStr || cur.sell_price,
            },
          };
        });
        if (secCost && secPrice) {
          setSectionCosts((sc) => ({
            ...sc,
            [sectionId]: { cost: secCost, price: secPrice },
          }));
        }
        return { ok: true };
      } catch {
        if (!silent) window.alert("Сеть недоступна при сохранении строки.");
        return { ok: false };
      }
    },
    [payload],
  );

  const listHeights = useMemo(() => {
    const cap =
      typeof window !== "undefined"
        ? Math.min(window.innerHeight * 0.55, 640)
        : 520;
    const o: Record<number, number> = {};
    for (const s of payload.sections) {
      const body = s.rows.reduce(
        (acc, r) => acc + (r.kind === "banner" ? BANNER_H : ROW_H),
        0,
      );
      o[s.id] = Math.min(Math.max(body + 8, 120), cap);
    }
    return o;
  }, [payload.sections]);

  useEffect(() => {
    recalcProjectCardsFromSections(sectionCosts);
  }, [sectionCosts]);

  const flushKeepalive = useCallback(() => {
    saveTimers.current.forEach((t) => window.clearTimeout(t));
    saveTimers.current.clear();
    const ids = Array.from(dirtyRef.current);
    for (const id of ids) {
      const sec = payload.sections.find((s) =>
        s.rows.some((r) => r.kind === "item" && r.id === id),
      );
      if (sec) void saveRowPromise(id, sec.id, { silent: true, force: true });
    }
  }, [payload.sections, saveRowPromise]);

  const flushBeforeNavigate = useCallback(async () => {
    saveTimers.current.forEach((t) => window.clearTimeout(t));
    saveTimers.current.clear();
    const ids = Array.from(dirtyRef.current);
    const results: { ok: boolean }[] = [];
    for (const id of ids) {
      const sec = payload.sections.find((s) =>
        s.rows.some((r) => r.kind === "item" && r.id === id),
      );
      if (sec)
        results.push(
          await saveRowPromise(id, sec.id, { silent: false, force: true }),
        );
    }
    return !results.some((r) => r.ok === false);
  }, [payload.sections, saveRowPromise]);

  const saveAllForce = useCallback(async () => {
    saveTimers.current.forEach((t) => window.clearTimeout(t));
    saveTimers.current.clear();
    const allIds: number[] = [];
    for (const s of payload.sections) {
      for (const r of s.rows) {
        if (r.kind === "item") allIds.push(r.id);
      }
    }
    const results: { ok: boolean }[] = [];
    for (const id of allIds) {
      const sec = payload.sections.find((x) =>
        x.rows.some((r) => r.kind === "item" && r.id === id),
      );
      if (sec)
        results.push(
          await saveRowPromise(id, sec.id, { silent: false, force: true }),
        );
    }
    return !results.some((r) => r.ok === false);
  }, [payload.sections, saveRowPromise]);

  useLayoutEffect(() => {
    apiHolder.current = {
      flushKeepalive,
      flushBeforeNavigate,
      saveAllForce,
    };
    (window as unknown as { __metrixEstimateVirtual?: ApiFns }).__metrixEstimateVirtual =
      apiHolder.current;
    return () => {
      const w = window as unknown as { __metrixEstimateVirtual?: ApiFns };
      if (w.__metrixEstimateVirtual === apiHolder.current) {
        delete w.__metrixEstimateVirtual;
      }
      apiHolder.current = null;
    };
  }, [flushBeforeNavigate, flushKeepalive, saveAllForce]);

  return (
    <>
      {payload.sections.map((sec) => (
        <SectionBlock
          key={sec.id}
          sec={sec}
          payload={payload}
          items={items}
          setItems={setItems}
          sectionCosts={sectionCosts[sec.id]!}
          setSectionCosts={setSectionCosts}
          registerTimer={registerTimer}
          clearTimer={clearTimer}
          markDirty={markDirty}
          isDirty={isDirty}
          saveRowPromise={saveRowPromise}
          listHeights={listHeights}
        />
      ))}
    </>
  );
}
