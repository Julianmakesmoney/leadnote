"""Qualifying in two steps, done by Claude Code (/leadnote-qualify), not by an API key.

    prepare(stage)    writes compact text batches to data/qualify/<stage>/batch-NNN.txt for the sub-agents
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
from .compact import clip, digest, keywords

SIEVE_FIT = ("pass", "drop")
DEEP_FIT = ("yes", "partly", "no")
SIZES = ("1-9", "10-49", "50-249", "250+", "unknown")

# Token estimate per batch, measured with real sub-agent runs on the Utrecht test data (README, "Cost and time"):
# about 80k tokens of fixed context per sub-agent (its system prompt and tools), plus the batch text it reads
# (about 2.8 characters per token, line numbers included), plus what it writes.
OVERHEAD_PER_BATCH = {"sieve": 80000, "deep": 80000}
CHARS_PER_TOKEN = 2.8
OUT_PER_COMPANY = {"sieve": 15, "deep": 170}
SECONDS_PER_BATCH = {"sieve": 60, "deep": 150}
BATCH_SIZE = {"sieve": 80, "deep": 20}
DEEP_BUDGET = 2400                   # characters of site sentences per company in the deep check
AUTO_PASS = ("unreachable", "no_website")


def _visit(conn, cid):
    v = conn.execute("SELECT * FROM visit WHERE company_id = ?", (cid,)).fetchone()
    if not v:
        return {}, [], None
    return json.loads(v["signals"] or "{}"), json.loads(v["pages"] or "[]"), v["status"]


def _domain(c):
    return c["domain"] or re.sub(r"^https?://(www\.)?|/.*$", "", c["website"] or "") or "no website"


def _maps_line(c, status):
    bits = [c["category"] or "no category", c["area"] or ""]
    if c["rating"]:
        bits.append(f"{c['rating']} ({c['reviews'] or 0} reviews)")
    bits.append(f"site {_domain(c)} ({status or 'not visited'})")
    return "maps: " + " · ".join(b for b in bits if b)


def _signals_line(sig):
    out = []
    st = sig.get("staff") or {}
    if st.get("value"):
        out.append(f"staff {st['value']}" + (f" (\"{clip(st.get('quote'), 100)}\")" if st.get("quote") else ""))
    fo = sig.get("founded") or {}
    if fo.get("value"):
        out.append(f"founded {fo['value']}")
    if sig.get("size_phrases"):
        out.append("size words: " + ", ".join(f"{x['phrase']} (\"{clip(x.get('quote'), 90)}\")" if isinstance(x, dict)
                                              else str(x) for x in sig["size_phrases"][:3]))
    jobs = sig.get("jobs") or {}
    if jobs.get("titles"):
        out.append("jobs: " + "; ".join(clip(t, 60) for t in jobs["titles"][:5]))
    elif jobs.get("page"):
        out.append("jobs page" + (" (no openings)" if jobs.get("none_open") else ""))
    if sig.get("webshop"):
        out.append("webshop")
    return "signals: " + ("; ".join(out) if out else "none found")


def sieve_line(conn, c, kws):
    """One line per company for the sieve: what the homepage says, about 500 characters."""
    _, pages, status = _visit(conn, c["id"])
    home = next((p for p in pages if p["kind"] == "home"), None)
    parts = [str(c["id"]), clip(c["name"], 60), c["category"] or "-", _domain(c)]
    if status != "ok":
        parts.append(f"site: {status}")
    if home:
        parts.append(clip(" ".join(x for x in [home.get("title"), home.get("description")] if x), 220))
        if home.get("headings"):
            parts.append("h: " + clip("; ".join(home["headings"][:10]), 200))
        d = digest([home], kws, budget=320, lead_chars=140, max_sentence=160)
        if d:
            parts.append(clip(" ".join(d[0][1]), 260))
    return " | ".join(parts).replace("\n", " ")


def deep_block(conn, c, kws, budget=DEEP_BUDGET, with_sieve=True):
    """A compact block per company for the deep check (and the briefer): Maps data, signals, then per page the
    title, a few headings and only the sentences that matter. Every sentence is literal page text."""
    sig, pages, status = _visit(conn, c["id"])
    out = [f"### id {c['id']} · {c['name']}", _maps_line(c, status), _signals_line(sig)]
    if with_sieve:
        sv = conn.execute("SELECT reason FROM label WHERE company_id = ? AND stage = 'sieve'", (c["id"],)).fetchone()
        if sv and sv["reason"]:
            out.append(f"sieve: {sv['reason']}")
    for p, ss in digest(pages[:6], kws, budget=budget):
        out.append(f"[{p['kind']}] {p['url']}" + (f" | {clip(p.get('title'), 90)}" if p.get("title") else ""))
        if p.get("headings"):
            out.append("h: " + clip("; ".join(p["headings"][:6]), 160))
        out += [f"- {s}" for s in ss]
    return "\n".join(x.replace("\n", " ") if i else x for i, x in enumerate(out))


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


def prefilter(conn, niche, rows):
    """Decide what needs no AI: parked domains are dropped, sites that could not be reached go straight to the deep
    check (it judges them on the Maps data), and a word from `sieve_drop_words` in the name or Maps category drops a
    company. Returns the rows that still need the sieve, and the counts."""
    words = [w.lower() for w in niche.get("sieve_drop_words") or [] if w]
    left, auto = [], {"pass": 0, "drop": 0}
    for c in rows:
        st = conn.execute("SELECT status FROM visit WHERE company_id = ?", (c["id"],)).fetchone()
        st = st["status"] if st else None
        hay = f"{c['name'] or ''} {c['category'] or ''}".lower()
        hit = next((w for w in words if w in hay), None)
        if st == "parked":
            fit, reason = "drop", "auto: parked domain, no business on the site"
        elif hit:
            fit, reason = "drop", f"auto: '{hit}' in the name or Maps category (sieve_drop_words)"
        elif st in AUTO_PASS:
            fit, reason = "pass", "auto: site could not be read; judge on the Maps data"
        else:
            left.append(c)
            continue
        conn.execute("INSERT OR REPLACE INTO label (company_id, stage, fit, reason, labeled_at) VALUES (?,?,?,?,?)",
                     (c["id"], "sieve", fit, reason, db.now()))
        auto[fit] += 1
    conn.commit()
    return left, auto


HEAD = {"sieve": "LEADNOTE sieve batch. Judge each company line against the criteria.",
        "deep": "LEADNOTE deep batch. Judge each company block against the criteria."}


def _criteria_text(paths):
    if not os.path.exists(paths.criteria):
        return "(no criteria file)"
    with open(paths.criteria, encoding="utf-8") as f:
        return f.read().strip()


def estimate(stage, batches, chars, companies):
    return int(batches * OVERHEAD_PER_BATCH[stage] + chars / CHARS_PER_TOKEN + companies * OUT_PER_COMPANY[stage])


def prepare(conn, paths, niche, stage, batch_size=None, limit=None):
    """Write the batches for one stage as compact text files. Returns a summary with counts and the cost estimate."""
    assert stage in ("sieve", "deep")
    batch_size = int(batch_size or BATCH_SIZE[stage])
    folder = os.path.join(paths.qualify_dir, stage)
    os.makedirs(folder, exist_ok=True)
    for f in glob.glob(os.path.join(folder, "batch-*")):
        os.remove(f)                 # old batches (labels already imported stay in the database)
    rows = candidates(conn, stage, niche, limit)
    auto = {"pass": 0, "drop": 0}
    if stage == "sieve":
        rows, auto = prefilter(conn, niche, rows)
    kws = keywords(niche, paths.criteria)
    crit = _criteria_text(paths)
    files, chars = [], 0
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i + batch_size]
        path = os.path.join(folder, f"batch-{i // batch_size + 1:03d}.txt")
        label_file = path[:-4] + ".labels.json"
        if stage == "sieve":
            body = ("## Companies (id | name | Maps category | domain | what the homepage says)\n" +
                    "\n".join(sieve_line(conn, c, kws) for c in chunk))
        else:
            body = "## Companies\n\n" + "\n\n".join(deep_block(conn, c, kws) for c in chunk)
        text = (f"{HEAD[stage]} {len(chunk)} companies.\nWrite the labels to: {label_file}\n\n"
                f"## Criteria\n{crit}\n\n{body}\n")
        chars += len(text)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        files.append(path)
    return {"stage": stage, "companies": len(rows), "auto_pass": auto["pass"], "auto_drop": auto["drop"],
            "keywords_missing": not niche.get("keywords"),
            "batches": len(files), "files": files, "est_tokens": estimate(stage, len(files), chars, len(rows)),
            "est_minutes_parallel4": round(-(-len(files) // 4) * SECONDS_PER_BATCH[stage] / 60, 1)}


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
    _, pages, _ = _visit(conn, company_id)
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
        if isinstance(lab, (list, tuple)):          # compact sieve form: [id, "pass"] or [id, "drop", "reason"]
            lab = {"id": lab[0] if lab else None, "fit": lab[1] if len(lab) > 1 else None,
                   "reason": lab[2] if len(lab) > 2 else None}
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
