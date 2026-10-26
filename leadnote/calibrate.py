"""Calibration (/leadnote-calibrate): check the criteria on about 10 real companies before qualifying hundreds.

    prepare()  picks a mix of visited companies (likely yes, likely partly, likely no) and writes one deep-style batch
    show()     reads the labels the qualifier wrote and prints one line per company, with the hard rules applied

Nothing here is stored as a label: calibration only changes criteria.md (the 'Learned from calibration' section,
written by `run.py learn`). Companies already used in a round are remembered in data/qualify/calibrate/used.json,
so the next round sees new ones, plus the ones you corrected (`--recheck`).
"""

import json
import os
import random

from . import criteria as crit_mod
from .compact import _kw_rx, clip, keywords
from .qualify import (CHARS_PER_TOKEN, OUT_PER_COMPANY, OVERHEAD_PER_BATCH, _criteria_text, _domain, deep_block,
                      read_labels_file)


def _folder(paths):
    return os.path.join(paths.qualify_dir, "calibrate")


def _used(paths):
    try:
        with open(os.path.join(_folder(paths), "used.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"rounds": []}


def _keyword_hits(conn, cid, rx):
    v = conn.execute("SELECT pages FROM visit WHERE company_id = ?", (cid,)).fetchone()
    pages = json.loads(v["pages"] or "[]") if v else []
    text = " ".join((p.get("title") or "") + " " + (p.get("text") or "")[:2500] for p in pages
                    if p.get("kind") in ("home", "about", "services"))
    return len({m.group(0).lower() for m in rx.finditer(text)}) if rx else 0


def buckets(conn, kws, exclude=()):
    """Visited, readable companies split into likely yes / partly / no, most telling first. Existing labels go first
    (a deep 'no' is a near miss, which teaches more than an obvious one); the rest is ranked by how many of the
    niche's keywords their home, about and services pages use: top third likely yes, middle third likely partly,
    bottom third likely no."""
    rows = conn.execute("SELECT c.id, d.fit AS deep, s.fit AS sieve FROM company c"
                        " JOIN visit v ON v.company_id = c.id AND v.status = 'ok'"
                        " LEFT JOIN label d ON d.company_id = c.id AND d.stage = 'deep'"
                        " LEFT JOIN label s ON s.company_id = c.id AND s.stage = 'sieve'"
                        " WHERE c.duplicate_of IS NULL ORDER BY c.id").fetchall()
    rows = [r for r in rows if r["id"] not in set(exclude)]
    out = {"yes": [], "partly": [], "no": []}
    rest = []
    for r in rows:
        if r["deep"]:
            out[r["deep"]].append(r["id"])
        else:
            rest.append(r["id"])
    sieve_drops = [r["id"] for r in rows if not r["deep"] and r["sieve"] == "drop"]
    rest = [i for i in rest if i not in set(sieve_drops)]
    rx = _kw_rx(kws)
    hits = {cid: _keyword_hits(conn, cid, rx) for cid in rest}
    ranked = sorted(rest, key=lambda cid: (-hits[cid], cid))
    third = max(1, len(ranked) // 3) if ranked else 0
    out["yes"] += ranked[:third]
    out["partly"] += ranked[third:2 * third]
    out["no"] += sieve_drops + ranked[2 * third:]
    return out


def pick(conn, kws, n=10, exclude=(), recheck=(), seed=0):
    """About n company ids: the ones to recheck first, then a third from the front of each bucket."""
    chosen = [int(x) for x in recheck][:n]
    b = buckets(conn, kws, exclude=set(exclude) | set(chosen))
    order = ["yes", "partly", "no"]
    want = {k: (n - len(chosen)) // 3 for k in order}
    for k in order[:(n - len(chosen)) % 3]:
        want[k] += 1
    spare = 0
    for k in order:
        take = b[k][:want[k] + spare]
        spare = want[k] + spare - len(take)
        chosen += take
    if spare:                                   # a bucket ran short: fill from whatever is left
        left = [i for k in order for i in b[k] if i not in chosen]
        chosen += left[:spare]
    random.Random(seed).shuffle(chosen)          # the user should not see the buckets in order
    return chosen[:n]


def prepare(conn, paths, niche, n=10, recheck=(), fresh=False):
    folder = _folder(paths)
    os.makedirs(folder, exist_ok=True)
    used = {"rounds": []} if fresh else _used(paths)
    rnd = len(used["rounds"]) + 1
    seen = [i for r in used["rounds"] for i in r]
    kws = keywords(niche, paths.criteria)
    rank_kws = [w.lower() for w in niche.get("keywords") or []] or kws      # the niche's own words rank best
    ids = pick(conn, rank_kws, n=n, exclude=seen, recheck=recheck, seed=rnd)
    path = os.path.join(folder, f"round-{rnd}.txt")
    label_file = path[:-4] + ".labels.json"
    if os.path.exists(label_file):
        os.remove(label_file)
    rows = [conn.execute("SELECT * FROM company WHERE id = ?", (i,)).fetchone() for i in ids]
    body = "## Companies\n\n" + "\n\n".join(deep_block(conn, c, kws, with_sieve=False) for c in rows)
    text = (f"LEADNOTE calibration batch (round {rnd}). {len(rows)} companies. Judge each company block against the "
            f"criteria and name the criteria ids you used; use \"stage\": \"calibrate\".\n"
            f"Write the labels to: {label_file}\n\n## Criteria\n{_criteria_text(paths, 'deep')}\n\n{body}\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    used["rounds"].append(ids)
    with open(os.path.join(folder, "used.json"), "w", encoding="utf-8") as f:
        json.dump(used, f)
    tokens = int(OVERHEAD_PER_BATCH["deep"] + len(text) / CHARS_PER_TOKEN + len(rows) * OUT_PER_COMPANY["deep"])
    return {"round": rnd, "companies": len(rows), "ids": ids, "file": path, "labels": label_file,
            "est_tokens": tokens, "est_minutes": 3}


def show(conn, paths, label_file):
    """One line per company: number, name, domain, verdict (with the hard rules applied), score and reason."""
    crit = crit_mod.load(paths.criteria)
    texts = crit_mod.item_text(crit)
    _, labels = read_labels_file(label_file)
    lines = []
    for i, lab in enumerate(labels, 1):
        try:
            c = conn.execute("SELECT * FROM company WHERE id = ?", (int(lab.get("id")),)).fetchone()
        except (TypeError, ValueError):
            c = None
        if not c:
            lines.append(f"{i}. ? (unknown id {lab.get('id')})")
            continue
        fit, score, checks, notes = crit_mod.enforce(lab, crit)
        named = [x for k in ("breakers", "fails", "unclear") for x in checks.get(k, [])]
        why = (lab.get("reason") or "").strip()
        if named:
            why += " [" + "; ".join(f"{x}: {clip(texts.get(x, ''), 60)}" for x in named) + "]"
        sc = f" {score}" if score is not None and fit != "no" else ""
        lines.append(f"{i}. {c['name']} ({_domain(c)}) | id {c['id']} | {fit.upper()}{sc} | {why}")
        lines += [f"     note: {n}" for n in notes if "->" in n]
    return lines
