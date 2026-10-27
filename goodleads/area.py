"""Areas and the search grid.

An area is any place OpenStreetMap knows: a city, a district, a province, a whole country. Nominatim gives its outline
(polygon) and bounding box; the grid covers the box with square cells and keeps the cells that touch the outline.
Free, no key. Nominatim's rule is at most one request per second with a real User-Agent, and answers are cached in
data/areas.json, so each area is looked up once.
"""

import json
import math
import os
import time

import requests

KM_PER_DEG_LAT = 111.32
NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "goodleads/1.0 (open-source prospect finder; https://github.com/)"
_last_call = [0.0]


def km_per_deg_lng(lat):
    return max(KM_PER_DEG_LAT * math.cos(math.radians(lat)), 1e-6)


def _nominatim(query, language="en"):
    wait = 1.1 - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    try:
        r = requests.get(NOMINATIM, timeout=30, headers={"User-Agent": USER_AGENT},
                         params={"q": query, "format": "jsonv2", "limit": 5, "polygon_geojson": 1,
                                 "polygon_threshold": 0.002, "accept-language": language})
        r.raise_for_status()
        return r.json()
    finally:
        _last_call[0] = time.time()


def _rings(geojson):
    """GeoJSON Polygon/MultiPolygon -> list of polygons, each a list of rings [(lng, lat), ...]."""
    if not geojson:
        return []
    t, c = geojson.get("type"), geojson.get("coordinates") or []
    if t == "Polygon":
        return [[[(p[0], p[1]) for p in ring] for ring in c]]
    if t == "MultiPolygon":
        return [[[(p[0], p[1]) for p in ring] for ring in poly] for poly in c]
    return []


def lookup(query, cache_path, language="en"):
    """Area dict {query, name, country_code, bbox: [south, north, west, east], polygons}. Cached."""
    cache = {}
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
    if query in cache:
        return cache[query]
    results = _nominatim(query, language)
    if not results:
        raise SystemExit(f"OpenStreetMap does not know the area '{query}'. Try a fuller name, e.g. "
                         "'Utrecht, Netherlands' or 'Ghent, Belgium'.")
    # Prefer an area with an outline (city, province, country) over a single point.
    best = next((r for r in results if (r.get("geojson") or {}).get("type") in ("Polygon", "MultiPolygon")), results[0])
    s, n, w, e = (float(x) for x in best["boundingbox"])
    area = {"query": query, "name": best.get("name") or query, "display_name": best.get("display_name"),
            "country_code": (best.get("address") or {}).get("country_code"), "bbox": [s, n, w, e],
            "polygons": _rings(best.get("geojson"))}
    cache[query] = area
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    tmp = cache_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    os.replace(tmp, cache_path)
    return area


def _in_ring(lng, lat, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def contains(area, lat, lng):
    """Is the point inside the area's outline (or its box, when there is no outline)?"""
    if lat is None or lng is None:
        return False
    s, n, w, e = area["bbox"]
    if not (s <= lat <= n and w <= lng <= e):
        return False
    if not area.get("polygons"):
        return True
    for poly in area["polygons"]:
        if poly and _in_ring(lng, lat, poly[0]) and not any(_in_ring(lng, lat, hole) for hole in poly[1:]):
            return True
    return False


def auto_cell_km(area):
    """Cell size for an area: a third of its longest side, between 3 and 20 km. Cities get small cells, countries
    20 km cells that split further where it is busy."""
    s, n, w, e = area["bbox"]
    mid = (s + n) / 2
    side = max((n - s) * KM_PER_DEG_LAT, (e - w) * km_per_deg_lng(mid))
    return round(min(max(side / 3, 3.0), 20.0), 1)


def zoom_for(cell_km, lat):
    """Google Maps zoom at which the visible map (~880 px next to the result list) spans about one cell."""
    metres_per_px = cell_km * 1000 / 880
    z = math.log2(156543.03 * math.cos(math.radians(lat)) / metres_per_px)
    return int(min(max(round(z), 8), 17))


def grid(area, cell_km):
    """Cells [{label, lat, lng, cell_km}] covering the area. A cell counts when its centre, a corner or a quarter
    point lies inside the outline; a tiny area always gets at least the cell around its centre."""
    s, n, w, e = area["bbox"]
    dlat = cell_km / KM_PER_DEG_LAT
    cells = []
    rows = max(1, math.ceil((n - s) / dlat))
    lat0 = (s + n) / 2 - (rows - 1) * dlat / 2
    for r in range(rows):
        lat = lat0 + r * dlat
        dlng = cell_km / km_per_deg_lng(lat)
        cols = max(1, math.ceil((e - w) / dlng))
        lng0 = (w + e) / 2 - (cols - 1) * dlng / 2
        for c in range(cols):
            lng = lng0 + c * dlng
            probes = [(0, 0)] + [(a, b) for a in (-0.5, 0.5) for b in (-0.5, 0.5)] + \
                     [(a, b) for a in (-0.25, 0.25) for b in (-0.25, 0.25)]
            if any(contains(area, lat + a * dlat, lng + b * dlng) for a, b in probes):
                cells.append({"label": f"{area['name']} r{r + 1}c{c + 1}", "lat": round(lat, 5),
                              "lng": round(lng, 5), "cell_km": cell_km})
    if not cells:
        cells.append({"label": f"{area['name']} centre", "lat": round((s + n) / 2, 5), "lng": round((w + e) / 2, 5),
                      "cell_km": cell_km})
    return cells


def children(lat, lng, cell_km):
    """The four quarter cells of a cell: (suffix, lat, lng, cell_km)."""
    q = cell_km / 4
    dlat, dlng = q / KM_PER_DEG_LAT, q / km_per_deg_lng(lat)
    return [(name, round(lat + a * dlat, 5), round(lng + b * dlng, 5), cell_km / 2)
            for name, a, b in (("NE", 1, 1), ("NW", 1, -1), ("SE", -1, 1), ("SW", -1, -1))]


def in_cell(lat, lng, c_lat, c_lng, cell_km):
    half = cell_km / 2
    return abs(lat - c_lat) * KM_PER_DEG_LAT <= half and abs(lng - c_lng) * km_per_deg_lng(c_lat) <= half
