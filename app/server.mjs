// GOODLEADS's local page. Zero dependencies: Node 20+ only.
// It asks `python run.py json` for the data (the database is SQLite, which Node 20 cannot read on its own),
// caches the answer for a few seconds, and serves the page in app/public.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";

const APP = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.dirname(APP);
const PUBLIC = path.join(APP, "public");
const PORT = Number(process.env.PORT) || 4760;
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".ico": "image/x-icon", ".json": "application/json" };

function python() {
  if (process.env.GOODLEADS_PYTHON) return process.env.GOODLEADS_PYTHON;
  for (const p of [".venv/bin/python", ".venv/Scripts/python.exe", "venv/bin/python", "venv/Scripts/python.exe"]) {
    if (fs.existsSync(path.join(ROOT, p))) return path.join(ROOT, p);
  }
  return process.platform === "win32" ? "python" : "python3";
}

let cache = { at: 0, body: null };
function data() {
  if (cache.body && Date.now() - cache.at < 4000) return Promise.resolve(cache.body);
  return new Promise((resolve, reject) => {
    execFile(python(), [path.join(ROOT, "run.py"), "json"], { cwd: ROOT, maxBuffer: 256 * 1024 * 1024 },
      (err, stdout, stderr) => {
        if (err) return reject(new Error((stderr || err.message).trim().split("\n").slice(-3).join(" ")));
        cache = { at: Date.now(), body: stdout };
        resolve(stdout);
      });
  });
}

function send(res, code, body, type = "application/json") {
  res.writeHead(code, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (url.pathname === "/api/data") return send(res, 200, await data());
    const file = path.normalize(path.join(PUBLIC, url.pathname === "/" ? "index.html" : url.pathname));
    if (!file.startsWith(PUBLIC) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      return send(res, 404, "Not found", "text/plain");
    }
    res.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream", "cache-control": "no-store" });
    fs.createReadStream(file).pipe(res);
  } catch (e) {
    send(res, 500, JSON.stringify({ error: String(e.message || e) }));
  }
});

server.listen(PORT, "127.0.0.1", () => console.log(`GOODLEADS on http://localhost:${PORT}`));
