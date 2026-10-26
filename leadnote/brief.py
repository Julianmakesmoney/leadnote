"""Cold-call briefings for the best-fit prospects (/leadnote-brief).

    prepare()        batches of fit=yes companies (not briefed yet) with everything stored about them
    import_briefs()  stores what the briefer wrote and renders one markdown briefing per company

Only fit 'yes' by default; 'partly' keeps the short qualification. Capped by max_brief in niche.json (default 25).
"""

import glob
import json
import os
import re

from . import db
from .qualify import deep_record, quote_found

OVERHEAD_PER_BATCH = 70000          # measured overhead of one sub-agent (see qualify.py)
WEB_PER_COMPANY = 25000             # a few extra pages and a news search per company
SECONDS_PER_COMPANY = 90


def candidates(conn, fits=("yes",), again=False):
    marks = ",".join("?" * len(fits))
    return conn.execute(
        f"SELECT c.* FROM company c JOIN label l ON l.company_id = c.id AND l.stage = 'deep' AND l.fit IN ({marks})"
        " WHERE c.duplicate_of IS NULL" + ("" if again else
                                            " AND NOT EXISTS (SELECT 1 FROM briefing b WHERE b.company_id = c.id)") +
        " ORDER BY c.id", fits).fetchall()


def prepare(conn, paths, niche, fits=("yes",), limit=None, batch_size=3, again=False):
    folder = os.path.join(paths.qualify_dir, "brief")
    os.makedirs(folder, exist_ok=True)
    for f in glob.glob(os.path.join(folder, "batch-*.json")):
        os.remove(f)
    rows = candidates(conn, fits, again)
    cap = int(limit or niche.get("max_brief") or 25)
    waiting = len(rows)
    rows = rows[:cap]
    files, chars = [], 0
    for i in range(0, len(rows), batch_size):
        recs = []
        for c in rows[i:i + batch_size]:
            rec = deep_record(conn, c)
            lab = conn.execute("SELECT * FROM label WHERE company_id = ? AND stage = 'deep'", (c["id"],)).fetchone()
            rec["qualification"] = {k: lab[k] for k in ("fit", "reason", "evidence", "evidence_url", "opener", "size")}
            rec["phone"] = c["phone"]
            v = conn.execute("SELECT pages FROM visit WHERE company_id = ?", (c["id"],)).fetchone()
            pages = json.loads(v["pages"] or "[]") if v else []
            rec["pages"] = [{"kind": p["kind"], "url": p["url"], "title": p.get("title"),
                             "headings": p.get("headings", [])[:25], "text": p.get("text", "")} for p in pages]
            recs.append(rec)
        path = os.path.join(folder, f"batch-{i // batch_size + 1:03d}.json")
        payload = {"stage": "brief", "criteria": paths.criteria, "label_file": path.replace(".json", ".briefs.json"),
                   "companies": recs}
        text = json.dumps(payload, ensure_ascii=False, indent=1)
        chars += len(text)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        files.append(path)
    tokens = chars // 2 + len(files) * OVERHEAD_PER_BATCH + len(rows) * WEB_PER_COMPANY
    return {"stage": "brief", "fits": list(fits), "companies": len(rows), "waiting": waiting, "cap": cap,
            "batches": len(files), "files": files, "est_tokens": tokens,
            "est_minutes_parallel3": round(-(-len(files) // 3) * batch_size * SECONDS_PER_COMPANY / 60, 1)}


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:50] or "company"


def render(c, b):
    """Briefing dict -> markdown for one company."""
    out = [f"# {c['name']}", ""]
    meta = " · ".join(x for x in [c["category"], c["address"], c["website"], c["phone"]] if x)
    if meta:
        out += [meta, ""]
    out += ["## Who and why now", b.get("who_why_now", "").strip(), ""]
    if b.get("talking_points"):
        out.append("## Talking points")
        for i, t in enumerate(b["talking_points"], 1):
            ev = f" — “{t['evidence']}”" if t.get("evidence") else ""
            src = f" ({t['url']})" if t.get("url") else ""
            out.append(f"{i}. {t.get('point', '').strip()}{ev}{src}")
        out.append("")
    if b.get("opener"):
        out += ["## Opener", b["opener"].strip(), ""]
    if b.get("objections"):
        out.append("## Likely objections")
        for o in b["objections"]:
            out.append(f"- **{o.get('objection', '').strip()}** {o.get('answer', '').strip()}")
        out.append("")
    if b.get("questions"):
        out.append("## Ask")
        out += [f"- {q.strip()}" for q in b["questions"]]
        out.append("")
    if b.get("decision_makers"):
        out.append("## Decision makers named on their site")
        out += [f"- {d.get('name', '')}, {d.get('role', '')}" + (f" ({d['url']})" if d.get("url") else "")
                for d in b["decision_makers"]]
        out.append("")
    facts = b.get("facts") or {}
    if facts:
        out.append("## Facts")
        out += [f"- {k.replace('_', ' ')}: {v}" for k, v in facts.items() if v not in (None, "", [], {})]
        out.append("")
    if b.get("sources"):
        out.append("## Sources")
        out += [f"- {s}" for s in b["sources"]]
    return "\n".join(out).strip() + "\n"


def import_briefs(conn, paths, path, log=print):
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    m = re.search(r"\{.*\}", raw, re.S)
    data = json.loads(m.group(0) if m else raw)
    folder = os.path.join(paths.data, "briefings")
    os.makedirs(folder, exist_ok=True)
    ok, notes = 0, []
    for b in data.get("briefs", []):
        try:
            cid = int(b.get("id"))
        except (TypeError, ValueError):
            notes.append(f"brief without a valid id: {str(b)[:80]}")
            continue
        c = conn.execute("SELECT * FROM company WHERE id = ?", (cid,)).fetchone()
        if not c:
            notes.append(f"id {cid}: no such company")
            continue
        missing = [k for k in ("who_why_now", "talking_points", "opener", "objections", "questions") if not b.get(k)]
        if missing:
            notes.append(f"id {cid}: missing {', '.join(missing)}")
        for t in b.get("talking_points") or []:
            if t.get("evidence") and not t.get("web") and not quote_found(conn, cid, t["evidence"]):
                t["unverified"] = True
                notes.append(f"id {cid}: evidence not on the stored pages: “{t['evidence'][:60]}”"
                             " (fine if it came from a page the briefer fetched; it says so with web: true)")
        md = render(c, b)
        fpath = os.path.join(folder, f"{cid:05d}-{_slug(c['name'])}.md")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(md)
        conn.execute("INSERT OR REPLACE INTO briefing (company_id, data, markdown, path, created_at) VALUES (?,?,?,?,?)",
                     (cid, json.dumps(b, ensure_ascii=False), md, fpath, db.now()))
        ok += 1
    conn.commit()
    log(f"{os.path.basename(path)}: {ok} briefings stored in {folder}" + (f", {len(notes)} notes:" if notes else ""))
    for n in notes:
        log(f"  - {n}")
    return ok, notes
