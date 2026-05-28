import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const payloadPath = path.join(__dirname, "schedule_payload_sample.json");
const payloadJson = fs.readFileSync(payloadPath, "utf8");
const jsUrl =
  "http://127.0.0.1:8000/static/core/schedule/virtual-gantt.js?v=20260528d";

async function assertMount(page, label) {
  await page.waitForTimeout(3000);
  const state = await page.evaluate(() => {
    const root = document.getElementById("schedule-virtual-root");
    if (!root) return { ok: false, reason: "no root" };
    return {
      ok:
        !!root.querySelector(".sched-timeline-head-cell") &&
        !!root.querySelector('input[type="date"]') &&
        !(root.innerText || "").includes("Не удалось"),
      hasHeader: !!root.querySelector(".sched-timeline-head-cell"),
      text: (root.innerText || "").slice(0, 80),
    };
  });
  if (!state.ok) {
    throw new Error(`${label} failed: ${JSON.stringify(state)}`);
  }
  console.log(`OK: ${label}`);
}

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message || e)));

  // 1) Inline payload mount
  await page.setContent(`
    <div id="schedule-virtual-root" style="width:1200px;height:600px"></div>
    <script type="application/json" id="schedule-virtual-bootstrap"></script>
    <script src="${jsUrl}"></script>
  `);
  await page.waitForFunction(() => window.MetrixScheduleVirtualMount);
  await page.evaluate((json) => {
    document.getElementById("schedule-virtual-bootstrap").textContent = json;
    window.MetrixScheduleVirtualMount(
      "schedule-virtual-root",
      "schedule-virtual-bootstrap",
    );
  }, payloadJson);
  await assertMount(page, "inline payload mount");

  // 2) Fetch mount (requires running Django on :8000)
  await page.setContent(`<div id="schedule-virtual-root"></div><script src="${jsUrl}"></script>`);
  await page.waitForFunction(() => window.MetrixScheduleVirtualFetch);
  try {
    await page.evaluate(() => {
      window.MetrixScheduleVirtualFetch(
        "schedule-virtual-root",
        "/projects/36/schedule/virtual-data/",
      );
    });
    await assertMount(page, "fetch mount (may fail without auth)");
  } catch (e) {
    console.log("SKIP fetch mount without auth:", String(e).slice(0, 120));
  }

  if (errors.length) {
    console.log("JS errors:", errors.join("\n"));
    process.exitCode = 1;
  }

  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
