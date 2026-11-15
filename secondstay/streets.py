"""Public streets around a building, from OpenStreetMap.

Used for the fire access row: which public street the building fronts and how far the
footprint is from it. OpenStreetMap is a fourth, public source next to the three sponsor
layers; it is named wherever its evidence is shown. Results are cached under data/raw/.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

from . import vexcel

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
SEARCH_RADIUS_M = 150
# Road classes open to the public and wide enough to count as a street. Service roads,
# driveways and alleys are listed separately and do not count as frontage.
PUBLIC_STREETS = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
    "living_street", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
}


@dataclass
class Street:
    name: str
    kind: str  # OpenStreetMap highway class
    points: list  # (lon, lat)
    distance_ft: Optional[float] = None  # from the building footprint

    @property
    def public(self) -> bool:
        return self.kind in PUBLIC_STREETS


def fetch(lat: float, lon: float, radius_m: int = SEARCH_RADIUS_M) -> list:
    """Roads within radius_m of the point, as plain dicts."""
    query = f"[out:json][timeout:25];way(around:{radius_m},{lat:.6f},{lon:.6f})[highway];out tags geom;"
    request = urllib.request.Request(
        OVERPASS_URL, data=urllib.parse.urlencode({"data": query}).encode(),
        headers={"User-Agent": "secondstay-precheck"},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = json.loads(response.read())
            break
        except urllib.error.HTTPError as error:
            if error.code not in (429, 504) or attempt == 3:
                raise RuntimeError(f"OpenStreetMap returned {error.code}") from None
            time.sleep(4 * (attempt + 1))
    return [
        {
            "name": (way.get("tags") or {}).get("name") or "",
            "kind": (way.get("tags") or {}).get("highway") or "",
            "points": [(p["lon"], p["lat"]) for p in way.get("geometry") or []],
        }
        for way in body.get("elements") or []
        if len(way.get("geometry") or []) >= 2
    ]


def fetch_many(points: list, radius_m: int = SEARCH_RADIUS_M) -> list:
    """Roads around several (lat, lon) points in one request: one list of roads per point."""
    around = "".join(f"way(around:{radius_m},{lat:.6f},{lon:.6f})[highway];" for lat, lon in points)
    query = f"[out:json][timeout:120];({around});out tags geom;"
    request = urllib.request.Request(
        OVERPASS_URL, data=urllib.parse.urlencode({"data": query}).encode(),
        headers={"User-Agent": "secondstay-precheck"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        ways = json.loads(response.read()).get("elements") or []
    roads = [
        {
            "name": (way.get("tags") or {}).get("name") or "",
            "kind": (way.get("tags") or {}).get("highway") or "",
            "points": [(p["lon"], p["lat"]) for p in way.get("geometry") or []],
        }
        for way in ways if len(way.get("geometry") or []) >= 2
    ]
    result = []
    for lat, lon in points:
        to_m = vexcel._grid(lat, lon)
        near = []
        for road in roads:
            line = [to_m(p) for p in road["points"]]
            if min(vexcel._to_segment((0.0, 0.0), a, c) for a, c in zip(line, line[1:])) <= radius_m:
                near.append(road)
        result.append(near)
    return result


def measure(roads: list, footprint: list, lat: float, lon: float) -> list:
    """Streets with their distance from the footprint, closest first."""
    to_m = vexcel._grid(lat, lon)
    rings = [[to_m(p) for p in ring] for ring in footprint]
    streets = []
    for road in roads:
        line = [to_m(tuple(p)) for p in road["points"]]
        if not rings:
            distance = None
        else:
            distance = min(
                min(vexcel._to_segment(p, a, b) for ring in rings for p in ring for a, b in zip(line, line[1:])),
                min(vexcel._point_to_ring(p, ring) for ring in rings for p in line),
            )
        streets.append(Street(
            road["name"], road["kind"], [tuple(p) for p in road["points"]],
            round(distance * vexcel.M_TO_FT, 1) if distance is not None else None,
        ))
    return sorted(streets, key=lambda s: (s.distance_ft is None, s.distance_ft or 0))


def frontage(streets: list) -> Optional[Street]:
    """The closest public street, if any was found."""
    return next((s for s in streets if s.public and s.distance_ft is not None), None)
