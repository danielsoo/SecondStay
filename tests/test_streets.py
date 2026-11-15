"""Street tests. Geometry is made up; no request is made."""

from secondstay.panoramas import spread
from secondstay.streets import frontage, measure

LAT, LON = 34.0, -118.0
M_LAT, M_LON = 1 / 110540.0, 1 / 92288.0


def at(x_m, y_m):
    return (LON + x_m * M_LON, LAT + y_m * M_LAT)


def test_closest_public_street_is_the_frontage():
    footprint = [[at(-10, -10), at(10, -10), at(10, 10), at(-10, 10), at(-10, -10)]]
    roads = [
        {"name": "Service Alley", "kind": "service", "points": [at(-50, 12), at(50, 12)]},
        {"name": "Example Ave", "kind": "secondary", "points": [at(-50, -30), at(50, -30)]},
        {"name": "Far St", "kind": "residential", "points": [at(-50, 90), at(50, 90)]},
    ]
    found = measure(roads, footprint, LAT, LON)
    assert [s.name for s in found] == ["Service Alley", "Example Ave", "Far St"]
    front = frontage(found)
    assert front.name == "Example Ave" and abs(front.distance_ft - 20 * 3.28084) < 1
    assert frontage(measure(roads[:1], footprint, LAT, LON)) is None  # an alley is not frontage


def test_panoramas_are_picked_far_apart():
    points = [(0, 0, 0), (0.1, 0, 0), (10, 0, 0), (10.1, 0, 0), (5, 8, 0)]
    assert spread(points, 3) == [0, 3, 4]  # the far end, then the point off to the side
    assert spread(points, 9) == [0, 1, 2, 3, 4]
