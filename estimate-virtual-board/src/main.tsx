import { createRoot, type Root } from "react-dom/client";

import { EstimateVirtualApp } from "./EstimateVirtualApp";
import type { EstimateVirtualPayload } from "./types";

declare global {
  interface Window {
    MetrixEstimateVirtualMount?: (rootId: string, scriptId: string) => void;
  }
}

let activeRoot: Root | null = null;

function mount(rootId: string, scriptId: string) {
  const el = document.getElementById(rootId);
  const sc = document.getElementById(scriptId);
  if (!el || !sc || !sc.textContent) return;
  try {
    const payload = JSON.parse(
      sc.textContent,
    ) as EstimateVirtualPayload;
    if (activeRoot) {
      try {
        activeRoot.unmount();
      } catch {
        /* ignore */
      }
      activeRoot = null;
    }
    activeRoot = createRoot(el);
    activeRoot.render(<EstimateVirtualApp payload={payload} />);
  } catch (e) {
    console.error("MetrixEstimateVirtualMount:", e);
  }
}

window.MetrixEstimateVirtualMount = mount;
