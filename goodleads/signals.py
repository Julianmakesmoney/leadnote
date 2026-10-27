"""General signals from a company's own website, in several languages: what they sell or do, open jobs, size,
founding year and contact page. Hints for the qualifier, never proof on their own: the qualifier quotes the page.

No e-mail addresses are collected: they are removed from the stored text before anything is saved.
"""

import re

EMAIL_RX = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

# Link kinds by URL path or link text. First match wins per link; one page per kind.
KINDS = [
    ("contact", r"contact|kontakt|contacto|contatt[io]|contato|nous-contacter|neem-contact|get-in-touch"),
    ("jobs", r"careers?|jobs?\b|vacatures?|vacancies|vacatures|werken-?bij|kom-werken|karriere|stellen(?:angebote)?|"
             r"emplois?|carrieres?|recrutement|empleo|trabaja|lavora-con-noi|join-(?:us|our-team)|working-at|"
             r"open-positions|solliciteren"),
    ("about", r"about|over-?ons|over-[a-z]+|wie-(?:zijn-)?wij|wie-we-zijn|ueber-uns|uber-uns|qui-sommes-nous|"
              r"a-propos|chi-siamo|quienes-somos|sobre-nos|our-story|ons-verhaal|company|bedrijf|unternehmen|"
              r"entreprise|empresa|azienda|team|ons-team|our-team|mensen|people"),
    ("services", r"services?|diensten|dienstverlening|solutions?|oplossingen|leistungen|prestations|servicios|"
                 r"servizi|servi[cç]os|what-we-do|wat-we-doen|expertise|aanbod|offering|specialisaties|"
                 r"werkzaamheden|cloud|managed|support"),
    ("products", r"products?|producten|assortiment|catalog(?:ue|us)?|shop|winkel|produkte|produits|productos|"
                 r"prodotti|produtos|range|brands|merken"),
]
_KIND_RX = [(k, re.compile(rx, re.I)) for k, rx in KINDS]
SKIP_LINK = re.compile(r"\.(?:pdf|jpe?g|png|gif|webp|svg|zip|docx?|xlsx?|pptx?|mp4|mp3)(?:[?#]|$)|"
                       r"login|log-in|inloggen|signin|sign-in|account|cart|winkelwagen|checkout|wishlist|"
                       r"privacy|cookie|terms|voorwaarden|disclaimer|/tag/|/category/|/author/|\?add-to-cart|"
                       r"mailto:|tel:|javascript:|whatsapp", re.I)

_NUM_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
              "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "hundred": 100,
              "twee": 2, "drie": 3, "vier": 4, "vijf": 5, "zes": 6, "zeven": 7, "acht": 8, "negen": 9, "tien": 10,
              "twaalf": 12, "vijftien": 15, "twintig": 20, "dertig": 30, "veertig": 40, "vijftig": 50,
              "zwei": 2, "drei": 3, "fünf": 5, "sechs": 6, "sieben": 7, "zehn": 10, "zwanzig": 20,
              "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "dix": 10, "vingt": 20, "trente": 30, "cinquante": 50}
_NUM = r"(\d{1,3}(?:[.,]\d{3})?|" + "|".join(sorted(_NUM_WORDS, key=len, reverse=True)) + r")"
_STAFF_WORDS = (r"employees|staff|people|professionals|specialists|engineers|consultants|experts|colleagues|"
                r"team members|technicians|accountants|advisors|advisers|"
                r"medewerk(?:st)?ers|werknemers|collega[’'`]?s|vakmensen|specialisten|adviseurs|monteurs|fte|"
                r"mitarbeiter(?:innen)?|mitarbeitende|angestellte|beschäftigte|kollegen|"
                r"collaborateurs|employés|salariés|personnes|"
                r"empleados|trabajadores|profesionales|dipendenti|collaboratori|funcionários|colaboradores")
STAFF_RX = re.compile(r"(?:more than|over|about|around|nearly|almost|ruim|meer dan|circa|ca\.?|bijna|zo'?n|"
                      r"über|mehr als|rund|plus de|environ|près de|más de|oltre|cerca de)?\s*(?<![\w.,])" + _NUM +
                      r"\s?\+?\s+(?:[a-zà-ÿ'-]+\s+){0,2}?(?:" + _STAFF_WORDS + r")\b", re.I)
TEAM_OF_RX = re.compile(r"\b(?:team of|team van|ein team von|une équipe de|un equipo de|un team di)\s+"
                        r"(?:more than |over |about |ruim |meer dan |circa |über |plus de |más de )?" + _NUM + r"\b", re.I)
FOUNDED_RX = re.compile(r"\b(?:founded|established|since|est\.|opgericht|sinds|gegründet|seit|fondée?|depuis|"
                        r"fundad[ao]|desde|fondat[ao]|dal|anno)\s*(?:in\s+)?(?:\d{1,2}[-/. ]\d{1,2}[-/. ])?"
                        r"((?:18|19|20)\d{2})\b", re.I)
SINCE_YEARS_RX = re.compile(r"\b(?:for|al|already|seit|depuis|desde|da)\s+(?:more than |over |ruim |meer dan |"
                            r"über |plus de |más de )?(\d{1,3})\s+(?:years|jaar|jahren|ans|años|anni)\b", re.I)
SIZE_PHRASE_RX = re.compile(r"\b(?:family[- ]owned|family business|familiebedrijf|familienunternehmen|"
                            r"entreprise familiale|empresa familiar|azienda familiare|small team|klein team|"
                            r"kleines team|petite équipe|one[- ]man|eenmanszaak|freelancer|zzp|sole trader|"
                            r"self-employed|mkb|sme|kmo|pme|offices? in \d+ countries|vestigingen in|"
                            r"locations across|nationwide|landelijk dekkend|wereldwijd|worldwide|global leader)\b", re.I)
NO_JOBS_RX = re.compile(r"no (?:current )?(?:open )?(?:vacancies|positions|openings|jobs)|geen (?:openstaande )?"
                        r"vacatures|op dit moment geen|keine offenen stellen|aucune offre|aucun poste|"
                        r"no hay vacantes|nessuna posizione", re.I)
ROLE_RX = re.compile(r"\b(?:engineer|developer|manager|consultant|specialist|technician|administrator|support|"
                     r"analyst|assistant|accountant|advisor|adviseur|medewerker|monteur|technicus|beheerder|"
                     r"ontwikkelaar|stagiair|intern|sales|account|officer|coordinator|coördinator|lead|director|"
                     r"mitarbeiter|berater|techniker|entwickler|leiter|comptable|technicien|conseiller|chargé|"
                     r"responsable|stagiaire|desarrollador|técnico|contable|tecnico|sviluppatore|"
                     r"m/v|m/f|v/m|m/w/d|h/f|f/h|m/v/x)\b", re.I)
PARKED_RX = re.compile(r"domain (?:is )?(?:for sale|parked)|this domain|buy this domain|domein (?:is )?te koop|"
                       r"under construction|coming soon|site in (?:aanbouw|ontwikkeling)|binnenkort online|"
                       r"website (?:in|under) (?:aanbouw|construction)|welcome to nginx|it works!|"
                       r"default web page|parked free|sedo|dan\.com|hugedomains|"
                       r"diese domain|ce domaine|en construcción|in costruzione", re.I)
SHOP_RX = re.compile(r"add to cart|in winkelwagen|winkelmand|in den warenkorb|ajouter au panier|añadir al carrito|"
                     r"aggiungi al carrello|checkout|afrekenen", re.I)


def link_kind(url, text):
    """Kind of a link ('contact', 'jobs', 'about', 'services', 'products') or None."""
    path = re.sub(r"^https?://[^/]+", "", url or "").lower()
    t = (text or "").lower().strip()
    if SKIP_LINK.search(url or ""):
        return None
    for kind, rx in _KIND_RX:
        if rx.search(path) or (t and len(t) <= 40 and rx.search(t.replace(" ", "-"))):
            return kind
    return None


def _num(s):
    s = s.lower()
    if s in _NUM_WORDS:
        return _NUM_WORDS[s]
    return int(re.sub(r"[.,]", "", s))


def snippet(text, start, end, around=60):
    a, b = max(0, start - around), min(len(text), end + around)
    return ("…" if a else "") + text[a:b].strip() + ("…" if b < len(text) else "")


def staff_count(pages):
    """First plausible staff number, about/home pages first: {value, quote, url} or None."""
    order = sorted(pages, key=lambda p: p["kind"] not in ("about", "home"))
    for p in order:
        for rx in (STAFF_RX, TEAM_OF_RX):
            for m in rx.finditer(p["text"]):
                n = _num(m.group(1))
                before = p["text"][max(0, m.start(1) - 2):m.start(1)]
                if re.search(r"[-–/]\s*$", before):
                    continue            # a range such as '1-49 employees' describes customers, not the company
                if 2 <= n <= 100000 and not (1900 <= n <= 2099):
                    return {"value": n, "quote": snippet(p["text"], m.start(), m.end()), "url": p["url"]}
    return None


def founded(pages):
    for p in sorted(pages, key=lambda p: p["kind"] not in ("about", "home")):
        m = FOUNDED_RX.search(p["text"])
        if m:
            return {"value": int(m.group(1)), "quote": snippet(p["text"], m.start(), m.end()), "url": p["url"]}
        m = SINCE_YEARS_RX.search(p["text"])
        if m and 2 <= int(m.group(1)) <= 200:
            return {"value": f"~{m.group(1)} years", "quote": snippet(p["text"], m.start(), m.end()), "url": p["url"]}
    return None


def size_phrases(pages):
    out, seen = [], set()
    for p in pages:
        for m in SIZE_PHRASE_RX.finditer(p["text"]):
            w = m.group(0).lower()
            if w in seen:
                continue
            seen.add(w)
            out.append({"phrase": w, "quote": snippet(p["text"], m.start(), m.end(), 50), "url": p["url"]})
            if len(out) >= 4:
                return out
    return out


def jobs(pages):
    """{page, titles, none_open}: the jobs page and what look like job titles on it."""
    jp = [p for p in pages if p["kind"] == "jobs"]
    if not jp:
        return {"page": None, "titles": [], "none_open": None}
    p = jp[0]
    titles = []
    for h in p.get("headings", []) + p.get("links", []):
        h = h.strip()
        if 4 <= len(h) <= 80 and ROLE_RX.search(h) and h.lower() not in (t.lower() for t in titles):
            titles.append(h)
    return {"page": p["url"], "titles": titles[:12], "none_open": bool(NO_JOBS_RX.search(p["text"]))}


def services(pages):
    """What they sell or do: the main menu and the headings of the services/products pages."""
    menu = []
    for p in pages:
        if p["kind"] == "home":
            menu = [m for m in p.get("menu", []) if 2 <= len(m) <= 40][:25]
    heads = []
    for p in pages:
        if p["kind"] in ("services", "products", "home"):
            for h in p.get("headings", []):
                if 3 <= len(h) <= 90 and h not in heads:
                    heads.append(h)
    return {"menu": menu, "headings": heads[:25]}


def keyword_counts(pages, words):
    text = " ".join(p["text"].lower() for p in pages)
    out = {}
    for w in words or []:
        n = len(re.findall(r"(?<!\w)" + re.escape(w.lower()), text))
        if n:
            out[w] = n
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def all_signals(pages, extra):
    """Signals for one site. extra: {phones, linkedin, has_shop} gathered while parsing."""
    home = next((p for p in pages if p["kind"] == "home"), pages[0] if pages else None)
    contact = next((p["url"] for p in pages if p["kind"] == "contact"), None)
    return {
        "title": home["title"] if home else None,
        "description": home.get("description") if home else None,
        "language": home.get("lang") if home else None,
        "services": services(pages),
        "jobs": jobs(pages),
        "staff": staff_count(pages),
        "founded": founded(pages),
        "size_phrases": size_phrases(pages),
        "contact_page": contact,
        "phone": (extra.get("phones") or [None])[0],
        "linkedin": extra.get("linkedin"),
        "webshop": bool(extra.get("has_shop")),
        "pages_read": [{"kind": p["kind"], "url": p["url"]} for p in pages],
    }


def redact(text):
    return EMAIL_RX.sub("[email]", text or "")
