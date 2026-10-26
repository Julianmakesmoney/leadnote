"""Qualifying in two steps, done by Claude Code (/leadnote-qualify), not by an API key.

    prepare(stage)    writes batches to data/qualify/<stage>/batch-NNN.json for the sub-agents to read
    import_labels()   reads the labels the sub-agents wrote, checks them, stores them

Step 1, the sieve (fast, cheap model): drop only what certainly does not fit. When in doubt: pass.
Step 2, the deep check (better model) on what passed: fit yes/partly/no, a reason, a verbatim quote as evidence,
and one specific opening line.
"""

import glob
import json
import os
import re

from . import db

SIEVE_FIT = ("pass", "drop")
DEEP_FIT = ("yes", "partly", "no")
SIZES = ("1-9", "10-49", "50-249", "250+", "unknown")

# Rough token estimate, measured in the test runs: each sub-agent costs ~70k tokens of fixed overhead (its own
# instructions and tools, counted again on every turn), and the batch text is read about twice (~4 chars per token).
OVERHEAD_PER_BATCH = 70000
OUT_PER_COMPANY = {"sieve": 40, "deep": 220}
SECONDS_PER_BATCH = {"sieve": 60, "deep": 240}


def _visit(conn, cid):
    v = conn.execute("SELECT * FROM visit WHERE company_id = ?", (cid,)).fetchone()
    if not v:
        return {}, []
    return json.loads(v["signals"] or "{}"), json.loads(v["pages"] or "[]")


def _base(c):
    return {"id": c["id"], "name": c["name"], "maps_category": c["category"], "area": c["area"],
            "address": c["address"], "website": c["website"], "rating": c["rating"], "reviews": c["reviews"]}


def sieve_record(conn, c):
    sig, pages = _visit(conn, c["id"])
    home = next((p for p in pages if p["kind"] == "home"), None)
    rec = _base(c)
    rec["site_status"] = conn.execute("SELECT status FROM visit WHERE company_id = ?", (c["id"],)).fetchone()["status"]
    if home:
        rec.update({"title": home.get("title"), "description": home.get("description"),
                    "menu": home.get("menu", [])[:15], "headings": home.get("headings", [])[:12],
                    "home_text": home.get("text", "")[:700]})
    return rec


def deep_record(conn, c):
    sig, pages = _visit(conn, c["id"])
    rec = _base(c)
    rec["site_status"] = conn.execute("SELECT status FROM visit WHERE company_id = ?", (c["id"],)).fetchone()["status"]
    rec["signals"] = {k: sig.get(k) for k in ("staff", "founded", "size_phrases", "jobs", "webshop", "contact_page",
                                               "services")}
    rec["pages"] = [{"kind": p["kind"], "url": p["url"], "title": p.get("title"), "headings": p.get("headings", [])[:15],
                     "text": p.get("text", "")[:2500]} for p in pages[:6]]
    sieve = conn.execute("SELECT reason FROM label WHERE company_id = ? AND stage = 'sieve'", (c["id"],)).fetchone()
    rec["sieve_reason"] = sieve["reason"] if sieve else None
    return rec


def candidates(conn, stage, niche, limit=None):
    """Companies waiting for this stage, capped by max_qualify (counted over everything ever sieved)."""
    if stage == "sieve":
        rows = conn.execute("SELECT c.* FROM company c JOIN visit v ON v.company_id = c.id WHERE c.duplicate_of IS NULL"
                            " AND NOT EXISTS (SELECT 1 FROM label l WHERE l.company_id = c.id AND l.stage = 'sieve')"
                            " ORDER BY c.id").fetchall()
        done = conn.execute("SELECT COUNT(*) FROM label WHERE stage = 'sieve'").fetchone()[0]
        cap = niche.get("max_qualify")
        if cap:
            rows = rows[:max(0, int(cap) - done)]
    else:
        rows = conn.execute("SELECT c.* FROM company c JOIN label s ON s.company_id = c.id AND s.stage = 'sieve'"
                            " AND s.fit = 'pass' WHERE c.duplicate_of IS NULL AND NOT EXISTS (SELECT 1 FROM label l"
                            " WHERE l.company_id = c.id AND l.stage = 'deep') ORDER BY c.id").fetchall()
    return rows[:int(limit)] if limit else rows


def prepare(conn, paths, niche, stage, batch_size=None, limit=None):
    """Write the batches for one stage. Returns a summary with counts and the cost estimate."""
    assert stage in ("sieve", "deep")
    batch_size = int(batch_size or (40 if stage == "sieve" else 8))
    folder = os.path.join(paths.qualify_dir, stage)
    os.makedirs(folder, exist_ok=True)
    for f in glob.glob(os.path.join(folder, "batch-*.json")):
        os.remove(f)                 # old batches (labels already imported stay in the database)
    rows = candidates(conn, stage, niche, limit)
    make = sieve_record if stage == "sieve" else deep_record
    files, chars = [], 0
    for i in range(0, len(rows), batch_size):
        recs = [make(conn, c) for c in rows[i:i + batch_size]]
        path = os.path.join(folder, f"batch-{i // batch_size + 1:03d}.json")
        payload = {"stage": stage, "criteria": paths.criteria, "label_file": path.replace(".json", ".labels.json"),
                   "companies": recs}
        text = json.dumps(payload, ensure_ascii=False, indent=1)
        chars += len(text)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        files.append(path)
    crit = os.path.getsize(paths.criteria) if os.path.exists(paths.criteria) else 0
    tokens_in = chars // 2 + len(files) * (OVERHEAD_PER_BATCH + crit // 4)
    tokens_out = len(rows) * OUT_PER_COMPANY[stage]
    return {"stage": stage, "companies": len(rows), "batches": len(files), "files": files,
            "est_tokens": tokens_in + tokens_out, "est_minutes_parallel4": round(
                -(-len(files) // 4) * SECONDS_PER_BATCH[stage] / 60, 1)}


def _norm(s):
    s = (s or "").lower()
    s = re.sub(r"[“”„\"'’‘`´]", "", s)
    s = s.replace("…", " ").replace("...", " ")
    return " ".join(re.sub(r"[^\w€$£%&+@./:-]+", " ", s).split())


def quote_found(conn, company_id, quote):
    """Is the evidence quote really on the stored pages (or in the Maps fields)? Whitespace, case and quote marks
    do not matter; a quote with '…' in it must have each part on the pages."""
    if not quote:
        return False
    c = conn.execute("SELECT name, category, address, website FROM company WHERE id = ?", (company_id,)).fetchone()
    _, pages = _visit(conn, company_id)
    hay = _norm(" ".join([c["name"] or "", c["category"] or "", c["address"] or ""] +
                         [" ".join([p.get("title") or "", p.get("description") or "", " ".join(p.get("headings", [])),
                                    " ".join(p.get("menu", [])), p.get("text") or ""]) for p in pages]))
    parts = [_norm(x) for x in re.split(r"…|\.\.\.", quote) if _norm(x)]
    return bool(parts) and all(p in hay for p in parts)


def import_labels(conn, path, log=print):
    """Read one labels file {stage, labels: [{id, fit, reason, evidence, evidence_url, opener, size}]}."""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    m = re.search(r"\{.*\}", raw, re.S)          # tolerate text around the JSON
    data = json.loads(m.group(0) if m else raw)
    stage = data.get("stage") or ("sieve" if "sieve" in os.path.basename(os.path.dirname(path)) else "deep")
    allowed = SIEVE_FIT if stage == "sieve" else DEEP_FIT
    ok, problems = 0, []
    for lab in data.get("labels", []):
        try:
            cid = int(lab.get("id"))
        except (TypeError, ValueError):
            problems.append(f"label without a valid id: {str(lab)[:80]}")
            continue
        if not conn.execute("SELECT 1 FROM company WHERE id = ?", (cid,)).fetchone():
            problems.append(f"id {cid}: no such company")
            continue
        fit = (lab.get("fit") or "").strip().lower()
        if fit not in allowed:
            problems.append(f"id {cid}: fit '{fit}' is not one of {allowed}")
            continue
        evidence = (lab.get("evidence") or "").strip() or None
        opener = (lab.get("opener") or "").strip() or None
        size = (lab.get("size") or "").strip() or None
        if stage == "deep":
            if fit in ("yes", "partly") and not opener:
                problems.append(f"id {cid}: fit '{fit}' but no opener")
            if not evidence:
                problems.append(f"id {cid}: no evidence quote")
            if size and size not in SIZES:
                problems.append(f"id {cid}: size '{size}' is not one of {SIZES}; stored as given")
        found = quote_found(conn, cid, evidence) if evidence else None
        if evidence and not found:
            problems.append(f"id {cid}: evidence quote not found on the stored pages (kept, marked unverified)")
        conn.execute("INSERT OR REPLACE INTO label (company_id, stage, fit, reason, evidence, evidence_url, quote_found,"
                     " opener, size, labeled_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (cid, stage, fit, (lab.get("reason") or "").strip() or None, evidence,
                      (lab.get("evidence_url") or "").strip() or None, None if found is None else int(found), opener,
                      size, db.now()))
        ok += 1
    conn.commit()
    log(f"{os.path.basename(path)}: {ok} {stage} labels imported" + (f", {len(problems)} notes:" if problems else ""))
    for p in problems:
        log(f"  - {p}")
    return ok, problems
