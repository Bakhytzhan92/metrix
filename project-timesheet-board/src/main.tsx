import { createRoot } from "react-dom/client";

import { TimesheetApp } from "./TimesheetApp";

declare global {
  interface Window {
    MetrixProjectTimesheetMount?: () => void;
  }
}

function mount() {
  const root =
    document.getElementById("timesheet-root") ||
    document.getElementById("project-timesheet-root");
  if (!root) return;
  const apiBase = root.dataset.apiBase || "";
  const csrf = root.dataset.csrf || "";
  if (!apiBase) return;
  root.innerHTML = "";
  createRoot(root).render(
    <TimesheetApp apiBase={apiBase} csrfToken={csrf} />,
  );
}

window.MetrixProjectTimesheetMount = mount;

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount);
} else {
  mount();
}
