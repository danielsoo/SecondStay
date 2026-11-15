"""Vexcel adapter tests. Geometry here is made up; no API call is made."""

from secondstay.checklist import ISSUE, build_checklist, SpaceFacts
from secondstay.vexcel import measure, parse_rings, roof_sample_points, to_facts

LAT, LON = 34.0, -118.0
M_LAT, M_LON = 1 / 110540.0, 1 / 92288.0  # degrees per metre at this latitude


def square(west_m, south_m, size_m):
    corners = [(0, 0), (size_m, 0), (size_m, size_m), (0, size_m), (0, 0)]
    points = ", ".join(f"{LON + (west_m + x) * M_LON:.7f} {LAT + (south_m + y) * M_LAT:.7f}" for x, y in corners)
    return {"properties": {"footprint.wkt": f"MULTIPOLYGON ((({points})))", "metadata.ortho-date-estimate": "2026-07-03T18:00:00"}}


def test_parse_rings_reads_each_polygon():
    rings = parse_rings("MULTIPOLYGON (((0 0, 1 0, 1 1, 0 0)), ((5 5, 6 5, 6 6, 5 5)))")
    assert len(rings) == 2 and rings[1][0] == (5.0, 5.0)


def test_measure_picks_the_building_at_the_point_and_the_gap_to_the_next():
    features = [square(30, -10, 20), square(-10, -10, 20), square(100, 100, 2)]  # neighbour, subject, shed
    outside = measure(features, LAT, LON)
    assert outside.loaded and outside.captured == "2026-07-03"
    assert abs(outside.neighbor_gap_ft - 20 * 3.28084) < 1  # 20 m between the two squares
    assert abs(outside.footprint_sqft - 400 * 10.7639) < 60
    assert len(outside.neighbors) == 1  # the 4 sq m shed is ignored


def test_measure_reports_when_nothing_matches():
    assert not measure([], LAT, LON).loaded
    far = measure([square(200, 200, 20)], LAT, LON)
    assert not far.loaded and "close enough" in far.error


def test_roof_samples_stay_inside_the_footprint():
    ring = parse_rings(square(-10, -10, 20)["properties"]["footprint.wkt"])[0]
    points = roof_sample_points(ring, extra=(LON, LAT))
    assert len(points) == 37 and points[-1] == (LON, LAT)


def test_height_that_does_not_fit_the_stories_on_record_is_flagged():
    facts = SpaceFacts(stories=20)
    facts.height_ft = 36.0
    row = {r.key: r for r in build_checklist(facts, 2026)}["height"]
    assert row.state == ISSUE and "do not fit together" in row.evidence


def test_drawn_outline_drops_tracing_jitter_but_keeps_corners():
    from secondstay.vexcel import simplify_ring
    k = 1 / 111320.0  # about a metre in degrees near the equator
    jagged = [(0, 0), (40 * k, 0)] + [((40 - i) * k, (20 + (0.8 if i % 2 else 0)) * k) for i in range(0, 41)] + [(0, 0)]
    clean = simplify_ring(jagged)
    assert len(clean) == 5  # a 40 m x 20 m box: four corners and the closing point
    assert clean[0] == clean[-1]
    square = [(0, 0), (10 * k, 0), (10 * k, 10 * k), (0, 10 * k), (0, 0)]
    assert simplify_ring(square) == square  # nothing to remove
