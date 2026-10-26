"""Status, CSV export and the JSON the local page reads."""

import csv
import io
import json

FIT_ORDER = {"yes": 0, "partly": 1, "no": 2, None: 3}


def funnel(conn):
    s = conn.execute("SELECT SUM(status IN ('ok','empty')) AS done, COUNT(*) AS planned, COALESCE(SUM(CASE WHEN status = 'ok' THEN results END),0) AS res,"
                     " SUM((status IN ('planned','error','blocked') AND attempts < 3) OR (status = 'empty' AND attempts < 2)) AS left"
                     " FROM search").fetchone()
    places = conn.execute("SELECT COUNT(*) AS n, SUM(gate='pass') AS pass, SUM(gate='outside_area') AS outside,"
                          " SUM(gate='category_out') AS cat, SUM(gate='no_website') AS nosite FROM place").fetchone()
    companies = conn.execute("SELECT COUNT(*) FROM company WHERE duplicate_of IS NULL").fetchone()[0]
    visits = conn.execute("SELECT COUNT(*) AS n, SUM(ok) AS ok FROM visit v JOIN company c ON c.id = v.company_id"
                          " WHERE c.duplicate_of IS NULL").fetchone()
    lab = {r["k"]: r["n"] for r in conn.execute("SELECT stage || ':' || fit AS k, COUNT(*) AS n FROM label l"
                                                " JOIN company c ON c.id = l.company_id WHERE c.duplicate_of IS NULL"
                                                " GROUP BY 1")}
    return {"searches": s["done"] or 0, "searches_planned": s["planned"] or 0, "searches_left": s["left"] or 0,
            "results": s["res"], "unique": places["n"] or 0, "outside_area": places["outside"] or 0,
            "category_out": places["cat"] or 0, "no_website": places["nosite"] or 0, "companies": companies,
            "visited": visits["n"] or 0, "visited_ok": visits["ok"] or 0,
            "sieved": lab.get("sieve:pass", 0) + lab.get("sieve:drop", 0), "sieve_pass": lab.get("sieve:pass", 0),
            "fit_yes": lab.get("deep:yes", 0), "fit_partly": lab.get("deep:partly", 0), "fit_no": lab.get("deep:no", 0)}


def status_text(f):
    return "\n".join([
        f"searches     {f['searches']} done, {f['searches_left']} left in the queue",
        f"results      {f['results']} list entries read",
        f"unique       {f['unique']} places  (outside the area {f['outside_area']}, category out {f['category_out']},"
        f" no website {f['no_website']})",
        f"companies    {f['companies']} after de-duplication",
        f"visited      {f['visited']} websites ({f['visited_ok']} readable)",
        f"sieve        {f['sieved']} sieved, {f['sieve_pass']} passed",
        f"fit          {f['fit_yes']} yes, {f['fit_partly']} partly, {f['fit_no']} no",
    ])


def rows(conn):
    out = []
    for c in conn.execute("SELECT * FROM company WHERE duplicate_of IS NULL ORDER BY id"):
        v = conn.execute("SELECT status, signals FROM visit WHERE company_id = ?", (c["id"],)).fetchone()
        sig = json.loads(v["signals"] or "{}") if v else {}
        labels = {l["stage"]: dict(l) for l in conn.execute("SELECT * FROM label WHERE company_id = ?", (c["id"],))}
        deep, sieve = labels.get("deep"), labels.get("sieve")
        fit = deep["fit"] if deep else ("no" if sieve and sieve["fit"] == "drop" else None)
        jobs = sig.get("jobs") or {}
        staff = sig.get("staff") or {}
        out.append({
            "id": c["id"], "name": c["name"], "website": c["website"], "domain": c["domain"], "phone": c["phone"],
            "category": c["category"], "address": c["address"], "area": c["area"], "rating": c["rating"],
            "reviews": c["reviews"], "lat": c["lat"], "lng": c["lng"],
            "maps_url": f"https://www.google.com/maps/search/?api=1&query={c['lat']},{c['lng']}" if c["lat"] else None,
            "site_status": v["status"] if v else None,
            "staff": staff.get("value"), "staff_quote": staff.get("quote"),
            "founded": (sig.get("founded") or {}).get("value"),
            "jobs_page": jobs.get("page"), "job_titles": jobs.get("titles") or [],
            "contact_page": sig.get("contact_page"), "linkedin": sig.get("linkedin"), "title": sig.get("title"),
            "stage": "deep" if deep else ("sieve" if sieve else None),
            "fit": fit, "reason": (deep or sieve or {}).get("reason"),
            "evidence": (deep or {}).get("evidence"), "evidence_url": (deep or {}).get("evidence_url"),
            "quote_found": (deep or {}).get("quote_found"), "opener": (deep or {}).get("opener"),
            "size": (deep or {}).get("size"),
        })
    out.sort(key=lambda r: (FIT_ORDER.get(r["fit"], 3), (r["name"] or "").lower()))
    return out


CSV_FIELDS = ["fit", "name", "website", "phone", "area", "address", "category", "rating", "reviews", "size", "staff",
              "founded", "reason", "evidence", "evidence_url", "opener", "contact_page", "jobs_page", "linkedin",
              "maps_url"]


def to_csv(rs, fits=None):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS, extrasaction="ignore")
    w.writeheader()
    for r in rs:
        if fits and (r["fit"] or "unlabeled") not in fits:
            continue
        w.writerow(r)
    return buf.getvalue()
