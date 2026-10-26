"""Visit each company's own website: the homepage plus a few subpages (contact, jobs, about, services, products).

Plain HTTP first, several sites in parallel. Sites that return (almost) no text without JavaScript get one more try
in a headless browser afterwards. Only pages on the company's own domain are read. E-mail addresses are removed
from the text before it is stored.
"""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from . import db
from .keys import domain_of
from .signals import PARKED_RX, SHOP_RX, all_signals, link_kind, redact

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
TEXT_PER_PAGE = 4000
MIN_WORDS = 40


def _clean_url(u):
    u = u.split("#")[0]
    return u.rstrip("/") if urlparse(u).path not in ("", "/") else u


def parse_page(html, url, kind):
    """HTML -> page dict {kind, url, title, description, lang, headings, menu, links, text} + extra info."""
    soup = BeautifulSoup(html or "", "html.parser")
    extra = {"phones": [], "linkedin": None, "links": []}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("tel:"):
            num = re.sub(r"[^\d+]", "", href[4:])
            if len(num) >= 8 and num not in extra["phones"]:
                extra["phones"].append(num)
        elif "linkedin.com/company/" in href.lower() and not extra["linkedin"]:
            extra["linkedin"] = href.split("?")[0]
        elif not href.lower().startswith(("mailto:", "javascript:")):
            extra["links"].append((urljoin(url, href), a.get_text(" ", strip=True)))
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    desc = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    lang = soup.html.get("lang") if soup.html else None
    menu = []
    for nav in soup.find_all(["nav"]) or soup.select("header"):
        for a in nav.find_all("a"):
            t = a.get_text(" ", strip=True)
            if t and t not in menu:
                menu.append(t)
    for tag in soup(["script", "style", "noscript", "svg", "template", "iframe"]):
        tag.decompose()
    headings = []
    for h in soup.find_all(["h1", "h2", "h3"]):
        t = " ".join(h.get_text(" ", strip=True).split())
        if t and t not in headings:
            headings.append(t)
    link_texts = [t for _, t in extra["links"] if t][:200]
    text = " ".join(soup.get_text(" ", strip=True).split())
    page = {"kind": kind, "url": url, "title": redact(title), "description": redact(desc.get("content", "") if desc
                                                                                  else ""),
            "lang": lang, "headings": [redact(h) for h in headings[:30]], "menu": [redact(m) for m in menu[:40]],
            "links": [redact(t) for t in link_texts], "text": redact(text)[:TEXT_PER_PAGE]}
    extra["has_shop"] = bool(SHOP_RX.search(text))
    return page, extra


def pick_subpages(home_url, links, max_pages):
    """One link per kind on the same domain; the shortest path wins (usually the overview page)."""
    dom = domain_of(home_url)
    best = {}
    for url, text in links:
        if not url.startswith("http") or domain_of(url) != dom:
            continue
        u = _clean_url(url)
        if u == _clean_url(home_url):
            continue
        kind = link_kind(u, text)
        if not kind:
            continue
        path = urlparse(u).path
        if kind not in best or len(path) < len(urlparse(best[kind]).path):
            best[kind] = u
    order = ["contact", "about", "services", "products", "jobs"]
    return [(k, best[k]) for k in order if k in best][:max(0, max_pages - 1)]


def _get(session, url):
    r = session.get(url, timeout=15, allow_redirects=True, headers={"User-Agent": UA, "Accept-Language": "en,*;q=0.5"})
    ctype = r.headers.get("content-type", "")
    if r.status_code >= 400 or ("html" not in ctype and "xml" not in ctype and ctype):
        return None, r.url, r.status_code
    r.encoding = r.encoding if r.encoding and r.encoding.lower() != "iso-8859-1" else r.apparent_encoding
    return r.text, r.url, r.status_code


def visit_site(website, max_pages=6, fetch=None):
    """Read one site. Returns {ok, status, final_url, pages, signals}. fetch(url) -> (html, final_url) can be
    swapped for a browser."""
    session = requests.Session()
    if fetch is None:
        def fetch(u):
            html, final, _ = _get(session, u)
            return html, final
    candidates = [website]
    if website.startswith("http://"):
        candidates.insert(0, "https://" + website[7:])
    html = final = None
    for u in candidates:
        try:
            html, final = fetch(u)
            if html:
                break
        except Exception:
            continue
    if not html:
        return {"ok": False, "status": "unreachable", "final_url": None, "pages": [], "signals": {}}
    home, extra = parse_page(html, final, "home")
    pages = [home]
    if PARKED_RX.search(home["text"][:1500]) and len(home["text"].split()) < 150:
        return {"ok": False, "status": "parked", "final_url": final, "pages": pages,
                "signals": all_signals(pages, extra)}
    for kind, url in pick_subpages(final, extra["links"], max_pages):
        try:
            sub_html, sub_final = fetch(url)
        except Exception:
            continue
        if not sub_html or domain_of(sub_final) != domain_of(final):
            continue
        page, ex = parse_page(sub_html, sub_final, kind)
        pages.append(page)
        extra["phones"] += [p for p in ex["phones"] if p not in extra["phones"]]
        extra["linkedin"] = extra["linkedin"] or ex["linkedin"]
        extra["has_shop"] = extra["has_shop"] or ex["has_shop"]
    words = sum(len(p["text"].split()) for p in pages)
    status = "ok" if words >= MIN_WORDS else "too_little_text"
    return {"ok": status == "ok", "status": status, "final_url": final, "pages": pages,
            "signals": all_signals(pages, extra)}


def _save(conn, company_id, result):
    for p in result["pages"]:
        p.pop("links", None)        # only used for the signals; not stored
    conn.execute("INSERT OR REPLACE INTO visit (company_id, visited_at, ok, status, final_url, signals, pages)"
                 " VALUES (?,?,?,?,?,?,?)", (company_id, db.now(), int(result["ok"]), result["status"],
                                            result["final_url"], json.dumps(result["signals"], ensure_ascii=False),
                                            json.dumps(result["pages"], ensure_ascii=False)))
    conn.commit()


class _BrowserFetch:
    """Headless Chromium for sites that need JavaScript. One page at a time, in the main thread."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._b = self._pw.chromium.launch(headless=True)
        self._ctx = self._b.new_context(user_agent=UA)
        return self

    def __call__(self, url):
        page = self._ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            return page.content(), page.url
        finally:
            page.close()

    def __exit__(self, *exc):
        for f in (self._b.close, self._pw.stop):
            try:
                f()
            except Exception:
                pass


def visit_companies(conn, niche, log=print, limit=None, again=False, use_browser=True):
    settings = niche.get("visit") or {}
    max_pages, threads = int(settings.get("max_pages", 6)), int(settings.get("threads", 6))
    sql = ("SELECT c.id, c.name, c.website FROM company c LEFT JOIN visit v ON v.company_id = c.id"
           " WHERE c.duplicate_of IS NULL" + ("" if again else " AND v.company_id IS NULL") + " ORDER BY c.id")
    rows = conn.execute(sql).fetchall()
    if limit:
        rows = rows[:int(limit)]
    if not rows:
        log("nothing to visit: every company has been visited (use --again to re-read)")
        return {}
    log(f"visiting {len(rows)} websites ({threads} at a time, up to {max_pages} pages each)")
    started = time.time()
    counts, retry = {}, []
    todo = [r for r in rows if r["website"]]
    for r in rows:
        if not r["website"]:
            _save(conn, r["id"], {"ok": False, "status": "no_website", "final_url": None, "pages": [], "signals": {}})
            counts["no_website"] = counts.get("no_website", 0) + 1
    with ThreadPoolExecutor(max_workers=threads) as pool:
        futures = {pool.submit(visit_site, r["website"], max_pages): r for r in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            r = futures[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = {"ok": False, "status": "unreachable", "final_url": None, "pages": [], "signals": {},
                       "error": str(e)}
            if res["status"] in ("too_little_text", "unreachable") and use_browser:
                retry.append(r)
            _save(conn, r["id"], res)
            counts[res["status"]] = counts.get(res["status"], 0) + 1
            log(f"[{i}/{len(todo)}] {r['name']}: {res['status']}, {len(res['pages'])} pages")
    if retry:
        log(f"{len(retry)} sites gave little or no text without JavaScript: trying them in a browser")
        try:
            with _BrowserFetch() as fetch:
                for r in retry:
                    try:
                        res = visit_site(r["website"], max_pages, fetch=fetch)
                    except Exception:
                        continue
                    if res["ok"]:
                        old = conn.execute("SELECT status FROM visit WHERE company_id = ?", (r["id"],)).fetchone()
                        counts[old["status"]] -= 1
                        counts["ok"] = counts.get("ok", 0) + 1
                        _save(conn, r["id"], res)
                        log(f"  {r['name']}: ok with a browser, {len(res['pages'])} pages")
        except Exception as e:
            log(f"  browser retry skipped ({type(e).__name__}: {e})")
    log(f"done in {(time.time() - started) / 60:.1f} min: " + ", ".join(f"{k} {v}" for k, v in counts.items() if v))
    return counts
