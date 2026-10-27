"""Read a few of the user's best clients' websites during /goodleads-setup, so the criteria can describe what they
have in common ("lookalikes"). Nothing is stored in the database; it prints a short, literal summary per site."""

from .compact import GENERIC, clip, digest
from .qualify import _signals_line
from .visit import visit_site


def describe(url, kws=None, budget=900, fetch=None):
    """One site -> a few lines: title, headings, size/jobs signals and the sentences that matter (literal text)."""
    if not url.startswith("http"):
        url = "https://" + url.strip("/")
    res = visit_site(url, max_pages=4, fetch=fetch)
    out = [f"### {url} ({res['status']}, {len(res['pages'])} pages read)"]
    if not res["pages"]:
        out.append("could not read this site; ask the user what this client does, its size and its customers")
        return "\n".join(out)
    home = res["pages"][0]
    out.append("title: " + clip(" ".join(x for x in [home.get("title"), home.get("description")] if x), 220))
    heads = [h for p in res["pages"] for h in (p.get("headings") or [])[:5]]
    if heads:
        out.append("h: " + clip("; ".join(dict.fromkeys(heads)), 300))
    out.append(_signals_line(res["signals"]))
    menu = (res["signals"].get("services") or {}).get("menu") or []
    if menu:
        out.append("menu: " + clip("; ".join(menu[:15]), 200))
    out.append("pages: " + ", ".join(p["kind"] for p in res["pages"]))
    if len(res["pages"]) == 1:
        out.append("note: only the home page could be read; check it is the right site before drawing conclusions")
    for p, ss in digest(res["pages"], list(kws or []) + GENERIC, budget=budget, lead_chars=300):
        out += [f"- [{p['kind']}] {s}" for s in ss]
    return "\n".join(out)
