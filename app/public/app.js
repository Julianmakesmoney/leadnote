// Dragnet page: funnel, filters, table, company card, CSV of what you see.
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n) => (n == null ? "–" : Number(n).toLocaleString("en-US"));

let DATA = { funnel: null, rows: [] };
const state = { q: "", fit: "fitting", area: "", size: "", jobs: false, sort: "fit", dir: 1, open: null };
try { Object.assign(state, JSON.parse(localStorage.getItem("dragnet.filters") || "{}"), { open: null }); } catch {}

function sizeOf(r) {
  if (r.size && r.size !== "unknown") return r.size;
  const n = r.staff;
  if (!n) return "unknown";
  return n < 10 ? "1-9" : n < 50 ? "10-49" : n < 250 ? "50-249" : "250+";
}
const FIT_RANK = { yes: 0, partly: 1, no: 2 };

function filtered() {
  const q = state.q.trim().toLowerCase();
  let rs = DATA.rows.filter((r) => {
    const fit = r.fit || "unlabeled";
    if (state.fit === "fitting" && !(fit === "yes" || fit === "partly")) return false;
    if (!["fitting", "all"].includes(state.fit) && fit !== state.fit) return false;
    if (state.area && r.area !== state.area) return false;
    if (state.size && sizeOf(r) !== state.size) return false;
    if (state.jobs && !(r.job_titles && r.job_titles.length)) return false;
    if (q && ![r.name, r.category, r.reason, r.domain, r.address].some((x) => (x || "").toLowerCase().includes(q))) return false;
    return true;
  });
  const key = {
    fit: (r) => FIT_RANK[r.fit] ?? 3, name: (r) => (r.name || "").toLowerCase(), category: (r) => (r.category || "").toLowerCase(),
    area: (r) => r.area || "", size: (r) => r.staff ?? -1, reviews: (r) => r.reviews ?? -1, jobs: (r) => (r.job_titles || []).length,
  }[state.sort];
  rs.sort((a, b) => {
    const x = key(a), y = key(b);
    return (x < y ? -1 : x > y ? 1 : 0) * state.dir || (a.name || "").localeCompare(b.name || "");
  });
  return rs;
}

function renderFunnel() {
  const f = DATA.funnel;
  if (!f) { $("#funnel").innerHTML = ""; return; }
  const fit = f.fit_yes + f.fit_partly;
  const steps = [
    { n: f.searches, l: "Searches", s: f.searches_left ? `${fmt(f.searches_left)} left in the queue` : "queue done" },
    { n: f.results, l: "Results", s: "list entries read on Maps" },
    { n: f.unique, l: "Unique", s: `${fmt(f.companies)} companies after filters` },
    { n: f.visited, l: "Visited", s: `${fmt(f.visited_ok)} sites readable` },
    { n: fit, l: "Fit", s: `${fmt(f.fit_yes)} yes · ${fmt(f.fit_partly)} partly · ${fmt(f.fit_no + (f.sieved - f.sieve_pass))} no`, win: true },
  ];
  const max = Math.max(1, f.results);
  $("#funnel").innerHTML = steps.map((s) => `
    <div class="step${s.win ? " win" : ""}">
      <div class="n">${fmt(s.n)}</div><div class="l">${s.l}</div><div class="s">${esc(s.s)}</div>
      <div class="bar"><i style="width:${Math.max(2, Math.min(100, (s.n / max) * 100))}%"></i></div>
    </div>`).join("");
}

function renderNiche() {
  const n = DATA.niche;
  $("#niche").innerHTML = n ? `<b>${esc(n.name || "")}</b> · ${esc((n.areas || []).join(", "))}` : "";
  const sel = $("#area");
  const areas = [...new Set(DATA.rows.map((r) => r.area).filter(Boolean))].sort();
  const cur = state.area;
  sel.innerHTML = `<option value="">All areas</option>` + areas.map((a) => `<option ${a === cur ? "selected" : ""}>${esc(a)}</option>`).join("");
}

function renderRows() {
  const rs = filtered();
  document.querySelectorAll("th").forEach((th) => th.classList.toggle("sorted", th.dataset.k === state.sort));
  const empty = $("#empty");
  if (!DATA.rows.length) {
    empty.hidden = false;
    empty.innerHTML = `Nothing yet. Run <code>python run.py find</code>, then <code>python run.py visit</code>, then <code>/dragnet-qualify</code> in Claude Code.`;
  } else if (!rs.length) {
    empty.hidden = false;
    empty.innerHTML = state.fit === "fitting" && !DATA.rows.some((r) => r.fit === "yes" || r.fit === "partly")
      ? `No companies qualified yet. Run <code>/dragnet-qualify</code> in Claude Code, or pick <b>All</b> above.`
      : "No companies match these filters.";
  } else empty.hidden = true;
  $("#rows").innerHTML = rs.slice(0, 2000).map((r) => `
    <tr data-id="${r.id}">
      <td>${r.fit ? `<span class="badge ${r.fit}">${r.fit}</span>` : `<span class="badge">not checked</span>`}</td>
      <td><div class="name">${esc(r.name)}</div><div class="sub">${esc(r.reason || r.domain || "")}</div></td>
      <td class="hide-s">${esc(r.category || "")}</td>
      <td class="hide-m">${esc(r.area || "")}</td>
      <td class="num">${r.staff ? fmt(r.staff) : esc(sizeOf(r) === "unknown" ? "–" : sizeOf(r))}</td>
      <td class="num hide-s">${r.reviews != null ? `${r.rating ?? "–"} · ${fmt(r.reviews)}` : "–"}</td>
      <td class="num hide-m">${(r.job_titles || []).length || (r.jobs_page ? "page" : "–")}</td>
    </tr>`).join("");
}

function link(url, label) { return url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(label)}</a>` : ""; }

function openCard(id) {
  const r = DATA.rows.find((x) => x.id === id);
  if (!r) return;
  state.open = id;
  const verified = r.quote_found === 1 ? "" : r.quote_found === 0 ? ` · <span class="warn">quote not found on the stored pages</span>` : "";
  $("#cardbody").innerHTML = `
    ${r.fit ? `<span class="badge ${r.fit}">${r.fit}</span>` : `<span class="badge">not checked</span>`}
    <h2>${esc(r.name)}</h2>
    <div class="meta">${esc([r.category, r.address, r.area].filter(Boolean).join(" · "))}</div>
    <div class="links">${link(r.website, r.domain || "Website")}${link(r.maps_url, "Maps")}${link(r.contact_page, "Contact page")}${link(r.jobs_page, "Jobs")}${link(r.linkedin, "LinkedIn")}</div>
    ${r.opener ? `<div class="block"><h3>Opening line</h3><div class="opener"><div id="opentext">${esc(r.opener)}</div><button id="copy">Copy</button></div></div>` : ""}
    ${r.reason ? `<div class="block"><h3>Why</h3><div>${esc(r.reason)}</div></div>` : ""}
    ${r.evidence ? `<div class="block"><h3>Evidence</h3><blockquote>“${esc(r.evidence)}”</blockquote><div class="src">${r.evidence_url ? link(r.evidence_url, r.evidence_url) : "Google Maps listing"}${verified}</div></div>` : ""}
    <div class="block"><h3>Signals</h3><dl>
      <dt>Size</dt><dd>${r.size && r.size !== "unknown" ? esc(r.size) + " people" : r.staff ? fmt(r.staff) + " people (site)" : "unknown"}${r.staff_quote ? `<div class="src">“${esc(r.staff_quote)}”</div>` : ""}</dd>
      <dt>Founded</dt><dd>${esc(r.founded ?? "unknown")}</dd>
      <dt>Reviews</dt><dd>${r.reviews != null ? `${r.rating ?? "–"} from ${fmt(r.reviews)} reviews` : "–"}</dd>
      <dt>Phone</dt><dd>${esc(r.phone || "–")}</dd>
      <dt>Jobs</dt><dd>${(r.job_titles || []).length ? `<div class="chips">${r.job_titles.map((t) => `<span>${esc(t)}</span>`).join("")}</div>` : r.jobs_page ? "jobs page, no titles read" : "none found"}</dd>
      <dt>Website</dt><dd>${esc(r.site_status || "not visited")}</dd>
    </dl></div>`;
  $("#card").classList.add("on");
  $("#card").setAttribute("aria-hidden", "false");
  $("#scrim").classList.add("on");
  const copy = $("#copy");
  if (copy) copy.onclick = () => navigator.clipboard.writeText(r.opener).then(() => { copy.textContent = "Copied"; setTimeout(() => (copy.textContent = "Copy"), 1400); });
}
function closeCard() {
  state.open = null;
  $("#card").classList.remove("on");
  $("#card").setAttribute("aria-hidden", "true");
  $("#scrim").classList.remove("on");
}

const CSV = ["fit", "name", "website", "phone", "area", "address", "category", "rating", "reviews", "size", "staff", "founded",
  "reason", "evidence", "evidence_url", "opener", "contact_page", "jobs_page", "linkedin", "maps_url"];
function exportCsv() {
  const cell = (v) => { const s = Array.isArray(v) ? v.join("; ") : String(v ?? ""); return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const lines = [CSV.join(",")].concat(filtered().map((r) => CSV.map((k) => cell(k === "size" ? sizeOf(r) : r[k])).join(",")));
  const blob = new Blob(["﻿" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `dragnet-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function save() { try { localStorage.setItem("dragnet.filters", JSON.stringify({ ...state, open: null })); } catch {} }

async function load() {
  try {
    const r = await fetch("/api/data");
    const j = await r.json();
    if (j.error) throw new Error(j.error);
    DATA = j;
    $("#live").classList.remove("err");
    renderNiche(); renderFunnel(); renderRows();
  } catch (e) {
    $("#live").classList.add("err");
    $("#live span").textContent = "error";
    $("#live").title = String(e.message || e);
  }
}

$("#q").value = state.q;
$("#jobs").checked = state.jobs;
$("#size").value = state.size;
document.querySelectorAll("#fit button").forEach((b) => b.classList.toggle("on", b.dataset.v === state.fit));
$("#q").addEventListener("input", (e) => { state.q = e.target.value; save(); renderRows(); });
$("#area").addEventListener("change", (e) => { state.area = e.target.value; save(); renderRows(); });
$("#size").addEventListener("change", (e) => { state.size = e.target.value; save(); renderRows(); });
$("#jobs").addEventListener("change", (e) => { state.jobs = e.target.checked; save(); renderRows(); });
$("#fit").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  state.fit = b.dataset.v; save();
  document.querySelectorAll("#fit button").forEach((x) => x.classList.toggle("on", x === b));
  renderRows();
});
document.querySelector("thead").addEventListener("click", (e) => {
  const th = e.target.closest("th"); if (!th) return;
  state.dir = state.sort === th.dataset.k ? -state.dir : 1;
  state.sort = th.dataset.k; save(); renderRows();
});
$("#rows").addEventListener("click", (e) => { const tr = e.target.closest("tr"); if (tr) openCard(Number(tr.dataset.id)); });
$("#close").addEventListener("click", closeCard);
$("#scrim").addEventListener("click", closeCard);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeCard(); });
$("#export").addEventListener("click", exportCsv);

load();
setInterval(load, 10000);
