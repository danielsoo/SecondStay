"""Read the outside of one building from the Vexcel API 2.0.

Credentials come from the environment (.env, never committed): VEXCEL_API_KEY,
sent in the X-API-KEY header. API reference: https://api.vexcelgroup.com/v2/api-docs

What we read for a CoStar latitude and longitude:

- /structure/extract   building footprints around the point (GeoJSON)
- /dsm/elevation       surface elevation (roof) at a point, in metres
- /dtm/elevation       ground elevation at a point, in metres
- /ortho/extract       a top-down image of the surroundings

Height is the highest roof point sampled on a grid over the footprint, minus the ground. The gap to the
neighbours is measured between footprints. Both are approximate and are shown
as evidence, never as a finding. Street frontage is not derived yet.
"""

import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Optional

from .checklist import SpaceFacts

API_URL = "https://api.vexcelgroup.com/v2"
M_TO_FT = 3.28084
SEARCH_RADIUS_M = 90.0
MIN_STRUCTURE_SQM = 40.0  # ignore sheds, kiosks and footprint slivers
IMAGE_ZOOM = 20  # about 0.13 m per pixel in Los Angeles
MAX_MATCH_DISTANCE_M = 40.0  # how far the CoStar point may sit from its footprint


@dataclass
class Outside:
    """What the imagery shows for one building. Coordinates are (longitude, latitude)."""

    height_ft: Optional[float] = None
    neighbor_gap_ft: Optional[float] = None
    footprint_sqft: Optional[float] = None
    footprint: list = field(default_factory=list)  # rings of the building itself
    neighbors: list = field(default_factory=list)  # rings of the other structures nearby
    neighbor_heights_ft: list = field(default_factory=list)  # one per neighbour ring, None if unread
    ground_m: Optional[float] = None  # ground elevation under the building
    bbox: list = field(default_factory=list)  # [west, south, east, north] of the image
    captured: str = ""
    collection: str = ""
    error: str = ""

    @property
    def loaded(self) -> bool:
        return bool(self.footprint)


def configured() -> bool:
    return bool(os.environ.get("VEXCEL_API_KEY"))


def _get(path: str, **params) -> bytes:
    url = f"{API_URL}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"X-API-KEY": os.environ.get("VEXCEL_API_KEY", "")})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Vexcel API returned {error.code} for {path}") from None


# --- geometry, in metres on a local flat grid -------------------------------------------------

def parse_rings(wkt: str) -> list:
    """Outer rings of a POLYGON or MULTIPOLYGON as lists of (lon, lat)."""
    rings = []
    for polygon in re.findall(r"\(\(([^()]+)\)", wkt or ""):
        points = [tuple(float(v) for v in pair.split()[:2]) for pair in polygon.split(",")]
        if len(points) >= 4:
            rings.append(points)
    return rings


def _grid(lat0: float, lon0: float):
    kx = 111320.0 * math.cos(math.radians(lat0))
    return lambda p: ((p[0] - lon0) * kx, (p[1] - lat0) * 110540.0)


def _inside(point, ring) -> bool:
    x, y = point
    hit = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def _to_segment(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _point_to_ring(p, ring) -> float:
    if _inside(p, ring):
        return 0.0
    return min(_to_segment(p, a, b) for a, b in zip(ring, ring[1:]))


def _ring_to_ring(first, second) -> float:
    return min(
        min(_point_to_ring(p, second) for p in first),
        min(_point_to_ring(p, first) for p in second),
    )


def _nearest_on_segment(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length))
    return (a[0] + t * dx, a[1] + t * dy)


def closest_pair(first: list, second: list) -> Optional[tuple]:
    """Closest points between two sets of outlines (rings or polylines), in (longitude, latitude).

    Returns (point on first, point on second, distance in feet), or None when either side is empty.
    Used to draw the measured gap on the image; the distance matches the measurement used in the review.
    """
    points = [p for line in first + second for p in line]
    if not any(first) or not any(second):
        return None
    lon0, lat0 = points[0]
    to_m = _grid(lat0, lon0)
    kx = 111320.0 * math.cos(math.radians(lat0))
    back = lambda q: (round(q[0] / kx + lon0, 7), round(q[1] / 110540.0 + lat0, 7))
    a_lines = [[to_m(p) for p in line] for line in first if line]
    b_lines = [[to_m(p) for p in line] for line in second if line]
    best = None
    for here, there, flip in ((a_lines, b_lines, False), (b_lines, a_lines, True)):
        for line in here:
            for p in line:
                for other in there:
                    for a, b in zip(other, other[1:]):
                        q = _nearest_on_segment(p, a, b)
                        d = math.hypot(p[0] - q[0], p[1] - q[1])
                        if best is None or d < best[2]:
                            best = (q, p, d) if flip else (p, q, d)
    if best is None:
        return None
    return back(best[0]), back(best[1]), round(best[2] * M_TO_FT, 1)


def _area(ring) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:]))) / 2


DRAW_TOLERANCE_M = 1.2  # footprint wobble below this is image-tracing noise, not a wall


def _douglas_peucker(points, tol):
    if len(points) < 3:
        return list(points)
    first, last = points[0], points[-1]
    far, index = -1.0, 0
    for i in range(1, len(points) - 1):
        d = _to_segment(points[i], first, last)
        if d > far:
            far, index = d, i
    if far <= tol:
        return [first, last]
    return _douglas_peucker(points[:index + 1], tol)[:-1] + _douglas_peucker(points[index:], tol)


def simplify_ring(ring, tolerance_m: float = DRAW_TOLERANCE_M) -> list:
    """A closed lon/lat ring with tracing jitter removed, for drawing only.

    Footprints traced from aerial imagery zigzag about a metre along straight walls; stacked
    once per floor, that reads as a torn edge. Areas and distances keep using the original ring.
    """
    if len(ring) < 5:
        return [tuple(p) for p in ring]
    to_m = _grid(ring[0][1], ring[0][0])
    pts = [to_m(p) for p in ring[:-1]]
    # Split the loop at the vertex farthest from the first, so both halves have fixed ends.
    split = max(range(len(pts)), key=lambda i: math.dist(pts[0], pts[i]))
    order = list(range(len(pts))) + [0]
    halves = (order[:split + 1], order[split:])
    keep = []
    for half in halves:
        sub = _douglas_peucker([pts[i] for i in half], tolerance_m)
        lookup = {pts[i]: i for i in half}
        keep.extend(lookup[p] for p in sub[:-1])
    if len(keep) < 3:
        return [tuple(p) for p in ring]
    return [tuple(ring[i]) for i in keep] + [tuple(ring[keep[0]])]


def _centroid(ring):
    xs, ys = [p[0] for p in ring[:-1]], [p[1] for p in ring[:-1]]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def roof_sample_points(ring, extra=None, grid: int = 6) -> list:
    """(lon, lat) points spread over the roof. Footprints often include a low podium,
    so a grid is needed to reach the tallest part."""
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    west, south, width, depth = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    points = [
        (west + width * (i + 0.5) / grid, south + depth * (j + 0.5) / grid)
        for i in range(grid) for j in range(grid)
    ]
    points = [p for p in points if _inside(p, ring)]
    if extra and _inside(extra, ring):
        points.append(extra)
    return points or [_centroid(ring)]


def measure(features: list, lat: float, lon: float) -> Outside:
    """Pick the building at (lat, lon) from structure features and measure it against the rest."""
    to_m = _grid(lat, lon)
    structures = []
    for feature in features:
        props = feature.get("properties") or {}
        rings = parse_rings(props.get("footprint.wkt") or "")
        metric = [[to_m(p) for p in ring] for ring in rings]
        metric = [ring for ring in metric if _area(ring) >= MIN_STRUCTURE_SQM]
        if metric:
            keep = [r for r in rings if _area([to_m(p) for p in r]) >= MIN_STRUCTURE_SQM]
            structures.append((min(_point_to_ring((0.0, 0.0), ring) for ring in metric), metric, keep, props))
    if not structures:
        return Outside(error="No building footprint was found in the imagery at this location.")
    structures.sort(key=lambda s: s[0])
    distance, subject, subject_rings, props = structures[0]
    if distance > MAX_MATCH_DISTANCE_M:
        return Outside(error="No building footprint in the imagery is close enough to the recorded location.")
    others = structures[1:]
    gaps = [_ring_to_ring(a, b) for _, rings, _, _ in others for a in subject for b in rings]
    return Outside(
        neighbor_gap_ft=round(min(gaps) * M_TO_FT, 1) if gaps else None,
        footprint_sqft=round(sum(_area(r) for r in subject) * M_TO_FT * M_TO_FT),
        footprint=subject_rings,
        neighbors=[ring for _, _, rings, _ in others for ring in rings],
        captured=(props.get("metadata.ortho-date-estimate") or "")[:10],
        collection=props.get("metadata.collection") or "",
    )


# --- API calls --------------------------------------------------------------------------------

def bbox(lat: float, lon: float, radius_m: float = SEARCH_RADIUS_M) -> list:
    dlat = radius_m / 110540.0
    dlon = radius_m / (111320.0 * math.cos(math.radians(lat)))
    return [lon - dlon, lat - dlat, lon + dlon, lat + dlat]


def _box_wkt(box: list) -> str:
    west, south, east, north = box
    corners = [(west, south), (east, south), (east, north), (west, north), (west, south)]
    return "POLYGON((" + ",".join(f"{x:.6f} {y:.6f}" for x, y in corners) + "))"


def _elevation(kind: str, point) -> Optional[float]:
    body = json.loads(_get(f"/{kind}/elevation", wkt=f"POINT({point[0]:.6f} {point[1]:.6f})"))
    match = re.search(r"POINT Z\s*\(\s*\S+\s+\S+\s+([-\d.]+)", body.get("wkt") or "")
    return float(match.group(1)) if match else None


def read_outside(lat: float, lon: float) -> Outside:
    """Footprint, neighbour gap and height for the building at this location."""
    box = bbox(lat, lon)
    features = json.loads(_get("/structure/extract", wkt=_box_wkt(box))).get("features") or []
    outside = measure(features, lat, lon)
    outside.bbox = box
    if not outside.loaded:
        return outside
    largest = max(outside.footprint, key=lambda ring: _area([_grid(lat, lon)(p) for p in ring]))
    points = roof_sample_points(largest, extra=(lon, lat))
    with ThreadPoolExecutor(max_workers=8) as pool:
        ground = pool.submit(_elevation, "dtm", points[0])
        roofs = [r for r in pool.map(lambda p: _elevation("dsm", p), points) if r is not None]
    outside.ground_m = ground.result()
    if roofs and outside.ground_m is not None:
        outside.height_ft = round((max(roofs) - outside.ground_m) * M_TO_FT)
    return add_neighbor_heights(outside)


def add_neighbor_heights(outside: Outside) -> Outside:
    """Rough height of each neighbouring structure, used only to draw the surroundings."""
    if not outside.neighbors:
        return outside
    if outside.ground_m is None:
        outside.ground_m = _elevation("dtm", _centroid(outside.footprint[0]))

    def height(ring):
        points = roof_sample_points(ring, grid=2)[:3]
        roofs = [r for r in (_elevation("dsm", p) for p in points) if r is not None]
        if not roofs or outside.ground_m is None:
            return None
        return max(0.0, round((max(roofs) - outside.ground_m) * M_TO_FT))

    with ThreadPoolExecutor(max_workers=8) as pool:
        outside.neighbor_heights_ft = list(pool.map(height, outside.neighbors))
    return outside


def fetch_image(box: list, zoom: int = IMAGE_ZOOM) -> bytes:
    """Top-down JPEG of the bounding box."""
    return _get(
        "/ortho/extract",
        **{"wkt": _box_wkt(box), "image-format": "jpeg", "crop": "bounding_box", "zoom": zoom},
    )


SURFACE_SIZE = 256  # cells per side of the surface grid sent to the page (about 0.7 m each near one building)


def _mercator(lon: float, lat: float) -> tuple:
    r = 6378137.0
    return (math.radians(lon) * r, math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * r)


def read_surface(tiff: bytes, box: list, ground_m: Optional[float] = None, size: int = SURFACE_SIZE) -> dict:
    """Heights above the ground on a size x size grid over box, from a /dsm/extract GeoTIFF.

    The DSM is the top of whatever was there when the imagery was captured: roofs, trees, cars, lamps.
    It is used to lay the aerial photo over a surface for display only; nothing is measured from this grid.
    """
    import io
    from array import array

    from PIL import Image

    image = Image.open(io.BytesIO(tiff))
    image.info.pop("xmp", None)  # Pillow cannot parse Vexcel's XMP block; it carries nothing needed here
    image.load()
    tie, scale = image.tag_v2[33922], image.tag_v2[33550]
    nodata = float(str(image.tag_v2.get(42113, "-9999")).strip("\x00") or -9999)
    values = array("f")
    values.frombytes(image.tobytes())
    # Vexcel writes big-endian floats and Pillow may hand them over unswapped: keep the byte order
    # under which more samples look like elevations in metres.
    plausible = lambda vs: sum(1 for v in vs[:: max(1, len(vs) // 4000)] if -500.0 < v < 9000.0 and abs(v) > 1e-3)
    swapped = array("f", values)
    swapped.byteswap()
    if plausible(swapped) > plausible(values):
        values = swapped
    real = lambda v: v > nodata + 1 and -500.0 < v < 9000.0  # metres above sea level anywhere on land
    usable = sorted(v for v in values[:: max(1, len(values) // 4000)] if real(v))
    if not usable:
        raise ValueError("The surface image has no readable heights.")
    floor = usable[len(usable) // 20]  # 5th percentile: open ground in the tile
    values = array("f", (v if real(v) else floor for v in values))
    surface = Image.frombytes("F", image.size, values.tobytes())
    # Crop the raster to the requested box (Web Mercator pixels), then average down to the grid.
    x0, y1 = _mercator(box[0], box[3])
    x1, y0 = _mercator(box[2], box[1])
    col = lambda x: tie[0] + (x - tie[3]) / scale[0]  # the tie point is a raster position, not always (0, 0)
    row = lambda y: tie[1] + (tie[4] - y) / scale[1]
    window = (max(0, round(col(x0))), max(0, round(row(y1))), min(image.size[0], round(col(x1))), min(image.size[1], round(row(y0))))
    if window[2] - window[0] < 2 or window[3] - window[1] < 2:
        raise ValueError("The surface image does not cover this area.")
    grid = surface.crop(window).resize((size, size), Image.BOX)
    base = ground_m if ground_m is not None else floor
    heights = [round(max(-2.0, v - base), 2) for v in (grid.get_flattened_data() if hasattr(grid, "get_flattened_data") else grid.getdata())]
    return {"size": size, "box": box, "ground_m": round(base, 2), "heights": heights}


def fetch_surface(box: list, ground_m: Optional[float] = None) -> dict:
    """The /dsm/extract surface over box, reduced to a display grid."""
    return read_surface(_get("/dsm/extract", wkt=_box_wkt(box)), box, ground_m)


def to_facts(outside: Outside, facts: Optional[SpaceFacts] = None) -> SpaceFacts:
    """Fill the Vexcel part of SpaceFacts. Street frontage stays empty for now."""
    facts = facts or SpaceFacts()
    facts.height_ft = outside.height_ft
    facts.neighbor_gap_ft = outside.neighbor_gap_ft
    return facts


def dump(outside: Outside) -> str:
    return json.dumps(asdict(outside))


def load(text: str) -> Outside:
    raw = json.loads(text)
    for key in ("footprint", "neighbors"):
        raw[key] = [[tuple(p) for p in ring] for ring in raw[key]]
    return Outside(**raw)
