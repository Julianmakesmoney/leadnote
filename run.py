#!/usr/bin/env python3
"""LEADNOTE: the Death Note for sales. Every company on the map; a briefing for the ones worth calling.

    python run.py plan                 preview the grid: areas, cells, searches, rough time (does not touch Google)
    python run.py find [--max N]       search Google Maps cell by cell; stop any time, run again to continue
    python run.py visit [--limit N]    read each company's own website
    python run.py status               the funnel so far
    python run.py export [--fit yes,partly] [--out prospects.csv]
    python run.py qualify-prep --stage sieve|deep    batches for /leadnote-qualify
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

from leadnote import config, db, report


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
    b = sub.add_parser("brief-prep", help="write batches for /leadnote-brief (fit=yes by default)")
    b.add_argument("--fit", default="yes", help="comma list: yes, partly")
    b.add_argument("--limit", type=int, help="at most this many (default: max_brief in niche.json, 25)")
    b.add_argument("--again", action="store_true", help="also companies that already have a briefing")
    i = sub.add_parser("import-labels", help="store labels or briefings written by Claude")
    i.add_argument("files", nargs="+")
    sub.add_parser("json", help="data for the local page")
    a = ap.parse_args(argv)

    paths = config.Paths(a.config, a.data)

    if a.cmd == "json":
        if not os.path.exists(paths.db):
            print(json.dumps({"funnel": None, "rows": [], "niche": None}))
            return
        conn = db.connect(paths.db)
        niche = None
        if os.path.exists(paths.niche):
            with open(paths.niche, encoding="utf-8") as fh:
                niche = json.load(fh)
        print(json.dumps({"funnel": report.funnel(conn), "rows": report.rows(conn),
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
        rs = report.rows(conn)
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
                n, _ = qualify.import_labels(conn, path)
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
        s = qualify.prepare(conn, paths, niche, a.stage, a.batch, a.limit)
        print(json.dumps(s, indent=1))
    elif a.cmd == "brief-prep":
        from leadnote import brief
        s = brief.prepare(conn, paths, niche, tuple(x.strip() for x in a.fit.split(",")), a.limit, again=a.again)
        print(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()
