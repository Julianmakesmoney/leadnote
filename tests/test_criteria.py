"""criteria.md: the fixed outline, numbered items, hard rules, the score, and learned rules."""

import json
import os

from goodleads import calibrate, config, criteria, db, qualify, report

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "criteria.md")

SMALL = """# Criteria: test

## Offer
Backup for IT firms.

## Ideal customer
IT firms with 5 to 50 people.

## Must-haves
- M1: Runs IT for businesses on a contract.
- M2: Business clients.

## Nice-to-haves
- N1 (weight 3): Mentions backup.
- N2: Founded before 2015.

## Deal-breakers
- D1: Consumer repair shop.

## Buying signals
- S1 (weight 2): Hiring.

## Who to ask for
The owner.

## Learned from calibration
none yet
"""


def test_example_is_complete():
    c = criteria.load(EXAMPLE)
    assert criteria.problems(c) == []
    assert c["order"] == criteria.SECTIONS
    kinds = {it["kind"] for it in c["items"]}
    assert {"M", "N", "D", "S"} <= kinds
    assert all(1 <= w <= 3 for w in criteria.weights(c).values())


def test_items_ids_and_weights():
    c = criteria.parse(SMALL)
    ids = {it["id"]: it for it in c["items"]}
    assert ids["N1"]["weight"] == 3 and ids["N2"]["weight"] == 1      # no weight given: 1
    assert ids["M1"]["weight"] is None and ids["M1"]["section"] == "Must-haves"
    assert ids["S1"]["text"] == "Hiring."
    assert criteria.weights(c) == {"N1": 3, "N2": 1, "S1": 2}


def test_problems_found():
    c = criteria.parse("# x\n\n## Offer\nsomething\n\n## Must-haves\nno numbers here\n\n## Nice-to-haves\n"
                       "- N1 (weight 5): too heavy\n- N1: twice\n- D1: wrong place\n")
    ps = "\n".join(criteria.problems(c))
    assert "'Ideal customer' is missing" in ps
    assert "'Deal-breakers' is missing" in ps
    assert "no numbered items like '- M1" in ps
    assert "N1: weight must be 1, 2 or 3" in ps
    assert "id N1 is used twice" in ps
    assert "D1 sits under 'Nice-to-haves'" in ps
    assert criteria.problems(criteria.parse("just text")) != []


def test_old_style_file_is_passed_whole():
    old = "# Criteria\n\n## What I sell\nX\n\n## Fit: yes\nY\n"
    assert criteria.for_stage(old, "sieve") == old.strip()


def test_stage_sections_keep_it_short():
    sieve = criteria.for_stage(SMALL, "sieve")
    deep = criteria.for_stage(SMALL, "deep")
    brief = criteria.for_stage(SMALL, "brief")
    assert "## Must-haves" in sieve and "## Deal-breakers" in sieve
    assert "## Nice-to-haves" not in sieve and "## Buying signals" not in sieve
    assert "## Nice-to-haves" in deep and "## Who to ask for" not in deep
    assert "## Who to ask for" in brief
    assert len(sieve) < len(deep) < len(brief)


def test_enforce_hard_rules_and_score():
    c = criteria.parse(SMALL)                                           # weights N1 3, N2 1, S1 2: total 6
    assert criteria.enforce({"fit": "yes", "hits": ["N1", "S1"]}, c)[:2] == ("yes", 83)
    fit, score, checks, notes = criteria.enforce({"fit": "yes", "breakers": ["D1"], "hits": ["N1"]}, c)
    assert (fit, score, checks) == ("no", 0, {"breakers": ["D1"]}) and "deal-breaker" in notes[0]
    assert criteria.enforce({"fit": "partly", "fails": "M2"}, c)[0] == "no"
    fit, score, _, _ = criteria.enforce({"fit": "yes", "unclear": ["M1"], "hits": "N2, S1"}, c)
    assert (fit, score) == ("partly", 50)
    fit, _, _, notes = criteria.enforce({"fit": "yes", "hits": ["N9"]}, c)
    assert fit == "yes" and "unknown id N9" in notes[0]
    assert criteria.enforce({"fit": "yes"}, criteria.parse(""))[:2] == ("yes", None)    # old style: no score


def test_add_learned(tmp_path):
    p = tmp_path / "criteria.md"
    p.write_text(SMALL, encoding="utf-8")
    assert criteria.add_learned(str(p), ["Hosting-only firms are a no.", "  "], note="round 1") == ["L1"]
    assert criteria.add_learned(str(p), ["Size does not matter."]) == ["L2"]
    text = p.read_text(encoding="utf-8")
    assert "none yet" not in text
    assert "- L1: Hosting-only firms are a no. (round 1)\n- L2: Size does not matter.\n" in text
    assert criteria.problems(criteria.parse(text)) == []
    p.write_text(SMALL.replace("## Learned from calibration\nnone yet\n", ""), encoding="utf-8")
    assert criteria.add_learned(str(p), ["New rule."]) == ["L1"]
    assert p.read_text(encoding="utf-8").rstrip().endswith("## Learned from calibration\n- L1: New rule.")


def _setup(tmp_path, n=12):
    cfg, data = tmp_path / "config", tmp_path / "data"
    cfg.mkdir()
    (cfg / "criteria.md").write_text(SMALL, encoding="utf-8")
    paths = config.Paths(str(cfg), str(data))
    conn = db.connect(paths.db)
    for i in range(1, n + 1):
        text = ("Wij doen beheer en backup voor bedrijven met een servicedesk. " * (i % 4) +
                "Wij zijn een bedrijf in Utrecht met een mooie website en veel plezier.")
        pages = [{"kind": "home", "url": f"https://f{i}.nl", "title": f"Firm {i}", "headings": [], "menu": [],
                  "text": text}]
        conn.execute("INSERT INTO company (id, key, name, domain, website) VALUES (?,?,?,?,?)",
                     (i, f"f{i}.nl", f"Firm {i}", f"f{i}.nl", f"https://f{i}.nl"))
        conn.execute("INSERT INTO visit (company_id, visited_at, ok, status, signals, pages) VALUES (?,?,?,?,?,?)",
                     (i, db.now(), 1, "ok", "{}", json.dumps(pages)))
    conn.commit()
    return conn, paths


def test_import_applies_rules_and_ranks(tmp_path):
    conn, paths = _setup(tmp_path, 3)
    lab = tmp_path / "deep.labels.json"
    lab.write_text(json.dumps({"stage": "deep", "labels": [
        {"id": 1, "fit": "yes", "hits": ["N2"], "reason": "r", "evidence": "Firm 1", "opener": "o"},
        {"id": 2, "fit": "yes", "hits": ["N1", "S1"], "reason": "r", "evidence": "Firm 2", "opener": "o"},
        {"id": 3, "fit": "yes", "breakers": ["D1"], "reason": "r", "evidence": "Firm 3", "opener": "o"}]}))
    n, notes = qualify.import_labels(conn, str(lab), log=lambda *_: None, crit=criteria.load(paths.criteria))
    assert n == 3 and any("deal-breaker D1" in x for x in notes)
    rs = report.rows(conn, criteria.load(paths.criteria))
    assert [(r["id"], r["fit"], r["score"], r["rank"]) for r in rs] == [(2, "yes", 83, 1), (1, "yes", 17, 2),
                                                                        (3, "no", 0, None)]
    assert rs[0]["matched"] == ["N1 Mentions backup.", "S1 Hiring."]
    assert rs[2]["opener"] is None
    head = report.to_csv(rs).splitlines()[0]
    assert head.startswith("rank,fit,score,name") and "matched" in head


def test_old_database_gets_new_columns(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE label (company_id INTEGER NOT NULL, stage TEXT NOT NULL, fit TEXT NOT NULL, reason TEXT,"
              " evidence TEXT, evidence_url TEXT, quote_found INTEGER, opener TEXT, size TEXT,"
              " labeled_at TEXT NOT NULL, PRIMARY KEY (company_id, stage))")
    c.commit()
    c.close()
    conn = db.connect(str(path))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(label)")}
    assert {"score", "hits", "checks"} <= cols


def test_calibration_pick_mix_and_rounds(tmp_path):
    conn, paths = _setup(tmp_path, 12)
    niche = {"keywords": ["beheer", "backup", "servicedesk"], "search_terms": []}
    s1 = calibrate.prepare(conn, paths, niche, n=6)
    assert s1["round"] == 1 and s1["companies"] == 6 and len(set(s1["ids"])) == 6
    text = open(s1["file"], encoding="utf-8").read()
    assert '"stage": "calibrate"' in text and "## Must-haves" in text and "## Who to ask for" not in text
    b = calibrate.buckets(conn, ["beheer", "backup", "servicedesk"])
    assert b["yes"] and b["no"]                                        # keyword-rich and keyword-poor both there
    s2 = calibrate.prepare(conn, paths, niche, n=6, recheck=[s1["ids"][0]])
    assert s1["ids"][0] in s2["ids"]
    assert not (set(s2["ids"]) - {s1["ids"][0]}) & set(s1["ids"])       # otherwise new companies
    lab = tmp_path / "round.labels.json"
    lab.write_text(json.dumps({"stage": "calibrate", "labels": [
        {"id": s1["ids"][0], "fit": "yes", "hits": ["N1"], "reason": "does backup"},
        {"id": s1["ids"][1], "fit": "yes", "breakers": ["D1"], "reason": "repair shop"}]}))
    lines = calibrate.show(conn, paths, str(lab))
    assert "| YES 50 | does backup" in lines[0]
    assert "| NO | repair shop [D1: Consumer repair shop.]" in lines[1]
    assert conn.execute("SELECT COUNT(*) FROM label").fetchone()[0] == 0   # calibration stores no labels


def test_lookalike_reads_a_site_without_storing():
    from goodleads import lookalike
    html = ("<html><head><title>Voorbeeld IT</title></head><body><nav><a href='/contact'>Contact</a></nav>"
            "<h1>Uw IT, ontzorgd</h1><p>Wij beheren de IT van 40 mkb-bedrijven met onze eigen servicedesk. "
            "Ons team van 14 collega's werkt sinds 2009 vanuit Utrecht voor zorg en onderwijs.</p></body></html>")
    out = lookalike.describe("voorbeeld-it.nl", ["servicedesk", "zorg"], fetch=lambda u: (html, u))
    assert out.startswith("### https://voorbeeld-it.nl (ok")
    assert "title: Voorbeeld IT" in out and "Uw IT, ontzorgd" in out
    assert "servicedesk" in out
    gone = lookalike.describe("https://down.example", fetch=lambda u: (None, u))
    assert "could not read this site" in gone
