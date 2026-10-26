#!/usr/bin/env python3
"""LEADNOTE: the Death Note for sales. Every company on the map; a briefing for the ones worth calling.

    python run.py plan                 preview the grid: areas, cells, searches, rough time (does not touch Google)
    python run.py find [--max N]       search Google Maps cell by cell; stop any time, run again to continue
    python run.py visit [--limit N]    read each company's own website
    python run.py status               the funnel so far
    python run.py export [--fit yes,partly] [--out prospects.csv]
    python run.py criteria-check       is config/criteria.md complete? (sections, numbered items, weights)
    python run.py lookalike URL...     read a few best clients' sites for /leadnote-setup (nothing stored)
    python run.py calibrate-prep [--n 10] [--recheck IDS]   a calibration batch for /leadnote-calibrate
    python run.py calibrate-show FILE  one line per company: verdict, score, reason
    python run.py learn "rule" ...     add rules to 'Learned from calibration' in criteria.md
    python run.py qualify-prep --stage sieve|deep [--again]    batches for /leadnote-qualify
    python run.py brief-prep [--fit yes]             batches for /leadnote-brief
    python run.py import-labels FILE...              store the labels or briefings Claude wrote
    python run.py json                 everything the local page shows (used by npm start)

Options for every command: --config DIR, --data DIR (or LEADNOTE_CONFIG / LEADNOTE_DATA).
"""

import argparse
import json
import math
import os
import sys

from leadnote import config, criteria, db, report


def main(argv=None):
    ap = argparse.ArgumentParser(prog="run.py", description="LEADNOTE: find and qualify B2B prospects from Google Maps.")
    ap.add_argument("--config", help="folder with niche.json and criteria.md (default: ./config)")
    ap.add_argument("--data", help="folder for the database and work files (default: ./data)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan", help="preview the grid without searching")
    f = sub.add_parser("find", help="search Google Maps")
    f.add_argument("--max", type=int, help="stop after this many searches (continue later)")
    f.add_argument("--show-browser", action="store_true", help="show the browser window")
    v = sub.add_parser("visit", help="read the companies' own websites")
    v.add_argument("--limit", type=int)
    v.add_argument("--again", action="store_true", help="also re-read sites that were visited before")
    v.add_argument("--no-browser", action="store_true", help="do not retry JavaScript-only sites in a browser")
    sub.add_parser("status", help="the funnel so far")
    e = sub.add_parser("export", help="CSV for calling, LinkedIn or your CRM")
    e.add_argument("--fit", default="yes,partly", help="comma list of yes, partly, no, unlabeled, or 'all'")
    e.add_argument("--out", help="file to write (default: data/prospects.csv); '-' for stdout")
    q = sub.add_parser("qualify-prep", help="write batches for /leadnote-qualify")
    q.add_argument("--stage", choices=["sieve", "deep"], required=True)
    q.add_argument("--batch", type=int, help="companies per batch (sieve 40, deep 8)")
    q.add_argument("--limit", type=int, help="at most this many companies")
    q.add_argument("--again", action="store_true", help="sieve: forget all labels first and judge everything again")
    sub.add_parser("criteria-check", help="check config/criteria.md")
    lk = sub.add_parser("lookalike", help="read best clients' websites (nothing stored)")
    lk.add_argument("urls", nargs="+")
    cp = sub.add_parser("calibrate-prep", help="a calibration batch of about 10 companies")
    cp.add_argument("--n", type=int, default=10)
    cp.add_argument("--recheck", default="", help="comma list of company ids to judge again (the ones you corrected)")
    cp.add_argument("--fresh", action="store_true", help="forget which companies earlier rounds used")
    cs = sub.add_parser("calibrate-show", help="show a calibration round, one line per company")
    cs.add_argument("file")
    ln = sub.add_parser("learn", help="add rules to 'Learned from calibration' in criteria.md")
    ln.add_argument("rules", nargs="+")
    ln.add_argument("--note", help="e.g. 'round 1'")
    b = sub.add_parser("brief-prep", help="write batches for /leadnote-brief (fit=yes by default)")
    b.add_argument("--fit", default="yes", help="comma list: yes, partly")
    b.add_argument("--limit", type=int, help="at most this many (default: max_brief in niche.json, 25)")
    b.add_argument("--again", action="store_true", help="also companies that already have a briefing")
    i = sub.add_parser("import-labels", help="store labels or briefings written by Claude")
    i.add_argument("files", nargs="+")
    sub.add_parser("json", help="data for the local page")
    a = ap.parse_args(argv)

    paths = config.Paths(a.config, a.data)

    if a.cmd == "criteria-check":
        if not os.path.exists(paths.criteria):
            raise SystemExit(f"No {paths.criteria} yet. Run /leadnote-setup.")
        c = criteria.load(paths.criteria)
        kinds = {}
        for it in c["items"]:
            kinds[it["kind"]] = kinds.get(it["kind"], 0) + 1
        print(f"{c['title'] or '(no title)'}\nsections: {', '.join(c['order']) or 'none'}\n"
              f"items: {kinds.get('M', 0)} must-haves, {kinds.get('N', 0)} nice-to-haves, "
              f"{kinds.get('D', 0)} deal-breakers, {kinds.get('S', 0)} buying signals, {kinds.get('L', 0)} learned")
        ps = criteria.problems(c)
        print("ok" if not ps else "problems:\n" + "\n".join(f"- {p}" for p in ps))
        sys.exit(1 if ps else 0)

    if a.cmd == "learn":
        if not os.path.exists(paths.criteria):
            raise SystemExit(f"No {paths.criteria} yet. Run /leadnote-setup.")
        ids = criteria.add_learned(paths.criteria, a.rules, note=a.note)
        print(f"added {', '.join(ids)} to 'Learned from calibration' in {paths.criteria}")
        return

    if a.cmd == "lookalike":
        from leadnote import lookalike
        from leadnote.compact import keywords
        kws = []
        if os.path.exists(paths.niche):
            with open(paths.niche, encoding="utf-8") as fh:
                kws = keywords(json.load(fh), paths.criteria)
        for u in a.urls:
            print(lookalike.describe(u, kws) + "\n")
        return

    if a.cmd == "json":
        if not os.path.exists(paths.db):
            print(json.dumps({"funnel": None, "rows": [], "niche": None}))
            return
        conn = db.connect(paths.db)
        niche = None
        if os.path.exists(paths.niche):
            with open(paths.niche, encoding="utf-8") as fh:
                niche = json.load(fh)
        print(json.dumps({"funnel": report.funnel(conn), "rows": report.rows(conn, criteria.load(paths.criteria)),
                          "niche": {k: niche.get(k) for k in ("name", "country", "areas", "search_terms")}
                          if niche else None}, ensure_ascii=False))
        return

    if a.cmd == "status":
        if not os.path.exists(paths.db):
            print("No data yet. Run: python run.py find")
            return
        print(report.status_text(report.funnel(db.connect(paths.db))))
        return

    if a.cmd == "export":
        conn = db.connect(paths.db)
        fits = None if a.fit == "all" else set(x.strip() for x in a.fit.split(","))
        rs = report.rows(conn, criteria.load(paths.criteria))
        text = report.to_csv(rs, fits)
        n = sum(1 for r in rs if not fits or (r["fit"] or "unlabeled") in fits)
        if a.out == "-":
            sys.stdout.write(text)
            return
        out = a.out or os.path.join(paths.data, "prospects.csv")
        with open(out, "w", encoding="utf-8-sig", newline="") as fh:
            fh.write(text)
        print(f"{n} companies -> {out}")
        return

    if a.cmd == "import-labels":
        from leadnote import brief, qualify
        conn = db.connect(paths.db)
        total = 0
        for path in a.files:
            if path.endswith(".briefs.json"):
                n, _ = brief.import_briefs(conn, paths, path)
            else:
                n, _ = qualify.import_labels(conn, path, crit=criteria.load(paths.criteria))
            total += n
        print(f"{total} stored. " + report.status_text(report.funnel(conn)).splitlines()[-1])
        return

    niche = config.load_niche(paths)

    if a.cmd == "plan":
        from leadnote import area, maps
        pace = niche.get("pace") or {}
        block, rest = int(pace.get("block", 12)), float(pace.get("rest_minutes", 20))
        total = 0
        for ar in maps.load_areas(niche, paths):
            setting = (niche.get("grid") or {}).get("cell_km", "auto")
            km = area.auto_cell_km(ar) if setting in (None, "auto") else float(setting)
            cells = area.grid(ar, km)
            n = len(cells) * len(niche["search_terms"])
            total += n
            print(f"{ar['query']}: {ar.get('display_name')}\n  {len(cells)} cells of {km} km x "
                  f"{len(niche['search_terms'])} terms = {n} searches (zoom {area.zoom_for(km, cells[0]['lat'])})")
        minutes = total * 25 / 60 + math.floor(total / block) * rest
        print(f"\nbase grid: {total} searches. Busy cells split into four, so expect more in cities.\n"
              f"rough time at {block} searches then {rest:.0f} min rest: {minutes / 60:.1f} hours for the base grid.\n"
              f"Stop with Ctrl+C any time; 'find' continues where it left off.")
        return

    conn = db.connect(paths.db)
    if a.cmd == "find":
        from leadnote import maps
        try:
            maps.find(conn, niche, paths, max_searches=a.max, visible=a.show_browser)
        except KeyboardInterrupt:
            print("\nstopped. Everything so far is saved; run find again to continue.")
    elif a.cmd == "visit":
        from leadnote import visit
        visit.visit_companies(conn, niche, limit=a.limit, again=a.again, use_browser=not a.no_browser)
    elif a.cmd == "qualify-prep":
        from leadnote import qualify
        s = qualify.prepare(conn, paths, niche, a.stage, a.batch, a.limit, again=a.again)
        print(json.dumps(s, indent=1))
    elif a.cmd == "calibrate-prep":
        from leadnote import calibrate
        ids = [int(x) for x in a.recheck.replace(" ", "").split(",") if x]
        print(json.dumps(calibrate.prepare(conn, paths, niche, n=a.n, recheck=ids, fresh=a.fresh), indent=1))
    elif a.cmd == "calibrate-show":
        from leadnote import calibrate
        print("\n".join(calibrate.show(conn, paths, a.file)))
    elif a.cmd == "brief-prep":
        from leadnote import brief
        s = brief.prepare(conn, paths, niche, tuple(x.strip() for x in a.fit.split(",")), a.limit, again=a.again)
        print(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()
