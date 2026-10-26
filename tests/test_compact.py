"""Compact batches: menus out, keyword sentences in, everything still literal page text."""

import json
import sqlite3

from leadnote import db, qualify
from leadnote.compact import digest, keywords, sentences

MENU = ["Home", "Diensten", "Over ons", "Contact", "Werken bij"]
TEXT = ("Home Diensten Over ons Contact Werken bij Wij ontzorgen MKB-bedrijven met managed IT en een eigen "
        "servicedesk. Ons team van 14 collega's werkt vanuit Utrecht. Koffie staat altijd klaar voor iedereen hier. "
        "Wij leveren ook backup en Microsoft 365 beheer aan zorginstellingen.")


def page(kind, text=TEXT):
    return {"kind": kind, "url": f"https://firm.nl/{kind}", "title": kind, "menu": MENU, "headings": [], "text": text}


def test_sentences_and_menu_strip():
    d = digest([page("home")], ["backup", "servicedesk"], budget=400, lead_chars=60)
    kept = d[0][1]
    assert kept[0].startswith("Wij ontzorgen MKB-bedrijven")          # navigation cut off
    assert any("backup" in s for s in kept)
    assert all(s in TEXT for s in kept)                                # literal page text
    assert len(sentences("Een. Twee!  Drie")) == 3


def test_repeated_boilerplate_only_once():
    d = digest([page("home"), page("about")], ["backup"], budget=2000)
    allkept = [s for _, ss in d for s in ss]
    assert len(allkept) == len(set(allkept))


def test_keywords_from_niche_and_criteria(tmp_path):
    crit = tmp_path / "criteria.md"
    crit.write_text("Managed services for offices, backup and continuity.", encoding="utf-8")
    kws = keywords({"keywords": ["servicedesk", "Microsoft 365"], "search_terms": ["IT-bedrijf"]}, str(crit))
    assert "service" in kws and "backup" in kws and "the" not in kws


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    for i, status in [(1, "ok"), (2, "parked"), (3, "unreachable")]:
        conn.execute("INSERT INTO company (id, key, name, category, website, domain) VALUES (?,?,?,?,?,?)",
                     (i, f"firm{i}.nl", f"Firm {i}", "IT-bedrijf", f"https://firm{i}.nl", f"firm{i}.nl"))
        conn.execute("INSERT INTO visit (company_id, visited_at, ok, status, signals, pages) VALUES (?,?,?,?,?,?)",
                     (i, "now", int(status == "ok"), status, "{}", json.dumps([page("home")] if status == "ok" else [])))
    return conn


def test_prefilter_and_compact_import(tmp_path):
    conn = _conn()
    left, auto = qualify.prefilter(conn, {}, conn.execute("SELECT * FROM company").fetchall())
    assert [c["id"] for c in left] == [1] and auto == {"pass": 1, "drop": 1}
    f = tmp_path / "batch-001.labels.json"
    f.write_text(json.dumps({"stage": "sieve", "labels": [[1, "drop", "not it"]]}), encoding="utf-8")
    ok, problems = qualify.import_labels(conn, str(f), log=lambda *_: None)
    assert ok == 1 and not problems
    assert conn.execute("SELECT fit FROM label WHERE company_id = 1").fetchone()["fit"] == "drop"
