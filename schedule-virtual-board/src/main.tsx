import { createRoot, type Root } from "react-dom/client";

import { buildSuccCatalog } from "./gantt";
import { ScheduleVirtualApp } from "./ScheduleVirtualApp";
import type { ScheduleVirtualPayload } from "./types";

declare global {
  interface Window {
    MetrixScheduleVirtualMount?: (rootId: string, scriptId: string) => void;
    MetrixScheduleVirtualFetch?: (rootId: string, apiUrl: string) => void;
  }
}

let activeRoot: Root | null = null;

function renderPayload(el: HTMLElement, payload: ScheduleVirtualPayload) {
  payload.succ_catalog = buildSuccCatalog(
    payload.rows || [],
    payload.succ_catalog,
  );
  el.innerHTML = "";
  if (activeRoot) {
    try {
      activeRoot.unmount();
    } catch {
      /* ignore */
    }
    activeRoot = null;
  }
  activeRoot = createRoot(el);
  activeRoot.render(<ScheduleVirtualApp payload={payload} />);
}

function showMountError(el: HTMLElement, message: string) {
  el.innerHTML = `<div class="rounded-2xl border border-red-200 bg-red-50 p-8 text-center text-sm text-red-700">${message}</div>`;
}

function mount(rootId: string, scriptId: string) {
  const el = document.getElementById(rootId);
  const sc = document.getElementById(scriptId);
  if (!el || !sc || !sc.textContent) return;
  try {
    const payload = JSON.parse(sc.textContent) as ScheduleVirtualPayload;
    renderPayload(el, payload);
  } catch (e) {
    console.error("MetrixScheduleVirtualMount:", e);
    showMountError(el, "Не удалось загрузить график. Обновите страницу (Ctrl+F5).");
  }
}

async function mountFetch(rootId: string, apiUrl: string) {
  const el = document.getElementById(rootId);
  if (!el) return;
  el.textContent = "Загрузка графика…";
  el.className =
    "flex items-center justify-center min-h-[420px] border border-slate-200 rounded-2xl bg-white text-sm text-slate-500";
  try {
    const resp = await fetch(apiUrl, {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }
    const payload = (await resp.json()) as ScheduleVirtualPayload;
    renderPayload(el, payload);
  } catch (e) {
    console.error("MetrixScheduleVirtualFetch:", e);
    showMountError(
      el,
      "Не удалось загрузить график. Обновите страницу (Ctrl+F5) или перезапустите сервер.",
    );
  }
}

window.MetrixScheduleVirtualMount = mount;
window.MetrixScheduleVirtualFetch = mountFetch;
