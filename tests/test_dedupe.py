"""De-duplication: the same place in one list, the same website across listings, the same phone at the same spot."""

import json

from dragnet import db
from dragnet.maps import merge_twins, process_cards

AREA = {"query": "Test", "name": "Test", "bbox": [52.0, 52.2, 5.0, 5.3], "polygons": []}
NICHE = {"country": "nl", "language": "nl", "category_exclude": ["Restaurant"], "name_keywords": [],
         "keep_without_website": False}


def href(cid_hex, lat, lng):
    return f"https://www.google.com/maps/place/x/data=!4m7!3m6!1s0x47c6:{cid_hex}!8m2!3d{lat}!4d{lng}!16s"


def card(name, cid_hex, lat=52.1, lng=5.1, website=None, cat="IT-bedrijf", phone="030 111 2222", extra=""):
    return {"name": name, "href": href(cid_hex, lat, lng), "website": website,
            "text": f"{name}\n{name}\n4,5(10)\n{cat} · Straat 1\nGeopend · {phone}{extra}"}


def setup():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    conn.execute("INSERT INTO search (id, term, area, cell, lat, lng, zoom, cell_km) VALUES"
                 " (1,'it','Test','c',52.1,5.1,14,5), (2,'it bedrijf','Test','c',52.1,5.1,14,5)")
    return conn


def test_same_place_twice_in_one_list_counts_once():
    conn = setup()
    cards = [card("Ad IT", "0x1", website="https://www.google.com/aclk?x", extra="\nGesponsord"),
             card("Ad IT", "0x1", website="https://ad-it.nl/")]
    out = process_cards(conn, NICHE, [AREA], conn.execute("SELECT * FROM search WHERE id=1").fetchone(), cards)
    assert out["new_places"] == 1
    assert conn.execute("SELECT COUNT(*) FROM place").fetchone()[0] == 1
    assert conn.execute("SELECT website FROM place").fetchone()[0] == "https://ad-it.nl/"


def test_same_website_two_listings_is_one_company():
    conn = setup()
    row = conn.execute("SELECT * FROM search WHERE id=1").fetchone()
    process_cards(conn, NICHE, [AREA], row, [card("Firm Utrecht", "0x2", website="https://www.firm.nl/"),
                                              card("Firm Zeist", "0x3", lat=52.12, website="https://firm.nl/zeist",
                                                   phone="030 999 8888")])
    assert conn.execute("SELECT COUNT(*) FROM place").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM company").fetchone()[0] == 1


def test_found_again_in_another_search_is_not_new():
    conn = setup()
    c = [card("Firm", "0x4", website="https://firm4.nl/")]
    a = process_cards(conn, NICHE, [AREA], conn.execute("SELECT * FROM search WHERE id=1").fetchone(), c)
    b = process_cards(conn, NICHE, [AREA], conn.execute("SELECT * FROM search WHERE id=2").fetchone(), c)
    assert a["new_places"] == 1 and b["new_places"] == 0
    assert conn.execute("SELECT COUNT(*) FROM hit").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM company").fetchone()[0] == 1


def test_gate_outside_area_category_and_no_website():
    conn = setup()
    row = conn.execute("SELECT * FROM search WHERE id=1").fetchone()
    process_cards(conn, NICHE, [AREA], row, [
        card("Far IT", "0x5", lat=40.0, lng=-30.0, website="https://far.nl/"),
        card("Pizza", "0x6", website="https://pizza.nl/", cat="Restaurant"),
        card("No Site IT", "0x7"),
        card("Good IT", "0x8", website="https://good.nl/")])
    gates = dict(conn.execute("SELECT name, gate FROM place").fetchall())
    assert gates == {"Far IT": "outside_area", "Pizza": "category_out", "No Site IT": "no_website", "Good IT": "pass"}
    assert [r[0] for r in conn.execute("SELECT name FROM company")] == ["Good IT"]


def test_same_phone_same_spot_merges_two_websites():
    conn = setup()
    row = conn.execute("SELECT * FROM search WHERE id=1").fetchone()
    process_cards(conn, NICHE, [AREA], row, [
        card("Brand A", "0x9", website="https://brand-a.nl/", phone="030 555 0000"),
        card("Brand A Shop", "0xa", lat=52.1002, website="https://brand-a-shop.nl/", phone="030 555 0000"),
        card("Other", "0xb", lat=52.15, website="https://other.nl/", phone="030 555 0000")])  # 5 km away
    assert merge_twins(conn) == 1
    live = [r[0] for r in conn.execute("SELECT name FROM company WHERE duplicate_of IS NULL ORDER BY id")]
    assert live == ["Brand A", "Other"]
    assert merge_twins(conn) == 0          # running it again changes nothing
