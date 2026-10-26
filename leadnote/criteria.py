"""config/criteria.md: one fixed outline, so every step can find what it needs.

Sections (## headings, in this order):
    Offer, Price, Ideal customer, Lookalikes from best clients, Must-haves, Nice-to-haves, Deal-breakers,
    Buying signals, Who to ask for, What a good first call looks like, Assumptions, Learned from calibration

Checkable items carry an id, so the qualifier can name them and LEADNOTE can count them:
    - M1: ...                 must-have      (all must hold for fit = yes)
    - D1: ...                 deal-breaker   (one is enough for fit = no)
    - N1 (weight 3): ...      nice-to-have   (weight 1 to 3; decides the order of the fits)
    - S1 (weight 2): ...      buying signal  (weight 1 to 3; decides the order of the fits)
    - L1: ...                 learned from calibration (overrules the sections above)

Must-haves and deal-breakers count hard: `enforce()` turns a label into `no` when one applies, and a `yes` with a
must-have the page leaves unclear into `partly`. Nice-to-haves and buying signals only set the score (0-100).
"""

import os
import re

SECTIONS = ["Offer", "Price", "Ideal customer", "Lookalikes from best clients", "Must-haves", "Nice-to-haves",
            "Deal-breakers", "Buying signals", "Who to ask for", "What a good first call looks like", "Assumptions",
            "Learned from calibration"]
REQUIRED = ["Offer", "Ideal customer", "Must-haves", "Deal-breakers", "Who to ask for"]
ITEM_SECTION = {"M": "Must-haves", "N": "Nice-to-haves", "D": "Deal-breakers", "S": "Buying signals",
                "L": "Learned from calibration"}
WEIGHTED = ("N", "S")

# What each step reads. The sieve only drops sure no's, so it gets the short version; the deep check gets everything
# but the call details; the briefer gets it all.
STAGE_SECTIONS = {
    "sieve": ["Offer", "Ideal customer", "Must-haves", "Deal-breakers", "Learned from calibration"],
    "deep": [s for s in SECTIONS if s != "Who to ask for"],
    "brief": SECTIONS,
}

ITEM_RX = re.compile(r"^\s*[-*]\s*([MNDSL])(\d+)\s*(?:\(\s*(?:weight|w)\s*[:=]?\s*(\d)\s*\))?\s*[:.)\-–]\s*(.+)$", re.I)
HEAD_RX = re.compile(r"^##\s+(.+?)\s*$")


def _canon(name):
    n = re.sub(r"[^a-z]", "", name.lower())
    for s in SECTIONS:
        if re.sub(r"[^a-z]", "", s.lower()) == n:
            return s
    return name.strip()


def parse(text):
    """criteria.md text -> {title, sections: {name: body}, order: [names], items: [{id, kind, weight, text}]}"""
    title, sections, order, cur = "", {}, [], None
    for line in (text or "").splitlines():
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            continue
        m = HEAD_RX.match(line)
        if m:
            cur = _canon(m.group(1))
            sections.setdefault(cur, [])
            order.append(cur)
            continue
        if cur:
            sections[cur].append(line)
    sections = {k: "\n".join(v).strip() for k, v in sections.items()}
    items = []
    for name, body in sections.items():
        for line in body.splitlines():
            m = ITEM_RX.match(line)
            if not m:
                continue
            kind = m.group(1).upper()
            w = int(m.group(3)) if m.group(3) else (1 if kind in WEIGHTED else None)
            items.append({"id": f"{kind}{int(m.group(2))}", "kind": kind, "weight": w, "text": m.group(4).strip(),
                          "section": name})
    return {"title": title, "sections": sections, "order": order, "items": items}


def load(path):
    if not path or not os.path.exists(path):
        return parse("")
    with open(path, encoding="utf-8") as f:
        return parse(f.read())


def is_structured(c):
    return any(s in c["sections"] for s in ("Must-haves", "Deal-breakers"))


def problems(c):
    """What is missing or odd, as short lines. Empty list = fine."""
    out = []
    if not c["sections"]:
        return ["no ## sections found; use the outline in examples/criteria.md"]
    for s in REQUIRED:
        if not c["sections"].get(s, "").strip():
            out.append(f"section '{s}' is missing or empty")
    kinds = {}
    for it in c["items"]:
        kinds.setdefault(it["kind"], []).append(it)
        if ITEM_SECTION[it["kind"]] != it["section"]:
            out.append(f"{it['id']} sits under '{it['section']}' but {it['kind']}-items belong under "
                       f"'{ITEM_SECTION[it['kind']]}'")
        if it["kind"] in WEIGHTED and not 1 <= it["weight"] <= 3:
            out.append(f"{it['id']}: weight must be 1, 2 or 3")
    ids = [it["id"] for it in c["items"]]
    for d in sorted({i for i in ids if ids.count(i) > 1}):
        out.append(f"id {d} is used twice")
    for kind, section in (("M", "Must-haves"), ("D", "Deal-breakers")):
        if c["sections"].get(section, "").strip() and not kinds.get(kind):
            out.append(f"'{section}' has no numbered items like '- {kind}1: ...'")
    return out


def weights(c):
    return {it["id"]: it["weight"] for it in c["items"] if it["kind"] in WEIGHTED}


def item_text(c):
    return {it["id"]: it["text"] for it in c["items"]}


def for_stage(text, stage):
    """The part of criteria.md one step needs. An old-style file without the fixed sections is passed whole."""
    c = parse(text)
    if not is_structured(c):
        return (text or "").strip()
    keep = STAGE_SECTIONS[stage]
    out = [f"# {c['title']}"] if c["title"] else []
    for s in c["order"]:
        if s in keep and c["sections"].get(s, "").strip() and s not in [o[3:] for o in out if o.startswith("## ")]:
            out += [f"## {s}", c["sections"][s]]
    return "\n".join(out).strip()


def add_learned(path, rules, note=None):
    """Append rules as L-items under '## Learned from calibration' (made if missing). Returns the new ids."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    c = parse(text)
    n = max([int(it["id"][1:]) for it in c["items"] if it["kind"] == "L"] or [0])
    new, lines = [], []
    for r in rules:
        r = " ".join(str(r).split())
        if not r:
            continue
        n += 1
        new.append(f"L{n}")
        lines.append(f"- L{n}: {r}" + (f" ({note})" if note else ""))
    if not lines:
        return []
    out = text.rstrip("\n").splitlines()
    if "Learned from calibration" not in c["sections"]:
        out += ["", "## Learned from calibration"]
        at = len(out)
    else:
        start = next(i for i, l in enumerate(out) if HEAD_RX.match(l) and _canon(HEAD_RX.match(l).group(1))
                     == "Learned from calibration")
        end = next((i for i in range(start + 1, len(out)) if HEAD_RX.match(out[i])), len(out))
        body = [i for i in range(start + 1, end) if out[i].strip()]
        if len(body) == 1 and out[body[0]].strip().lower() in ("none", "none yet", "nothing yet", "-"):
            del out[body[0]]
            end -= 1
        at = end
        while at > start + 1 and not out[at - 1].strip():
            at -= 1
    out[at:at] = lines
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out).rstrip("\n") + "\n")
    return new


def _ids(v):
    if not v:
        return []
    if isinstance(v, str):
        v = re.split(r"[,\s]+", v)
    return [str(x).strip().upper() for x in v if str(x).strip()]


def enforce(label, c):
    """Apply the hard rules to one deep label. label: {fit, hits, fails, unclear, breakers}.
    Returns (fit, score, checks, notes). Unknown ids are dropped with a note."""
    known = {it["id"] for it in c["items"]}
    notes, got = [], {}
    for key in ("hits", "fails", "unclear", "breakers"):
        ids = _ids(label.get(key))
        bad = [i for i in ids if known and i not in known]
        if bad:
            notes.append(f"{key}: unknown id {', '.join(bad)} (not in criteria.md)")
        got[key] = [i for i in ids if i not in bad]
    fit = (label.get("fit") or "").strip().lower()
    if got["breakers"] and fit != "no":
        notes.append(f"fit {fit} -> no: deal-breaker {', '.join(got['breakers'])}")
        fit = "no"
    elif got["fails"] and fit != "no":
        notes.append(f"fit {fit} -> no: must-have not met {', '.join(got['fails'])}")
        fit = "no"
    elif got["unclear"] and fit == "yes":
        notes.append(f"fit yes -> partly: must-have unclear {', '.join(got['unclear'])}")
        fit = "partly"
    w = weights(c)
    total = sum(w.values())
    score = None
    if total:
        score = 0 if fit == "no" else round(100 * sum(w.get(i, 0) for i in set(got["hits"])) / total)
    checks = {k: v for k, v in got.items() if v and k != "hits"}
    return fit, score, checks, notes
