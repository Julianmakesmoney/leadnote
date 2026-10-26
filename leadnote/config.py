"""Where things live and what the niche looks like.

config/niche.json   what to search and where (written by /leadnote-setup; example in examples/)
config/criteria.md  who counts as a good prospect (read by /leadnote-qualify)
data/               the database and work files (never committed)

LEADNOTE_CONFIG and LEADNOTE_DATA (or --config / --data) point somewhere else, handy for several projects.
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULTS = {
    "name": "my-niche",
    "country": "us",                 # ISO 3166-1 alpha-2, decides the phone format and Google's gl=
    "language": "en",                # Google Maps interface language (hl=), also used to read list cards
    "areas": [],                     # free text for OpenStreetMap, e.g. "Utrecht, Netherlands" or "Belgium"
    "search_terms": [],
    "category_exclude": [],          # Maps categories that are certainly not a fit
    "name_keywords": [],             # a word in the name that rescues a company from category_exclude
    "keywords": [],                  # word stems in the sites' language; pick the sentences the AI reads
    "sieve_drop_words": [],          # a word in the name or Maps category that means a certain "no", without AI
    "keep_without_website": False,   # also keep companies that have no website on Maps
    "grid": {"cell_km": "auto", "max_depth": 3, "split_min_in_cell": 10},
    "pace": {"block": 12, "rest_minutes": 20, "wait_seconds": [4, 8]},
    "visit": {"max_pages": 6, "threads": 6},
    "max_qualify": 300,
    "max_brief": 25,                 # most cold-call briefings per run of /leadnote-brief (fit = yes only)
}


class Paths:
    def __init__(self, config_dir=None, data_dir=None):
        self.config = os.path.abspath(config_dir or os.environ.get("LEADNOTE_CONFIG") or os.path.join(ROOT, "config"))
        self.data = os.path.abspath(data_dir or os.environ.get("LEADNOTE_DATA") or os.path.join(ROOT, "data"))

    @property
    def niche(self):
        return os.path.join(self.config, "niche.json")

    @property
    def criteria(self):
        return os.path.join(self.config, "criteria.md")

    @property
    def db(self):
        return os.path.join(self.data, "leadnote.db")

    @property
    def areas_cache(self):
        return os.path.join(self.data, "areas.json")

    @property
    def pace_state(self):
        return os.path.join(self.data, "pace.json")

    @property
    def qualify_dir(self):
        return os.path.join(self.data, "qualify")


def load_niche(paths):
    if not os.path.exists(paths.niche):
        raise SystemExit(f"No {paths.niche} yet. Run /leadnote-setup in Claude Code, or copy examples/niche.json to "
                         "config/niche.json and edit it.")
    with open(paths.niche, encoding="utf-8") as f:
        user = json.load(f)
    niche = json.loads(json.dumps(DEFAULTS))
    for k, v in user.items():
        if isinstance(v, dict) and isinstance(niche.get(k), dict):
            niche[k].update(v)
        else:
            niche[k] = v
    niche["country"] = (niche.get("country") or "us").lower()
    niche["language"] = (niche.get("language") or "en").lower()
    if not niche["areas"]:
        raise SystemExit("config/niche.json has no 'areas'. Add at least one, e.g. \"Utrecht, Netherlands\".")
    if not niche["search_terms"]:
        raise SystemExit("config/niche.json has no 'search_terms'.")
    return niche
