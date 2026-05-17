import * as esbuild from "esbuild";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(
  __dirname,
  "../backend/core/static/core/project_gsm/board.js",
);

await esbuild.build({
  entryPoints: [path.join(__dirname, "src/main.tsx")],
  bundle: true,
  outfile: out,
  format: "iife",
  platform: "browser",
  jsx: "automatic",
  minify: true,
  loader: { ".tsx": "tsx", ".ts": "ts" },
  define: {
    "process.env.NODE_ENV": '"production"',
  },
});

console.log("built", out);
