"""SQLite storage. One file per project (data/goodleads.db). Only what finding, visiting and qualifying need."""

import os
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS search (
    id            INTEGER PRIMARY KEY,
    term          TEXT NOT NULL,
    area          TEXT NOT NULL,          -- area name from config (e.g. 'Utrecht')
    cell          TEXT NOT NULL,          -- readable cell label, e.g. 'Utrecht r2c3 NE'
    lat           REAL NOT NULL,
    lng           REAL NOT NULL,
    zoom          INTEGER NOT NULL,
    cell_km       REAL NOT NULL,
    depth         INTEGER NOT NULL DEFAULT 0,
    parent_id     INTEGER REFERENCES search(id),
    status        TEXT NOT NULL DEFAULT 'planned',   -- planned | ok | empty | error | blocked | skipped
    attempts      INTEGER NOT NULL DEFAULT 0,
    results       INTEGER,
    end_reached   INTEGER,
    full          INTEGER,
    in_cell       INTEGER,
    new_places    INTEGER,
    started_at    TEXT,
    done_at       TEXT,
    UNIQUE (term, lat, lng, zoom)
);

CREATE TABLE IF NOT EXISTS place (
    cid           TEXT PRIMARY KEY,       -- stable Google Maps id of the listing
    place_id      TEXT,
    name          TEXT,
    category      TEXT,
    lat           REAL,
    lng           REAL,
    address       TEXT,                   -- street part as shown on the list card (business address)
    website       TEXT,
    domain        TEXT,
    phone         TEXT,                   -- normalised business phone (for de-duplication)
    rating        REAL,
    reviews       INTEGER,
    sponsored     INTEGER DEFAULT 0,
    area          TEXT,                   -- area of the first search that found it
    gate          TEXT,                   -- pass | category_out | outside_area
    company_id    INTEGER REFERENCES company(id),
    first_seen    TEXT,
    last_seen     TEXT
);

CREATE TABLE IF NOT EXISTS hit (
    search_id     INTEGER NOT NULL REFERENCES search(id),
    cid           TEXT NOT NULL,
    rank          INTEGER,
    PRIMARY KEY (search_id, cid)
);

CREATE TABLE IF NOT EXISTS company (
    id            INTEGER PRIMARY KEY,
    key           TEXT NOT NULL UNIQUE,   -- own domain, or 'nosite:<cid>' for companies without a website
    name          TEXT,
    website       TEXT,
    domain        TEXT,
    phone         TEXT,
    category      TEXT,
    address       TEXT,
    area          TEXT,
    lat           REAL,
    lng           REAL,
    rating        REAL,
    reviews       INTEGER,
    duplicate_of  INTEGER REFERENCES company(id),
    created_at    TEXT
);

CREATE TABLE IF NOT EXISTS visit (
    company_id    INTEGER PRIMARY KEY REFERENCES company(id),
    visited_at    TEXT NOT NULL,
    ok            INTEGER NOT NULL,
    status        TEXT,                   -- ok | no_website | unreachable | parked | too_little_text
    final_url     TEXT,
    signals       TEXT,                   -- JSON
    pages         TEXT                    -- JSON [{kind, url, title, headings, text}] (emails removed)
);

CREATE TABLE IF NOT EXISTS label (
    company_id    INTEGER NOT NULL REFERENCES company(id),
    stage         TEXT NOT NULL,          -- sieve | deep
    fit           TEXT NOT NULL,          -- sieve: pass | drop ; deep: yes | partly | no
    reason        TEXT,
    evidence      TEXT,                   -- verbatim quote from the site or Maps
    evidence_url  TEXT,
    quote_found   INTEGER,                -- 1 if the quote was found in the stored page text
    opener        TEXT,                   -- one specific line to open the conversation with
    size          TEXT,
    score         INTEGER,                -- 0-100 from the nice-to-haves and buying signals it shows (deep only)
    hits          TEXT,                   -- JSON list of criteria ids it shows (N1, S2, ...)
    checks        TEXT,                   -- JSON {fails, unclear, breakers}: must-haves and deal-breakers named
    labeled_at    TEXT NOT NULL,
    PRIMARY KEY (company_id, stage)
);

CREATE TABLE IF NOT EXISTS briefing (
    company_id    INTEGER PRIMARY KEY REFERENCES company(id),
    data          TEXT NOT NULL,          -- JSON as written by the briefer
    markdown      TEXT NOT NULL,          -- the cold-call briefing, also saved as data/briefings/<id>-<name>.md
    path          TEXT,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS place_company ON place(company_id);
CREATE INDEX IF NOT EXISTS place_phone ON place(phone);
CREATE INDEX IF NOT EXISTS search_status ON search(status, depth);
"""


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def connect(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    have = {r[1] for r in conn.execute("PRAGMA table_info(label)")}
    for col, kind in (("score", "INTEGER"), ("hits", "TEXT"), ("checks", "TEXT")):
        if col not in have:                     # databases made before scoring existed
            conn.execute(f"ALTER TABLE label ADD COLUMN {col} {kind}")
    conn.commit()
    return conn


def live_companies_sql(alias="c"):
    """Companies that are not merged into another one."""
    return f"{alias}.duplicate_of IS NULL"
