"""Reading Google Maps list cards and links. Card texts follow the real layout; names and numbers are made up."""

from dragnet.maps import category_out, has_keyword, looks_like_rating, parse_card_text, parse_href, search_url
from dragnet.keys import domain_of, normalise_phone, real_website

HREF = ("https://www.google.com/maps/place/Example+IT/data=!4m7!3m6!1s0x47c6659d7f4ed723:0x78bfcf870294c262"
        "!8m2!3d52.0692675!4d5.0786642!16s%2Fg%2F11bbwpdhv4!19sChIJI9dOf51lxkcRYsKUAofPv3g?authuser=0&hl=nl")


def test_href_gives_cid_place_id_and_location():
    p = parse_href(HREF)
    assert p["cid"] == str(int("0x78bfcf870294c262", 16))
    assert p["place_id"] == "ChIJI9dOf51lxkcRYsKUAofPv3g"
    assert p["lat"] == 52.0692675 and p["lng"] == 5.0786642


def test_href_without_ids():
    assert parse_href("https://example.com") == {"cid": None, "place_id": None, "lat": None, "lng": None}
    assert parse_href(None)["cid"] is None


def test_dutch_card_with_empty_icon_piece():
    t = ("Example IT\nExample IT\n4,1(50)\nIT-consultancy ·  · Voorbeeldlaan 69\n"
         "Geopend ⋅ Sluit om 17:00 · 030 239 0000\n\nWebsite\n\nRoute")
    r = parse_card_text(t)
    assert r["category"] == "IT-consultancy"
    assert r["address"] == "Voorbeeldlaan 69"
    assert r["rating"] == 4.1 and r["reviews"] == 50
    assert r["phone_raw"] == "030 239 0000"
    assert r["sponsored"] is False


def test_english_card_with_thousands_in_reviews():
    t = ("Sample Accountants\nSample Accountants\n4.7(1,234)\nAccountant · 12 Main Street\n"
         "Open ⋅ Closes 5 PM · +32 9 123 45 67\nWebsite\nDirections")
    r = parse_card_text(t)
    assert r["category"] == "Accountant"
    assert r["address"] == "12 Main Street"
    assert r["reviews"] == 1234 and r["rating"] == 4.7
    assert r["phone_raw"] == "+32 9 123 45 67"


def test_no_reviews_and_no_phone():
    t = "Firm\nFirm\nGeen reviews\nManagement-consultant · Laan 58\nGeopend ⋅ Sluit om 17:00\n\nWebsite"
    r = parse_card_text(t)
    assert r["reviews"] == 0 and r["rating"] is None
    assert r["category"] == "Management-consultant"
    assert r["phone_raw"] is None


def test_rating_on_the_same_line_as_category():
    r = parse_card_text("Shop\n4,6(33) · Krantenwinkel · Dorp")
    assert r["category"] == "Krantenwinkel"
    assert r["rating"] is None or r["rating"] == 4.6


def test_rating_with_icon_character_is_not_a_category():
    assert looks_like_rating("4,6(33)")
    r = parse_card_text("Shop\n4,6(33)\nBoekhandel · Straat 1")
    assert r["category"] == "Boekhandel"


def test_opening_hours_line_is_never_the_category():
    r = parse_card_text("Name\nOuvert ⋅ Ferme à 18:00 · Rue 1\nComptable · Rue de la Paix 3")
    assert r["category"] == "Comptable"


def test_sponsored_card():
    r = parse_card_text("Gesponsord\nAd Firm\n4,0(10)\nIT-bedrijf · Straat 1")
    assert r["sponsored"] is True
    assert r["category"] == "IT-bedrijf"


def test_price_level_after_rating_is_skipped():
    r = parse_card_text("Cafe\n4,5(100) · €€\nRestaurant · Markt 1")
    assert r["category"] == "Restaurant"


def test_search_url_has_language_and_country():
    u = search_url("IT managed service provider", 52.09, 5.12, 14, "nl", "nl")
    assert u == "https://www.google.com/maps/search/IT+managed+service+provider/@52.09,5.12,14z?hl=nl&gl=nl"


def test_category_filter_whole_words_and_keyword_rescue():
    ex = ["Restaurant", "Hotel", "Kapper"]
    assert category_out("Restaurant", "Cafe X", ex, [])
    assert category_out("Hotels", "Y", ex, [])
    assert not category_out("Hotelapparatuur", "Z", ex, [])
    assert not category_out("Restaurant", "Bytes IT Restaurant", ex, ["bytes"])
    assert not category_out(None, "Unknown", ex, [])
    assert has_keyword("Hydraulics Service", ["hydraul"])
    assert not has_keyword("Max Promotion", ["motion"])


def test_domains_and_websites():
    assert domain_of("https://shop.firm.co.uk/x") == "firm.co.uk"
    assert domain_of("http://www.example.nl/") == "example.nl"
    assert domain_of("https://www.facebook.com/firm") == ""
    assert domain_of("https://firm.wixsite.com/home") == "firm.wixsite.com"
    assert real_website("https://www.google.com/aclk?sa=l") is None
    assert real_website("https://firm.nl") == "https://firm.nl"


def test_phone_normalisation():
    assert normalise_phone("030 239 0000", "nl") == "+31302390000"
    assert normalise_phone("+32 9 123 45 67", "nl") == "+3291234567"
    assert normalise_phone("09 123 45 67", "be") == "+3291234567"
    assert normalise_phone("0032 9 123 45 67", "be") == "+3291234567"
    assert normalise_phone("(415) 555-0100", "us") == "+14155550100"
    assert normalise_phone("12", "nl") is None
