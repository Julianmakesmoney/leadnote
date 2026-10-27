"""The search grid: cells over an area, splitting, zoom."""

from goodleads import area
from goodleads.maps import FULL_FROM, should_split

# A square of about 22 x 22 km around 52.09 N, 5.12 E, with a triangular outline in its lower-left half.
BOX = {"query": "Test", "name": "Test", "bbox": [52.0, 52.2, 5.0, 5.32], "polygons": []}
TRIANGLE = dict(BOX, polygons=[[[(5.0, 52.0), (5.32, 52.0), (5.0, 52.2), (5.0, 52.0)]]])


def test_auto_cell_size_city_and_country():
    assert 3 <= area.auto_cell_km(BOX) <= 10
    country = {"bbox": [49.5, 51.5, 2.5, 6.4]}
    assert area.auto_cell_km(country) == 20.0
    tiny = {"bbox": [51.05, 51.06, 3.72, 3.73]}
    assert area.auto_cell_km(tiny) == 3.0


def test_grid_covers_box():
    km = area.auto_cell_km(BOX)
    cells = area.grid(BOX, km)
    assert len(cells) >= 9
    lats = [c["lat"] for c in cells]
    lngs = [c["lng"] for c in cells]
    assert min(lats) < 52.05 and max(lats) > 52.15
    assert min(lngs) < 5.07 and max(lngs) > 5.25


def test_grid_skips_cells_outside_the_outline():
    km = area.auto_cell_km(BOX)
    full = area.grid(BOX, km)
    tri = area.grid(TRIANGLE, km)
    assert 0 < len(tri) < len(full)
    # the top-right corner is outside the triangle
    assert not any(c["lat"] > 52.17 and c["lng"] > 5.28 for c in tri)


def test_tiny_area_gets_one_cell():
    tiny = {"query": "T", "name": "T", "bbox": [51.05, 51.051, 3.72, 3.721], "polygons": []}
    cells = area.grid(tiny, 3.0)
    assert len(cells) == 1


def test_contains_with_hole():
    ring = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
    hole = [(4, 4), (6, 4), (6, 6), (4, 6), (4, 4)]
    a = {"bbox": [0, 10, 0, 10], "polygons": [[ring, hole]]}
    assert area.contains(a, 2, 2)
    assert not area.contains(a, 5, 5)
    assert not area.contains(a, 11, 5)
    assert not area.contains(a, None, None)


def test_children_are_four_quarters_one_size_smaller():
    kids = area.children(52.1, 5.1, 8.0)
    assert len(kids) == 4
    assert all(k[3] == 4.0 for k in kids)
    for _, lat, lng, km in kids:
        assert area.in_cell(lat, lng, 52.1, 5.1, 8.0)


def test_zoom_grows_as_cells_shrink():
    z20 = area.zoom_for(20, 52)
    z5 = area.zoom_for(5, 52)
    assert z20 == 12
    assert z5 == z20 + 2


def test_split_only_full_and_busy_cells():
    assert should_split(5, 0, FULL_FROM + 20, 80, 2.0, 10, 3)
    assert not should_split(5, 0, 60, 60, 2.0, 10, 3)               # not full
    assert not should_split(5, 3, FULL_FROM + 20, 80, 2.0, 10, 3)   # max depth
    assert not should_split(5, 0, FULL_FROM + 20, 5, 9.0, 10, 3)    # full of far-away results
    assert should_split(5, 0, 120, 30, 4.0, 10, 3)                  # last results still close by
    assert not should_split(5, 0, 120, 80, 2.0, 10, 3, new_places=3)  # full, but hardly anything new
    assert should_split(5, 0, 120, 80, 2.0, 10, 3, new_places=40)
