"""Compact, pre-filtered facts for the AI steps. Most of the cost of qualifying is the text the sub-agents read, so
GOODLEADS never sends raw site text: it cuts each page into sentences, drops menus and boilerplate that repeats across
pages, and keeps the opening of the home and about page plus the sentences that touch the criteria. Every sentence
kept is a literal piece of the stored page, so evidence quotes can still be checked against the pages.
"""

import os
import re

# Words that point at size, customers, hiring and history, in the languages GOODLEADS reads. Matched as word stems.
GENERIC = """
team medewerk collega werknemer vakmens specialist employee staff people colleague professional engineer mitarbeiter
kolleg collaborat employ salari empleado dipendent fte klant client customer kunde clientèle cliente opdrachtgever
sector branche industr mkb sme kmo pme midden zakelijk business bedrijven companies unternehmen entreprises
vacature vacatur job career werken bij solliciteer stelle karriere emploi recrut opgericht since sinds founded
established gegründet seit fondé depuis jaar years jahre ans años vestiging office kantoor locati standort
""".split()

STOP = set("""
the and for with that this from what who are not but any all can our your their they them one two more than into
about such like also only must should would could which when where there here have has been being were was its
it's does done doing make made want wants need needs good bad very some most less much many each other same
yes partly fit fits sell sells signals signal opening line tone language website site sites company companies
clearly clear deal breaker breakers kind roughly part small group etc e.g. a an of to in on or by as at is be
""".split())

SPLIT_RX = re.compile(r"(?<=[.!?])\s+|\s{2,}|\s+[|•·»›]\s+|\s+[-–—]\s+(?=[A-ZÀ-Ý])")
WORD_RX = re.compile(r"[a-zà-ÿ0-9][a-zà-ÿ0-9'’+-]*", re.I)


def keywords(niche, criteria_path=None):
    """Word stems to look for: niche.json 'keywords' (written by /goodleads-setup, in the site language), the search
    terms, the longer words of criteria.md, and a fixed list about size, customers, jobs and history."""
    words = []
    for w in (niche.get("keywords") or []) + (niche.get("search_terms") or []) + (niche.get("name_keywords") or []):
        words += WORD_RX.findall(str(w).lower())
    if criteria_path and os.path.exists(criteria_path):
        with open(criteria_path, encoding="utf-8") as f:
            words += [w for w in WORD_RX.findall(f.read().lower()) if len(w) >= 5]
    words += GENERIC
    out, seen = [], set()
    for w in words:
        w = w.strip("'’-+")
        if len(w) < 3 or w in STOP or w.isdigit() or w in seen:
            continue
        seen.add(w)
        out.append(w[:7] if len(w) > 8 else w)      # a stem catches plurals and compounds
    return sorted(set(out))


def _kw_rx(kws):
    return re.compile(r"(?<![a-zà-ÿ])(?:" + "|".join(re.escape(k) for k in sorted(kws, key=len, reverse=True)) + ")",
                      re.I) if kws else None


def sentences(text):
    return [s.strip(" ,;:") for s in SPLIT_RX.split(text or "") if s.strip(" ,;:")]


def _menu_words(page):
    """Words of the short menu items. Long items (mega-menus with a description per service) are content, not menu."""
    return {w.lower() for m in (page.get("menu") or []) if len(m.split()) <= 4 for w in WORD_RX.findall(m)}


NOISE = {"home", "menu", "zoek", "search", "naar", "skip", "inhoud", "content", "main", "ga", "to", "naar:"}


def _w(t):
    return t.strip(".,:;!?()[]'\"’‘“”").lower()


def _strip_menu(s, menu):
    """Cut navigation glued in front of the first real sentence: the longest start of the chunk that is mostly
    (70%+) menu words and ends on two of them in a row. What is left is still literal page text."""
    toks = s.split()
    menu = menu | NOISE
    cut, hits, seen, run = 0, 0, 0, 0
    for j, t in enumerate(toks, 1):
        w = _w(t)
        if len(w) < 4 and w not in NOISE:
            continue                       # short words (de, en, of) say nothing either way
        seen += 1
        if w in menu:
            hits += 1
            run += 1
            if seen >= 3 and run >= 2 and hits / seen >= 0.7:
                cut = j
        else:
            run = 0
    while cut and cut < len(toks) and _w(toks[cut]) in menu:
        cut += 1                           # short menu words right after the cut ("Werken bij")
    return " ".join(toks[cut:]) if cut and len(toks) - cut >= 5 else s


def _informative(s, menu):
    ws = WORD_RX.findall(s.lower())
    if len(ws) < 5:
        return False
    ws = [w for w in ws if len(w) >= 4] or ws
    inmenu = sum(1 for w in ws if w in menu)
    return inmenu / len(ws) < 0.6


def digest(pages, kws, budget=2200, lead_chars=500, max_sentence=280, kinds=None):
    """[(page, [sentence, ...])] for the given pages, at most `budget` characters of sentences in total.
    The first `lead_chars` of informative text on the home and about page always go in (what they do, in their own
    words); the rest of the budget goes to the sentences with the most keyword hits, kept in page order."""
    rx = _kw_rx(kws)
    seen, cands, keep = set(), [], {}
    for pi, p in enumerate(pages):
        if kinds and p.get("kind") not in kinds:
            continue
        menu = _menu_words(p)
        lead = 0
        for si, s in enumerate(sentences(p.get("text"))):
            s = _strip_menu(s, menu)
            key = s.lower()
            if key in seen or not _informative(s, menu):
                continue
            seen.add(key)
            s = s[:max_sentence]
            hits = len(set(m.group(0).lower() for m in rx.finditer(s))) if rx else 0
            if p.get("kind") in ("home", "about") and lead < lead_chars:
                keep[(pi, si)] = s
                lead += len(s)
            elif hits:
                cands.append((-hits, pi, si, s))
    used = sum(len(s) for s in keep.values())
    for _, pi, si, s in sorted(cands):
        if used + len(s) > budget:
            continue
        keep[(pi, si)] = s
        used += len(s)
    out = []
    for pi, p in enumerate(pages):
        ss = [keep[k] for k in sorted(keep) if k[0] == pi]
        if ss:
            out.append((p, ss))
    return out


def clip(s, n):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"
