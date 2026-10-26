"""Google Maps as a source: for every search term x grid cell, read the result list without clicking into listings.

Each list card already holds the name, website, category, Maps id and location, so one search reads up to ~120
companies. A list that comes back full (Maps shows no more than ~120) in a busy cell is split into four smaller
cells one zoom level deeper, so dense city centres are not cut off. Every search is stored, so a run can stop at any
moment (Ctrl+C, a crash, a block) and continue where it left off.

Google's terms of service do not allow automated reading of Maps. Dragnet keeps a slow work-rest rhythm, reads only
business listings, and never opens review pages or collects e-mail addresses. Use it at your own responsibility.
"""

import json
import os
import random
import re
import time
from urllib.parse import quote_plus

import requests

from . import area as areas
from . import db
from .keys import distance_km, domain_of, normalise_phone, real_website

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

FULL_FROM = 100              # from this many results a list counts as full (Maps shows ~120 at most, sometimes ~100)
MAX_SCROLLS = 60
MAX_SECONDS_PER_SEARCH = 150
STILL_SCROLLS_END = 6        # list did not grow for this many scrolls: treat as the end of the list
RESTART_EVERY = 15           # fresh browser after this many searches (memory)
BLOCK_AFTER = 3              # this many failed searches in a row = probably blocked
PAUSE_ON_BLOCK = 600         # first pause; then 20, 40, 60 min
MAX_BLOCKS_IN_A_ROW = 6      # then stop with a clear message
MAX_ATTEMPTS = 3
ADVERTISERS_PER_SEARCH = 1   # sponsored cards link to an ad; look up their real website on the listing page
TWIN_KM = 0.05               # same phone number within 50 m = the same company

BLOCK_MIN, BLOCK_MAX = 4, 40
REST_MIN, REST_MAX = 300, 2400

# ── Reading list cards (pure functions, tested without a browser) ─────────────────────────────────────────

_CARDS_JS = """() => Array.from(document.querySelectorAll("div[role='feed'] a.hfpxzc")).map(a => {
    const card = a.parentElement;
    const web = card ? card.querySelector("a[data-value='Website'], a[aria-label*='ebsite'], a[data-value='Site Web']") : null;
    return {name: a.getAttribute('aria-label'), href: a.href, text: card ? card.innerText : '',
            website: web ? web.href : null};
})"""
_PLACE_JS = """() => {
    const h1 = document.querySelector('h1');
    const cat = document.querySelector('button[jsaction*="category"]');
    const web = document.querySelector("a[data-item-id='authority']");
    const tel = document.querySelector("button[data-item-id^='phone:tel:']");
    return {name: h1 ? h1.innerText : null, text: cat ? cat.innerText + ' ·' : '', website: web ? web.href : null,
            phone: tel ? tel.getAttribute('data-item-id').replace('phone:tel:', '') : null};
}"""

_PRIVATE_USE = re.compile("[-\U000f0000-\U000ffffd\U00100000-\U0010fffd]")
_RATING = re.compile(r"^([1-5][,.]\d)\s*\(([\d.,\s  ]+)\)")
_NO_REVIEWS = re.compile(r"^(?:no reviews|geen reviews|aucun avis|keine rezensionen|keine bewertungen|sin reseñas|"
                         r"nessuna recensione|sem avaliações|brak opinii|inga recensioner|ingen anmeldelser)$", re.I)
_HOURS = re.compile(r"\b(?:open|opens|closed|closes|geopend|gesloten|opent|sluit|ouvert|ouvre|fermé|ferme|geöffnet|"
                    r"geschlossen|öffnet|schließt|abierto|abre|cerrado|cierra|aperto|apre|chiuso|chiude|aberto|abre|"
                    r"fechado|fecha|otwarte|zamknięte|öppet|stängt|åben|lukket|24 hours|24 uur|24h/24|24 stunden|"
                    r"binnenkort|soon|bientôt|tijdelijk|temporarily|temporairement|vorübergehend|permanently|definitief)\b",
                    re.I)
_SPONSORED = {"gesponsord", "sponsored", "sponsorisé", "gesponsert", "patrocinado", "sponsorizzato", "sponsorowane",
              "sponset", "sponsrad", "sponsoreret", "annonce", "ad", "anzeige", "advertentie"}
_BLOCKED_TEXT = re.compile(r"unusual traffic|ongebruikelijk verkeer|trafic inhabituel|ungewöhnlichen datenverkehr|"
                           r"tráfico inusual|traffico insolito|tráfego incomum|nietypowy ruch", re.I)
_NOT_FOUND_TEXT = re.compile(r"can't find|cannot find|niet vinden|ne trouve pas|introuvable|nicht finden|"
                             r"no encuentra|non trova|não encontra|nie może znaleźć|no results|geen resultaten|"
                             r"aucun résultat|keine ergebnisse|sin resultados|nessun risultato", re.I)
_END_TEXT = re.compile(r"reached the end|einde van de lijst|fin de la liste|ende der liste|final de la lista|"
                       r"fine dell'elenco|fim da lista|koniec listy", re.I)


def parse_href(href):
    """Maps link of a list card -> {cid, place_id, lat, lng}. Everything is inside the link itself."""
    href = href or ""
    out = {"cid": None, "place_id": None, "lat": None, "lng": None}
    m = re.search(r"!1s0x[0-9a-f]+:(0x[0-9a-f]+)", href)
    if m:
        out["cid"] = str(int(m.group(1), 16))
    m = re.search(r"!19s(ChIJ[\w-]+)", href)
    if m:
        out["place_id"] = m.group(1)
    m = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", href)
    if m:
        out["lat"], out["lng"] = float(m.group(1)), float(m.group(2))
    return out


def looks_like_rating(text):
    """'4,6(33)' or '4.6 (1,234)' (also with an icon character in it) is a rating, not a category."""
    t = _PRIVATE_USE.sub("", text or "").strip()
    return bool(t) and bool(re.fullmatch(r"[1-5][,.]\d\s*(?:\([\d.,\s  ]+\))?", t))


def _int(text):
    digits = re.sub(r"\D", "", text or "")
    return int(digits) if digits else None


def parse_card_text(text):
    """Text of a list card -> {category, address, sponsored, phone_raw, rating, reviews}.
    The category is the first piece before a '·' on a line after the name (after the rating, if the rating shares
    the line); the piece after it is the street address."""
    lines = [l.strip() for l in _PRIVATE_USE.sub("", text or "").replace(" | ", "\n").split("\n") if l.strip()]
    category = address = None
    for line in lines[1:] or lines:
        if "·" not in line:
            continue
        pieces = [p.strip() for p in line.split("·")]
        after_rating = False
        while len(pieces) > 1 and pieces[0] and looks_like_rating(pieces[0]):
            pieces.pop(0)
            after_rating = True
        cand = pieces[0]
        if after_rating and (re.search(r"\d", cand) or not re.search(r"[^\W\d_]", cand)):
            continue                    # address or price level ('€€') after the rating: the next line has it
        if not cand or re.fullmatch(r"[\d.,() ]+", cand) or _HOURS.search(cand) or not re.search(r"[^\W\d_]", cand):
            continue
        category = cand
        rest = [p for p in pieces[1:] if p and not _HOURS.search(p) and not re.fullmatch(r"[\W\d_]*[€$£¥]+", p)]
        if rest and not re.fullmatch(r"\+?[\d\s()\-/.]{7,}", rest[0]):
            address = rest[0]
        break
    phone = None
    for piece in (x.strip() for l in lines for x in l.split("·")):
        digits = re.sub(r"\D", "", piece)
        if re.fullmatch(r"\+?\(?\d[\d\s()\-/.]{6,18}\d", piece) and 8 <= len(digits) <= 15:
            phone = piece
            break
    rating = reviews = None
    for l in lines:
        m = _RATING.match(l)
        if m:
            rating, reviews = float(m.group(1).replace(",", ".")), _int(m.group(2))
            break
        if _NO_REVIEWS.match(l):
            reviews = 0
            break
    sponsored = any(l.lower() in _SPONSORED for l in lines)
    return {"category": category, "address": address, "sponsored": sponsored, "phone_raw": phone,
            "rating": rating, "reviews": reviews}


def search_url(term, lat, lng, zoom, language="en", country=None):
    gl = f"&gl={country}" if country else ""
    return f"https://www.google.com/maps/search/{quote_plus(term)}/@{lat},{lng},{zoom}z?hl={language}{gl}"


def category_out(category, name, exclude, keywords):
    """True when a word from the exclude list is in the Maps category (whole word, plural allowed) and no name
    keyword appears in the name or category. Unknown category passes."""
    c = (category or "").lower()
    if not c:
        return False
    hit = False
    for w in exclude:
        w = (w or "").lower().strip()
        if w and re.search(r"(?<![\w])" + re.escape(w) + r"(?:s|es|'s|en)?(?![\w])", c):
            hit = True
            break
    if not hit:
        return False
    return not has_keyword(f"{name or ''} {category or ''}", keywords)


def has_keyword(text, keywords):
    """A keyword counts at the start of a word: 'Hydraulics' matches 'hydraul', 'Max Promotion' does not match 'motion'."""
    t = (text or "").lower()
    return any(re.search(r"(?<![\w])" + re.escape(k.lower()), t) for k in keywords if k)


def should_split(cell_km, depth, results, in_cell_count, median_last_km, min_in_cell, max_depth, new_places=None):
    """Split when the list was full (Maps shows no more), the search still found enough new places (otherwise the
    smaller cells mostly repeat what is known), and the cell itself is busy: enough results inside the cell, and
    either half the list lies inside it or the last results are still close by. A full list made of far-away
    companies (Maps tops up) is not a busy cell."""
    if depth >= max_depth or results < FULL_FROM or in_cell_count < min_in_cell:
        return False
    if new_places is not None and new_places < min_in_cell:
        return False
    return in_cell_count >= results // 2 or (median_last_km is not None and median_last_km <= cell_km)


# ── Browser ─────────────────────────────────────────────────────────────────────────────────────────────────

class MapsBrowser:
    def __init__(self, language="en", country=None, visible=False):
        self.language, self.country, self.visible = language, country, visible
        self.page = None
        self._state = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._start()
        return self

    def _start(self, state=None):
        locale = f"{self.language}-{(self.country or 'us').upper()}"
        self._browser = self._pw.chromium.launch(
            headless=not self.visible, args=["--disable-blink-features=AutomationControlled"])
        self._context = self._browser.new_context(locale=locale, user_agent=UA, viewport={"width": 1280, "height": 900},
                                                  storage_state=state)
        self.page = None
        self._new_tab()

    def _new_tab(self):
        """A fresh tab per search: a reused tab sometimes read the list before it had loaded."""
        if self.page:
            try:
                self.page.close()
            except Exception:
                pass
        self.page = self._context.new_page()
        self.page.set_default_timeout(20000)

    def restart(self, forget=False):
        """Fresh browser. Cookies (including the cookie choice) carry over, so Google sees one returning visitor;
        forget=True after a block starts clean."""
        state = None
        if not forget:
            try:
                state = self._context.storage_state()
            except Exception:
                state = None
        try:
            self._browser.close()
        except Exception:
            pass
        self._start(state)

    def pause(self, forget=False):
        self._state = None
        if not forget:
            try:
                self._state = self._context.storage_state()
            except Exception:
                pass
        for close in (self._browser.close, self._pw.stop):
            try:
                close()
            except Exception:
                pass

    def resume(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._start(self._state)

    def __exit__(self, *exc):
        for close in (self._browser.close, self._pw.stop):
            try:
                close()
            except Exception:
                pass

    def _reject_cookies(self):
        """Google's consent page: always the most privacy-preserving choice (reject all)."""
        pg = self.page
        if "consent" not in pg.url:
            return
        selectors = ["form:has(input[name='set_eom'][value='true']) button",
                     "button:has-text('Reject all')", "button:has-text('Alles afwijzen')",
                     "button:has-text('Tout refuser')", "button:has-text('Alle ablehnen')",
                     "button:has-text('Rechazar todo')", "button:has-text('Rifiuta tutto')",
                     "button:has-text('Rejeitar tudo')", "button:has-text('Odrzuć wszystko')"]
        for sel in selectors:
            try:
                btn = pg.locator(sel).first
                if btn.is_visible(timeout=2000):
                    btn.click()
                    pg.wait_for_load_state("domcontentloaded")
                    time.sleep(2)
                    return
            except Exception:
                pass

    def place_by_cid(self, cid):
        """Open one listing page. (status, {name, website, phone}); status ok | error | blocked."""
        self._new_tab()
        pg = self.page
        try:
            pg.goto(f"https://www.google.com/maps?cid={cid}&hl={self.language}", wait_until="domcontentloaded",
                    timeout=30000)
            self._reject_cookies()
            if "/sorry/" in pg.url:
                return "blocked", {}
            try:
                pg.wait_for_selector("h1", timeout=15000)
            except Exception:
                try:
                    body = pg.inner_text("body", timeout=5000)
                except Exception:
                    body = ""
                return ("blocked" if _BLOCKED_TEXT.search(body) else "error"), {}
            try:
                pg.wait_for_function("""() => document.querySelector("a[data-item-id='authority'],"
                    + " button[data-item-id^='phone:tel:'], button[data-item-id='address']")""", timeout=6000)
            except Exception:
                pass
            return "ok", pg.evaluate(_PLACE_JS)
        except Exception as e:
            if "Closed" in type(e).__name__ or "Disconnected" in type(e).__name__:
                raise
            return "error", {}

    def search(self, url):
        """(status, cards, end_reached). status ok | empty | error | blocked. 'empty' only counts when a second try
        in a fresh tab is empty as well."""
        status, cards, end = self._search_once(url)
        if status == "empty":
            time.sleep(4)
            status, cards, end = self._search_once(url)
        return status, cards, end

    def _search_once(self, url):
        self._new_tab()
        pg = self.page
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=30000)
            self._reject_cookies()
            if "consent" in pg.url or "/maps" not in pg.url:
                pg.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            if "Closed" in type(e).__name__ or "Disconnected" in type(e).__name__:
                raise
            return "error", [], False
        if "/sorry/" in pg.url:
            return "blocked", [], False
        try:
            pg.wait_for_function("""() => document.querySelector("div[role='feed'] a.hfpxzc")
                || location.pathname.includes('/maps/place/')
                || /""" + _NOT_FOUND_TEXT.pattern + "|" + _BLOCKED_TEXT.pattern + """/i.test(document.body.innerText)""",
                                 timeout=20000)
        except Exception:
            pass
        try:
            body = pg.inner_text("body", timeout=5000)
        except Exception:
            body = ""
        if _BLOCKED_TEXT.search(body):
            return "blocked", [], False
        if pg.locator("div[role='feed']").count() == 0:
            if "/maps/place/" in pg.url:            # Maps jumped straight to one listing
                place = pg.evaluate(_PLACE_JS)
                place["href"] = pg.url
                return "ok", [place], False          # not 'end reached': one hit for a whole cell is suspicious
            if _NOT_FOUND_TEXT.search(body):
                return "empty", [], True
            return "error", [], False

        start, previous, still, end = time.time(), 0, 0, False
        for _ in range(MAX_SCROLLS):
            pg.locator("div[role='feed']").evaluate("el => el.scrollBy(0, 3000)")
            time.sleep(1.2)
            n = pg.locator("div[role='feed'] a.hfpxzc").count()
            if _END_TEXT.search(pg.locator("div[role='feed']").inner_text()):
                end = True
                break
            still = still + 1 if n == previous else 0
            previous = n
            if still >= STILL_SCROLLS_END and n < FULL_FROM:
                end = True                           # language-independent: the list stopped growing
                break
            if still >= 10 or time.time() - start > MAX_SECONDS_PER_SEARCH:
                break
        return "ok", pg.evaluate(_CARDS_JS), end


# ── Work-rest rhythm ────────────────────────────────────────────────────────────────────────────────────────

def _sleep(seconds, log=None):
    end = time.time() + seconds
    while True:
        left = end - time.time()
        if left <= 0:
            return
        time.sleep(min(left, 30))


class Pace:
    """Google tends to block after a fixed NUMBER of searches in a row, not after a time. So: a work block of N
    searches at a normal tempo, then a rest with the browser closed, before Google blocks. A block or an empty list
    at the end of a block makes the next block 2 shorter; three clean blocks in a row make it 1 longer. The learned
    numbers are kept in data/pace.json across runs."""

    def __init__(self, settings, state_path, log=print):
        self.log, self.path = log, state_path
        self.wait = tuple(settings.get("wait_seconds") or (4, 8))
        self.block = int(settings.get("block") or 12)
        self.rest = int(float(settings.get("rest_minutes") or 20) * 60)
        self.clean = 0
        self.blocks_in_a_row = 0
        self.last_block = 0.0
        self.rest_until = 0.0
        try:
            with open(state_path, encoding="utf-8") as f:
                saved = json.load(f)
            if saved.get("settings") == [self.block, self.rest]:     # learned values only for the same settings
                self.block = min(max(int(saved["block"]), BLOCK_MIN), BLOCK_MAX)
                self.rest = min(max(int(saved["rest"]), REST_MIN), REST_MAX)
                self.clean = int(saved.get("clean", 0))
            if time.time() - float(saved.get("last_block", 0)) < 7200:
                self.blocks_in_a_row = int(saved.get("blocks_in_a_row", 0))
            self.rest_until = min(float(saved.get("rest_until", 0)), time.time() + REST_MAX)
        except Exception:
            pass
        self._settings = [int(settings.get("block") or 12), int(float(settings.get("rest_minutes") or 20) * 60)]
        self.done = 0

    def save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"settings": self._settings, "block": self.block, "rest": self.rest, "clean": self.clean,
                           "blocks_in_a_row": self.blocks_in_a_row, "last_block": self.last_block,
                           "rest_until": self.rest_until, "saved": db.now()}, f)
            os.replace(tmp, self.path)
        except Exception:
            pass

    def next(self, browser, doubt=False, more_work=True):
        """After a search without a (recognised) block: short wait, or a rest when the work block is full."""
        self.done += 1
        if self.done < self.block:
            time.sleep(random.uniform(*self.wait))
            return
        if doubt:
            self.clean = 0
            self.block = max(self.block - 2, BLOCK_MIN)
            self.log(f"  empty list at the end of a work block: {self.block} searches per block from now on")
        else:
            self.clean += 1
            if self.clean % 3 == 0 and self.block < BLOCK_MAX:
                self.block += 1
                self.log(f"  {self.clean} clean blocks: {self.block} searches per block from now on")
        self.save()
        if not more_work:
            return
        self.log(f"  work block done: resting {self.rest // 60} min before Google would block (Ctrl+C is safe)")
        browser.pause()
        self.sleep(self.rest)
        browser.resume()
        self.done = 0

    def sleep(self, seconds):
        self.rest_until = time.time() + seconds
        self.save()
        _sleep(seconds)

    def ok(self):
        if self.blocks_in_a_row:
            self.blocks_in_a_row = 0
            self.save()

    def blocked(self, right_after_rest=False):
        self.blocks_in_a_row += 1
        self.last_block = time.time()
        self.clean = 0
        if self.blocks_in_a_row == 1:
            if right_after_rest:
                self.rest = min(self.rest + 300, REST_MAX)
                self.log(f"  blocked right after a rest: rests are {self.rest // 60} min from now on")
            else:
                self.block = max(self.block - 2, BLOCK_MIN)
                self.log(f"  shorter work blocks: {self.block} searches, then {self.rest // 60} min rest")
        self.save()
        return self.blocks_in_a_row


# ── Planning ────────────────────────────────────────────────────────────────────────────────────────────────

def load_areas(niche, paths):
    return [areas.lookup(q, paths.areas_cache, niche["language"]) for q in niche["areas"]]


def plan(conn, niche, area_list):
    """Put every grid cell x search term in the queue (existing rows stay). Returns the number of new rows."""
    new = 0
    setting = (niche.get("grid") or {}).get("cell_km", "auto")
    for a in area_list:
        cell_km = areas.auto_cell_km(a) if setting in (None, "auto") else float(setting)
        for cell in areas.grid(a, cell_km):
            zoom = areas.zoom_for(cell_km, cell["lat"])
            for term in niche["search_terms"]:
                new += conn.execute(
                    "INSERT OR IGNORE INTO search (term, area, cell, lat, lng, zoom, cell_km, depth, status, attempts)"
                    " VALUES (?,?,?,?,?,?,?,0,'planned',0)",
                    (term, a["query"], cell["label"], cell["lat"], cell["lng"], zoom, cell_km)).rowcount
    conn.commit()
    return new


def plan_children(conn, row):
    new = 0
    for suffix, lat, lng, km in areas.children(row["lat"], row["lng"], row["cell_km"]):
        new += conn.execute(
            "INSERT OR IGNORE INTO search (term, area, cell, lat, lng, zoom, cell_km, depth, parent_id, status, attempts)"
            " VALUES (?,?,?,?,?,?,?,?,?,'planned',0)",
            (row["term"], row["area"], f"{row['cell']} {suffix}", lat, lng, min(int(row["zoom"]) + 1, 18), km,
             (row["depth"] or 0) + 1, row["id"])).rowcount
    return new


def next_search(conn, terms):
    """First the whole grid (depth 0), then each level deeper. Within a level first what was never tried."""
    return conn.execute(
        f"SELECT * FROM search WHERE term IN ({','.join('?' * len(terms))})"
        " AND ((status IN ('planned','error','blocked') AND attempts < ?) OR (status = 'empty' AND attempts < 2))"
        " ORDER BY depth, status <> 'planned', id LIMIT 1", (*terms, MAX_ATTEMPTS)).fetchone()


def queue_left(conn, terms):
    return conn.execute(
        f"SELECT COUNT(*) FROM search WHERE term IN ({','.join('?' * len(terms))})"
        " AND ((status IN ('planned','error','blocked') AND attempts < ?) OR (status = 'empty' AND attempts < 2))",
        (*terms, MAX_ATTEMPTS)).fetchone()[0]


# ── Storing results ─────────────────────────────────────────────────────────────────────────────────────────

def _company_for(conn, p):
    """Create or find the company for a place that passed the gate. Key: own domain, else 'nosite:<cid>'."""
    domain = domain_of(p["website"]) if p["website"] else ""
    key = domain or f"nosite:{p['cid']}"
    conn.execute("INSERT OR IGNORE INTO company (key, name, website, domain, phone, category, address, area, lat, lng,"
                 " rating, reviews, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (key, p["name"], p["website"], domain or None, p["phone"], p["category"], p["address"], p["area"],
                  p["lat"], p["lng"], p["rating"], p["reviews"], db.now()))
    row = conn.execute("SELECT id FROM company WHERE key = ?", (key,)).fetchone()
    conn.execute("UPDATE company SET phone = COALESCE(phone, ?), category = COALESCE(category, ?),"
                 " address = COALESCE(address, ?), rating = COALESCE(?, rating),"
                 " reviews = MAX(COALESCE(reviews, 0), COALESCE(?, 0)) WHERE id = ?",
                 (p["phone"], p["category"], p["address"], p["rating"], p["reviews"], row["id"]))
    return row["id"]


def _gate(p, niche, area_list):
    for a in area_list:
        if areas.contains(a, p["lat"], p["lng"]):
            p["area"] = a["query"]
            break
    else:
        return "outside_area"
    if category_out(p["category"], p["name"], niche.get("category_exclude", []), niche.get("name_keywords", [])):
        return "category_out"
    if not p["website"]:
        if p["sponsored"]:
            return "sponsored_unknown"            # its card links to the ad; the listing page has the real site
        if niche.get("keep_without_website") or has_keyword(f"{p['name']} {p['category'] or ''}",
                                                            niche.get("name_keywords", [])):
            return "pass"
        return "no_website"
    return "pass"


def process_cards(conn, niche, area_list, row, cards):
    """Store the places of one search and create companies. Returns counts used for the split decision."""
    now = db.now()
    seen = {}
    for rank, card in enumerate(cards, 1):
        ids = parse_href(card.get("href"))
        if not ids["cid"]:
            continue
        info = parse_card_text(card.get("text"))
        p = {"cid": ids["cid"], "place_id": ids["place_id"], "lat": ids["lat"], "lng": ids["lng"],
             "name": card.get("name"), "category": info["category"], "address": info["address"],
             "website": real_website(card.get("website")), "sponsored": info["sponsored"], "rank": rank,
             "phone": normalise_phone(card.get("phone") or info["phone_raw"], niche["country"]),
             "rating": info["rating"], "reviews": info["reviews"], "area": None}
        if p["cid"] in seen:        # same place twice in one list (organic + ad): merge
            e = seen[p["cid"]]
            e["website"] = e["website"] or p["website"]
            e["sponsored"] = e["sponsored"] and p["sponsored"]
            e["phone"] = e["phone"] or p["phone"]
            e["category"] = e["category"] or p["category"]
            continue
        seen[p["cid"]] = p
    places = list(seen.values())

    out = {"new_places": 0, "in_cell": 0, "median_last_km": None}
    dists = []
    for p in places:
        if p["lat"] is None:
            continue
        dists.append(distance_km(row["lat"], row["lng"], p["lat"], p["lng"]))
        if areas.in_cell(p["lat"], p["lng"], row["lat"], row["lng"], row["cell_km"]):
            out["in_cell"] += 1
    last = sorted(dists[-20:])
    if last:
        out["median_last_km"] = round(last[len(last) // 2], 1)

    for p in places:
        conn.execute("INSERT OR IGNORE INTO hit (search_id, cid, rank) VALUES (?,?,?)", (row["id"], p["cid"], p["rank"]))
        old = conn.execute("SELECT * FROM place WHERE cid = ?", (p["cid"],)).fetchone()
        if old:
            conn.execute("UPDATE place SET last_seen = ?, phone = COALESCE(phone, ?), rating = COALESCE(?, rating),"
                         " reviews = COALESCE(?, reviews), category = COALESCE(category, ?) WHERE cid = ?",
                         (now, p["phone"], p["rating"], p["reviews"], p["category"], p["cid"]))
            if old["website"] or not p["website"]:
                continue
            # a website appeared (e.g. the organic card after the ad card): run the gate again below
        else:
            out["new_places"] += 1
        gate = _gate(p, niche, area_list)
        company_id = _company_for(conn, p) if gate == "pass" else None
        conn.execute("INSERT INTO place (cid, place_id, name, category, lat, lng, address, website, domain, phone,"
                     " rating, reviews, sponsored, area, gate, company_id, first_seen, last_seen)"
                     " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                     " ON CONFLICT (cid) DO UPDATE SET website = excluded.website, domain = excluded.domain,"
                     " gate = excluded.gate, company_id = COALESCE(excluded.company_id, place.company_id),"
                     " area = COALESCE(place.area, excluded.area), last_seen = excluded.last_seen",
                     (p["cid"], p["place_id"], p["name"], p["category"], p["lat"], p["lng"], p["address"],
                      p["website"], domain_of(p["website"]) if p["website"] else None, p["phone"], p["rating"],
                      p["reviews"], int(p["sponsored"]), p["area"], gate, company_id, now, now))
    return out


def lookup_advertisers(conn, niche, area_list, browser, limit=ADVERTISERS_PER_SEARCH):
    """Sponsored cards link to their ad, not their site: read the real website from their listing page."""
    rows = conn.execute("SELECT * FROM place WHERE gate = 'sponsored_unknown' ORDER BY rowid LIMIT ?", (limit,)).fetchall()
    for r in rows:
        status, info = browser.place_by_cid(r["cid"])
        if status != "ok":
            return status
        p = dict(r)
        p["website"] = real_website(info.get("website"))
        p["sponsored"] = False
        p["phone"] = p["phone"] or normalise_phone(info.get("phone"), niche["country"])
        gate = _gate(p, niche, area_list)
        company_id = _company_for(conn, p) if gate == "pass" else None
        conn.execute("UPDATE place SET website = ?, domain = ?, gate = ?, company_id = ?, phone = ? WHERE cid = ?",
                     (p["website"], domain_of(p["website"]) if p["website"] else None, gate, company_id, p["phone"],
                      p["cid"]))
        conn.commit()
    return "ok"


def merge_twins(conn):
    """Companies with a listing that has the same phone number within 50 m of each other are one company (e.g. a
    second website or a duplicate listing). The one with a website (then the lowest id) stays; the others get
    duplicate_of. Nothing is deleted. Returns the number merged."""
    import collections
    by_phone = collections.defaultdict(list)
    for r in conn.execute("SELECT p.phone, p.lat, p.lng, COALESCE(c.duplicate_of, c.id) AS cid, c.key FROM place p"
                          " JOIN company c ON c.id = p.company_id WHERE p.phone IS NOT NULL AND p.lat IS NOT NULL"):
        by_phone[r["phone"]].append(r)
    merged = 0
    for rows in by_phone.values():
        if len({r["cid"] for r in rows}) < 2:
            continue
        parent = {r["cid"]: r["cid"] for r in rows}

        def root(x):
            while parent[x] != x:
                x = parent[x]
            return x
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if a["cid"] != b["cid"] and distance_km(a["lat"], a["lng"], b["lat"], b["lng"]) <= TWIN_KM:
                    parent[root(a["cid"])] = root(b["cid"])
        groups = collections.defaultdict(set)
        for c in parent:
            groups[root(c)].add(c)
        keys = {r["cid"]: r["key"] for r in rows}
        for group in groups.values():
            if len(group) < 2:
                continue
            head = min(group, key=lambda c: (keys[c].startswith("nosite:"), c))
            for c in group - {head}:
                merged += conn.execute("UPDATE company SET duplicate_of = ? WHERE id = ? AND duplicate_of IS NULL",
                                       (head, c)).rowcount
    conn.commit()
    return merged


# ── The run ─────────────────────────────────────────────────────────────────────────────────────────────────

def online():
    try:
        requests.head("https://www.google.com", timeout=8)
        return True
    except Exception:
        return False


def wait_for_internet(log):
    """True if the connection was gone (and is back now)."""
    if online():
        return False
    log("  no internet: waiting until the connection is back")
    while not online():
        time.sleep(30)
    return True


def totals(conn):
    r = conn.execute("SELECT SUM(status IN ('ok','empty')) AS searches,"
                     " COALESCE(SUM(CASE WHEN status = 'ok' THEN results END), 0) AS results FROM search").fetchone()
    unique = conn.execute("SELECT COUNT(*) FROM place").fetchone()[0]
    companies = conn.execute("SELECT COUNT(*) FROM company WHERE duplicate_of IS NULL").fetchone()[0]
    return {"searches": r["searches"] or 0, "results": r["results"], "unique": unique, "companies": companies}


def find(conn, niche, paths, log=print, max_searches=None, visible=False):
    area_list = load_areas(niche, paths)
    for a in area_list:
        log(f"area: {a['query']} -> {a.get('display_name') or a['name']}")
    new = plan(conn, niche, area_list)
    terms = niche["search_terms"]
    log(f"queue: {new} new searches planned, {queue_left(conn, terms)} to do")
    grid = niche.get("grid") or {}
    max_depth, min_in_cell = int(grid.get("max_depth", 3)), int(grid.get("split_min_in_cell", 10))
    pace = Pace(niche.get("pace") or {}, paths.pace_state, log)
    log(f"rhythm: {pace.block} searches, then {pace.rest // 60} min rest")
    if pace.rest_until > time.time() + 5:
        log(f"  a rest was still running: {int(pace.rest_until - time.time()) // 60} min first")
        _sleep(pace.rest_until - time.time())

    done = 0
    suspect = []
    started = time.time()
    with MapsBrowser(niche["language"], niche["country"], visible) as browser:
        while True:
            if max_searches and done >= max_searches:
                log(f"stopped at --max {max_searches}; run find again to continue")
                break
            row = next_search(conn, terms)
            if not row:
                break
            if done and done % RESTART_EVERY == 0:
                browser.restart()
            attempt = (row["attempts"] or 0) + 1
            conn.execute("UPDATE search SET attempts = ?, started_at = ? WHERE id = ?", (attempt, db.now(), row["id"]))
            conn.commit()
            try:
                status, cards, end = browser.search(search_url(row["term"], row["lat"], row["lng"], row["zoom"],
                                                               niche["language"], niche["country"]))
            except Exception as e:
                log(f"  browser fell over ({type(e).__name__}), restarting")
                browser.restart()
                status, cards, end = "error", [], False
            done += 1
            if status in ("error", "empty") and wait_for_internet(log):
                conn.execute("UPDATE search SET status = 'planned', attempts = attempts - 1 WHERE id = ?", (row["id"],))
                conn.commit()
                continue

            res = {"new_places": 0, "in_cell": 0, "median_last_km": None}
            if status == "ok":
                try:
                    res = process_cards(conn, niche, area_list, row, cards)
                except Exception as e:
                    conn.rollback()
                    log(f"  could not process the list ({type(e).__name__}: {e}); will retry")
                    status = "error"
                if status == "ok" and not end and len(cards) < FULL_FROM and attempt < MAX_ATTEMPTS:
                    status = "error"            # list did not load to the end and is not full: incomplete, retry
            full = int(len(cards) >= FULL_FROM)
            conn.execute("UPDATE search SET status=?, done_at=?, results=?, end_reached=?, full=?, in_cell=?,"
                         " new_places=? WHERE id=?", (status, db.now(), len(cards), int(end), full, res["in_cell"],
                                                       res["new_places"], row["id"]))
            planned = 0
            if status == "ok" and should_split(row["cell_km"], row["depth"] or 0, len(cards), res["in_cell"],
                                               res["median_last_km"], min_in_cell, max_depth, res["new_places"]):
                planned = plan_children(conn, row)
            conn.commit()
            if status == "ok":
                try:
                    if lookup_advertisers(conn, niche, area_list, browser) == "blocked":
                        status = "blocked"
                except Exception as e:
                    conn.rollback()
                    log(f"  advertiser lookup failed ({type(e).__name__}), later")
            t = totals(conn)
            log(f"[{done}] {row['term']} @ {row['cell']} (level {row['depth']}): {status}, {len(cards)} results"
                f"{' (full)' if full else ''}, {res['in_cell']} in cell, {res['new_places']} new"
                f"{f', split into {planned}' if planned else ''}"
                f"  | total: {t['searches']} searches, {t['results']} results, {t['unique']} unique,"
                f" {t['companies']} companies")

            no_result = status == "blocked" or (status in ("error", "empty") and not cards)
            suspect = suspect + [row["id"]] if no_result else []
            if status == "ok":
                pace.ok()
            if status == "blocked" or len(suspect) >= BLOCK_AFTER or (no_result and pace.blocks_in_a_row):
                right_after_rest = len(suspect) == pace.done + 1
                for sid in suspect:     # these did not really count
                    conn.execute("UPDATE search SET status = 'planned', attempts = MAX(attempts - 1, 0) WHERE id = ?",
                                 (sid,))
                conn.commit()
                suspect = []
                n = pace.blocked(right_after_rest)
                if n >= MAX_BLOCKS_IN_A_ROW:
                    log(f"!!! {n} blocks in a row: stopped. Google is blocking, or the Maps page changed. Start again"
                        " later; nothing is lost.")
                    break
                pause = min(PAUSE_ON_BLOCK * 2 ** (n - 1), 3600)
                log(f"  probably blocked by Google: pausing {pause // 60} min, then a fresh browser")
                browser.pause(forget=True)
                pace.sleep(pause)
                browser.resume()
                pace.done = 0
            else:
                more = not (max_searches and done >= max_searches) and queue_left(conn, terms) > 0
                pace.next(browser, doubt=bool(suspect), more_work=more)

    merged = merge_twins(conn)
    t = totals(conn)
    minutes = (time.time() - started) / 60
    log(f"done in {minutes:.0f} min: {done} searches this run{f', {merged} duplicates merged' if merged else ''}."
        f" Total: {t['searches']} searches, {t['results']} results, {t['unique']} unique places,"
        f" {t['companies']} companies. {queue_left(conn, terms)} searches left in the queue.")
    return t
