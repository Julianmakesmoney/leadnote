"""Keys that tell whether two records are the same company: domain, phone, distance."""

import math
import re
from urllib.parse import urlparse

# Two-part public suffixes, so 'shop.firm.co.uk' -> 'firm.co.uk'.
_TWO_PART = {"co.uk", "org.uk", "ac.uk", "ltd.uk", "plc.uk", "me.uk", "com.au", "net.au", "org.au", "co.nz", "co.za",
             "com.br", "com.tr", "co.jp", "co.kr", "co.in", "com.mx", "com.ar", "com.sg", "com.my", "com.cn", "com.hk",
             "com.tw", "co.il", "com.pl", "co.at", "or.at", "com.es", "com.pt", "com.de", "eu.com", "uk.com", "us.com",
             "de.com", "gb.com", "gb.net", "uk.net", "se.net", "qc.ca", "com.ua", "co.id", "com.ph", "com.vn"}

# A profile on a platform or directory is not an own website.
_PLATFORMS = {"facebook.com", "fb.com", "linkedin.com", "instagram.com", "twitter.com", "x.com", "youtube.com",
              "google.com", "goo.gl", "g.page", "business.site", "tiktok.com", "pinterest.com", "wa.me", "linktr.ee",
              "yelp.com", "tripadvisor.com", "europages.com", "kompass.com", "cylex.nl", "kvk.nl", "goudengids.be",
              "goldenpages.be", "gelbeseiten.de", "pagesjaunes.fr", "yell.com", "yellowpages.com", "booking.com",
              "calendly.com"}

# Site builders where every subdomain is a different company: the full host is the key.
_SHARED_HOSTS = {"wixsite.com", "webnode.nl", "webnode.page", "weebly.com", "wordpress.com", "blogspot.com",
                 "jimdosite.com", "jimdo.com", "webador.nl", "webador.com", "myshopify.com", "squarespace.com",
                 "site123.me", "strikingly.com", "godaddysites.com", "webflow.io", "netlify.app", "github.io",
                 "vercel.app", "jouwweb.nl", "jouwweb.site", "one.com", "onepage.website", "carrd.co"}

# Country calling codes for the countries people are most likely to use. Others keep their raw digits.
CALLING_CODES = {"nl": "31", "be": "32", "de": "49", "fr": "33", "lu": "352", "uk": "44", "gb": "44", "ie": "353",
                 "es": "34", "pt": "351", "it": "39", "at": "43", "ch": "41", "dk": "45", "se": "46", "no": "47",
                 "fi": "358", "pl": "48", "cz": "420", "us": "1", "ca": "1", "au": "61", "nz": "64", "za": "27"}


def host_of(url):
    url = (url or "").strip()
    if not url:
        return ""
    host = (urlparse(url if "//" in url else "//" + url).hostname or "").lower().strip(".")
    return host[4:] if host.startswith("www.") else host


def domain_of(url):
    """Key for 'the same website': registrable domain without www ('https://shop.firm.nl/x' -> 'firm.nl').
    Full host for site builders; empty for platform profiles (Facebook, LinkedIn, directories)."""
    host = host_of(url)
    parts = [p for p in host.split(".") if p]
    if len(parts) < 2:
        return ""
    base = ".".join(parts[-3:]) if len(parts) >= 3 and ".".join(parts[-2:]) in _TWO_PART else ".".join(parts[-2:])
    if base in _PLATFORMS:
        return ""
    if base in _SHARED_HOSTS:
        return host
    return base


def real_website(url):
    """An ad click (google.com/aclk) or any Google link is not the company's own website."""
    if not url:
        return None
    host = host_of(url)
    if not host or "google." in host:
        return None
    return url if domain_of(url) else None


def normalise_phone(raw, country="nl"):
    """'+31 30 123 4567', '030-1234567' (country nl) -> '+31301234567'. Returns None when it does not look like a
    phone number. Only used to recognise the same company twice; never shown as a contact field."""
    raw = (raw or "").strip()
    digits = re.sub(r"\D", "", raw)
    if not 7 <= len(digits) <= 15:
        return None
    if raw.startswith("+"):
        return "+" + digits
    if digits.startswith("00"):
        return "+" + digits[2:]
    code = CALLING_CODES.get((country or "").lower())
    if code == "1":
        return "+1" + digits[-10:] if len(digits) >= 10 else None
    if code and digits.startswith("0"):
        return "+" + code + digits[1:]
    return digits


def distance_km(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(d))


_LEGAL = r"(?<![a-z])(?:b\.?\s?v\.?|n\.?\s?v\.?|v\.?o\.?f\.?|bvba|bv|srl|sprl|gmbh|ag|ltd|llc|inc|sa|sas|sarl|plc)(?![a-z])"


def name_key(name):
    """'Acme IT B.V.' and 'acme it bv' -> 'acmeit'."""
    n = (name or "").lower()
    n = re.sub(_LEGAL, " ", n)
    return re.sub(r"[^a-z0-9]", "", n)
