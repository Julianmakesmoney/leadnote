"""Cold-call briefings for the best-fit prospects (/goodleads-brief).

    prepare()        batches of fit=yes companies (not briefed yet) with everything stored about them
    import_briefs()  stores what the briefer wrote and renders one markdown briefing per company

Only fit 'yes' by default; 'partly' keeps the short qualification. Capped by max_brief in niche.json (default 25).
"""

import glob
import json
import os
import re

from . import db
from .compact import keywords
from .qualify import CHARS_PER_TOKEN, _criteria_text, deep_block, quote_found

OVERHEAD_PER_BATCH = 80000          # measured: one briefer sub-agent's fixed context (see qualify.py)
WEB_PER_COMPANY = 2500              # one news search, at most one extra page, and the briefing it writes
SECONDS_PER_COMPANY = 60
BRIEF_BUDGET = 4500                 # characters of site sentences per company
BATCH_SIZE = 4


def candidates(conn, fits=("yes",), again=False):
    marks = ",".join("?" * len(fits))
    return conn.execute(
        f"SELECT c.* FROM company c JOIN label l ON l.company_id = c.id AND l.stage = 'deep' AND l.fit IN ({marks})"
        " WHERE c.duplicate_of IS NULL" + ("" if again else
                                            " AND NOT EXISTS (SELECT 1 FROM briefing b WHERE b.company_id = c.id)") +
        " ORDER BY CASE l.fit WHEN 'yes' THEN 0 ELSE 1 END, COALESCE(l.score, -1) DESC, c.id", fits).fetchall()


def brief_block(conn, c, kws):
    lab = conn.execute("SELECT * FROM label WHERE company_id = ? AND stage = 'deep'", (c["id"],)).fetchone()
    score = f", score {lab['score']}" if lab["score"] is not None else ""
    q = [f"qualified: {lab['fit']}{score}, size {lab['size'] or 'unknown'}. {lab['reason'] or ''}",
         f"evidence: \"{lab['evidence'] or ''}\" ({lab['evidence_url'] or 'maps'})",
         f"opener: {lab['opener'] or ''}"]
    block = deep_block(conn, c, kws, budget=BRIEF_BUDGET, with_sieve=False).split("\n")
    return "\n".join(block[:3] + q + block[3:])


def prepare(conn, paths, niche, fits=("yes",), limit=None, batch_size=BATCH_SIZE, again=False):
    folder = os.path.join(paths.qualify_dir, "brief")
    os.makedirs(folder, exist_ok=True)
    for f in glob.glob(os.path.join(folder, "batch-*")):
        os.remove(f)
    rows = candidates(conn, fits, again)
    cap = int(limit or niche.get("max_brief") or 25)
    waiting = len(rows)
    rows = rows[:cap]
    kws = keywords(niche, paths.criteria)
    crit = _criteria_text(paths, "brief")
    files, chars = [], 0
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i + batch_size]
        path = os.path.join(folder, f"batch-{i // batch_size + 1:03d}.txt")
        text = (f"GOODLEADS brief batch. {len(chunk)} companies.\nWrite the briefings to: {path[:-4]}.briefs.json\n\n"
                f"## Criteria\n{crit}\n\n## Companies\n\n" + "\n\n".join(brief_block(conn, c, kws) for c in chunk) +
                "\n")
        chars += len(text)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        files.append(path)
    tokens = int(len(files) * OVERHEAD_PER_BATCH + chars / CHARS_PER_TOKEN + len(rows) * WEB_PER_COMPANY)
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
    if b.get("ask_for"):
        out += ["## Ask for", b["ask_for"].strip(), ""]
    if b.get("call_goal"):
        out += ["## Goal of this call", b["call_goal"].strip(), ""]
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
