"""Website signals and page parsing (made-up pages)."""

from leadnote.signals import founded, jobs, link_kind, redact, staff_count
from leadnote.visit import parse_page, pick_subpages


def page(kind, text, **kw):
    return dict({"kind": kind, "url": f"https://firm.nl/{kind}", "text": text, "headings": [], "links": []}, **kw)


def test_staff_count_languages_and_ranges():
    assert staff_count([page("about", "Wij zijn met 12 medewerkers actief.")])["value"] == 12
    assert staff_count([page("about", "A team of 25 engineers.")])["value"] == 25
    assert staff_count([page("home", "Plus de 40 collaborateurs.")])["value"] == 40
    assert staff_count([page("home", "Für kleine Firmen mit 1-49 Mitarbeiter.")]) is None
    assert staff_count([page("home", "Opgericht in 1998 met 3 medewerkers")])["value"] == 3


def test_founded():
    assert founded([page("about", "Opgericht in 1998 in Utrecht.")])["value"] == 1998
    assert founded([page("about", "Since 2005 we help offices.")])["value"] == 2005
    assert founded([page("home", "Al meer dan 20 jaar uw partner.")])["value"] == "~20 years"


def test_jobs_titles():
    p = page("jobs", "Werken bij ons", headings=["Servicedesk medewerker (32-40 uur)", "Over ons"],
             links=["Systeembeheerder m/v", "Contact"])
    j = jobs([p])
    assert j["titles"] == ["Servicedesk medewerker (32-40 uur)", "Systeembeheerder m/v"]


def test_link_kinds():
    assert link_kind("https://firm.nl/contact", "") == "contact"
    assert link_kind("https://firm.nl/werken-bij", "") == "jobs"
    assert link_kind("https://firm.nl/x", "Over ons") == "about"
    assert link_kind("https://firm.nl/diensten/beheer", "") == "services"
    assert link_kind("https://firm.nl/privacy-contact", "") is None
    assert link_kind("https://firm.nl/brochure.pdf", "Contact") is None


def test_emails_are_removed_and_subpages_picked():
    html = """<html lang="nl"><head><title>Firm</title></head><body><nav><a href="/diensten">Diensten</a>
    <a href="/contact">Contact</a><a href="/vacatures">Vacatures</a><a href="https://other.nl/contact">x</a></nav>
    <h1>Managed IT</h1><p>Mail ons op info@firm.nl of bel <a href="tel:+31301234567">030</a>.</p></body></html>"""
    p, extra = parse_page(html, "https://firm.nl/", "home")
    assert "info@firm.nl" not in p["text"] and "[email]" in p["text"]
    assert extra["phones"] == ["+31301234567"]
    kinds = dict(pick_subpages("https://firm.nl/", extra["links"], 6))
    assert kinds == {"contact": "https://firm.nl/contact", "services": "https://firm.nl/diensten",
                     "jobs": "https://firm.nl/vacatures"}
    assert redact("a.b@c.co.uk") == "[email]"
