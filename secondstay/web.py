"""Local checklist screen: ``python -m secondstay.web`` then open http://127.0.0.1:8000.

Reads the CoStar kit from disk and Matterport from the API at request time, so
no real records, model ids or keys are ever part of the repo. Standard library
only.
"""

import datetime
import json
import os
import re
import sys
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import costar, evidence, finances, matterport, panoramas, streets, vexcel
from .changes import CERTAINTIES, changes_for, to_dicts
from .checklist import NOTICE, STATES, build_checklist, next_steps, stairs_by_floor, summary, top_occupied_ft

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
SCAN_CACHE = REPO_ROOT / "data" / "raw" / "matterport"
OUTSIDE_CACHE = REPO_ROOT / "data" / "raw" / "vexcel"
STREET_CACHE = REPO_ROOT / "data" / "raw" / "streets"
MODEL_ID = re.compile(r"^[A-Za-z0-9]{6,20}$")

# Which evidence view the right-hand side shows for each requirement.
VIEWS = {
    "age": "record", "zone": "record", "elevator": "record", "sprinklers": "record",
    "units": "scan", "exits": "scan", "escape": "scan",
    "height": "aerial", "separation": "aerial", "access": "aerial",
    "stay": "setting",
}


def load_env(path: Path = REPO_ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#") and value.strip():
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def matterport_configured() -> bool:
    return bool(os.environ.get("MATTERPORT_TOKEN_ID") and os.environ.get("MATTERPORT_TOKEN_SECRET"))


def read_scan(model_id: str):
    """Return (model, error). Cached under data/raw/, which is git-ignored."""
    cached = SCAN_CACHE / f"{model_id}.json"
    if cached.exists():
        return json.loads(cached.read_text()), ""
    if not matterport_configured():
        return None, "Matterport keys are not set in .env, so the scan has not been measured."
    if os.environ.get("SECONDSTAY_OFFLINE"):
        return None, "Offline mode: no cached scan is available."
    try:
        model = matterport.fetch_model(model_id)
    except Exception as error:  # network, auth or API error: show it, keep the screen working
        return None, f"The scan could not be read: {error}"
    if model is None:
        return None, "The Matterport API returned no model for this scan."
    SCAN_CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(model))
    return model, ""


def read_outside(b: costar.Building, fetch: bool = True) -> vexcel.Outside:
    """What Vexcel imagery shows for the building. Cached under data/raw/, which is git-ignored."""
    cached = OUTSIDE_CACHE / f"{b.property_id}.json"
    if cached.exists():
        outside = vexcel.load(cached.read_text())
        if fetch and not os.environ.get("SECONDSTAY_OFFLINE") and outside.neighbors and not outside.neighbor_heights_ft and vexcel.configured():
            try:  # caches written before the 3D view have no neighbour heights
                cached.write_text(vexcel.dump(vexcel.add_neighbor_heights(outside)))
            except Exception:
                pass
        return outside
    if b.latitude is None or b.longitude is None:
        return vexcel.Outside(error="The record has no location, so imagery could not be looked up.")
    if not vexcel.configured():
        return vexcel.Outside(error="The Vexcel key is not set in .env, so nothing has been measured from the air.")
    if os.environ.get("SECONDSTAY_OFFLINE"):
        return vexcel.Outside(error="Offline mode: no cached aerial measurements are available.")
    if not fetch:
        return vexcel.Outside(error="Not read yet.")
    try:
        outside = vexcel.read_outside(b.latitude, b.longitude)
    except Exception as error:  # network, auth or API error: show it, keep the screen working
        return vexcel.Outside(error=f"The imagery could not be read: {error}")
    OUTSIDE_CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(vexcel.dump(outside))
    return outside


def read_streets(b: costar.Building, outside: vexcel.Outside, fetch: bool = True) -> list:
    """Streets around the building with their distance from its footprint. Empty when unread."""
    cached = STREET_CACHE / f"{b.property_id}.json"
    if cached.exists():
        roads = json.loads(cached.read_text())
    elif fetch and outside.loaded and not os.environ.get("SECONDSTAY_OFFLINE"):
        try:
            roads = streets.fetch(b.latitude, b.longitude)
        except Exception:
            return []
        STREET_CACHE.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(roads))
    else:
        return []
    return streets.measure(roads, outside.footprint, b.latitude, b.longitude)


def add_street_facts(facts, found: list, read: bool) -> None:
    if not read or not any(s.distance_ft is not None for s in found):  # unread, or no footprint to measure from
        return
    front = streets.frontage(found)
    facts.street_frontage = front is not None
    if front:
        facts.street_name, facts.street_distance_ft = front.name, front.distance_ft


def context_bbox(box: list) -> list:
    """Eight times the photo coverage per axis, for the orbiting 3D scene only."""
    if len(box) != 4:
        return []
    west, south, east, north = box
    lon, lat = (west + east) / 2, (south + north) / 2
    dx, dy = (east - west) * 4, (north - south) * 4
    return [lon - dx, lat - dy, lon + dx, lat + dy]


def read_image(b: costar.Building, context: bool = False) -> bytes:
    # Lower zoom keeps the wider overview near the original image's pixel count.
    zoom = vexcel.IMAGE_ZOOM - 3 if context else vexcel.IMAGE_ZOOM
    suffix = ".context-v1" if context else ""
    cached = OUTSIDE_CACHE / f"{b.property_id}{suffix}.z{zoom}.jpg"
    if cached.exists():
        return cached.read_bytes()
    if os.environ.get("SECONDSTAY_OFFLINE"):
        raise FileNotFoundError("No cached image is available.")
    box = read_outside(b).bbox
    if context:
        box = context_bbox(box)
    if not box:
        raise FileNotFoundError("No imagery bounds are available.")
    image = vexcel.fetch_image(box, zoom=zoom)
    OUTSIDE_CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(image)
    return image


def read_surface(b: costar.Building) -> dict:
    """The Vexcel surface grid over the building's image, for laying the photo on in 3D. Cached under data/raw/."""
    cached = OUTSIDE_CACHE / f"{b.property_id}.surface-v1.json"
    if cached.exists():
        return json.loads(cached.read_text())
    if os.environ.get("SECONDSTAY_OFFLINE"):
        raise FileNotFoundError("No cached surface is available.")
    outside = read_outside(b)
    if not outside.bbox:
        raise FileNotFoundError("No imagery bounds are available.")
    surface = vexcel.fetch_surface(outside.bbox, outside.ground_m)
    OUTSIDE_CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(surface, separators=(",", ":")))
    return surface


def outside_fields(o: vexcel.Outside) -> dict:
    feet = lambda v: f"about {v:,.0f} ft" if v is not None else None
    area = f"about {o.footprint_sqft:,.0f} sq ft" if o.footprint_sqft else None
    return {
        "height": [("Highest roof point above ground", feet(o.height_ft), "Vexcel /dsm/elevation minus /dtm/elevation")],
        "access": [],
        "separation": [
            ("Closest other structure", feet(o.neighbor_gap_ft), "Vexcel /structure/extract footprints"),
            ("Other structures within about 300 ft", len(o.neighbors) if o.loaded else None, "Vexcel /structure/extract"),
            ("Footprint of this building", area, "Vexcel /structure/extract"),
        ],
    }


def measure_lines(o: vexcel.Outside, streets_found: list) -> dict:
    """End points of the measured gaps, so each evidence image can show the distance it states."""
    lines = {}
    if o.loaded and o.neighbors:
        pair = vexcel.closest_pair(o.footprint, o.neighbors)
        if pair:
            lines["separation"] = {"points": [pair[0], pair[1]], "feet": pair[2],
                                   "label": "Closest other structure"}
    street = streets.frontage(streets_found) if streets_found else None
    if o.loaded and street:
        pair = vexcel.closest_pair(o.footprint, [list(street.points)])
        if pair:
            lines["access"] = {"points": [pair[0], pair[1]], "feet": pair[2],
                               "label": f"Closest public street: {street.name}" if street.name else "Closest public street"}
    return lines


def best_cached_scan(b: costar.Building) -> str:
    """The scan with room labels, then the largest measured area, among those already read."""
    best, best_rank = "", (False, False, False, 0.0)
    for scan in b.scans:
        cached = SCAN_CACHE / f"{scan.model_id}.json"
        if not cached.exists():
            continue
        rank = matterport.scan_rank(matterport.to_facts(json.loads(cached.read_text())))
        if rank > best_rank:
            best, best_rank = scan.model_id, rank
    return best


def record_fields(b: costar.Building) -> dict:
    """Record values shown as evidence, per requirement: (label, value, CoStar field)."""
    sprinklers = {True: "Yes", False: "No", None: None}[b.has_sprinklers]
    if sprinklers == "Yes" and b.sprinkler_type:
        sprinklers += f" ({b.sprinkler_type})"
    height = f"{b.record_height_ft:.0f} ft" if b.record_height_ft else None
    stories = ("Stories above grade", b.stories, "numStoriesAboveGrade")
    return {
        "age": [("Year built", b.year_built, "constructionEvents[] (ConstructionComplete)")],
        "zone": [
            ("Zoning as recorded", b.zone_recorded, "zoningDescription"),
            ("Zone class we read from it", b.zone, "derived"),
            ("Parcel numbers", ", ".join(b.parcel_numbers) or None, "parcelNumbers"),
        ],
        "elevator": [
            stories,
            ("Passenger elevators", b.passenger_elevators, "propertyOffice.structural.elevators[]"),
        ],
        "sprinklers": [("Sprinkler system", sprinklers, "hasSprinklers, sprinklerType")],
        "height": [stories, ("Building height", height, "buildingHeightInFeet")],
    }


def floors_3d(b: costar.Building) -> int:
    """Floors the floor view can draw (from a Matterport scan or a traced plan); the landing puts these buildings first."""
    from .floor_geometry import source_catalog
    try:
        floors = source_catalog(b)["floors"]
    except Exception:  # a broken private model must not take the landing down
        return 0
    return sum(1 for f in floors if any(a.get("geometry_available") for a in f["assets"]))


def showcase_key(card: dict) -> tuple:
    """Most complete first: buildings with a 3D tour, then the most floors drawn, then the most scans."""
    return (-(1 if card.get("scans") else 0), -card.get("floors_3d", 0), -card.get("scans", 0), -(card.get("available_sqft") or 0))


def building_card(b: costar.Building) -> dict:
    card = asdict(b)
    card["zone"] = b.zone
    card["unaccounted_share"] = b.unaccounted_share
    return card


def space_payload(b: costar.Building, model_id: str = "", space_id: str = "") -> dict:
    """Everything the screen shows for one building, for one suite on the market when one is chosen."""
    from .floor_geometry import source_catalog
    space = next((s for s in b.spaces if str(s["id"]) == str(space_id)), None)
    scan_ids = space["scans"] if space else [s.model_id for s in b.scans]
    if model_id not in scan_ids:
        if space:  # only a scan of that suite stands for it
            ranked = sorted(
                space["scans"],
                key=lambda m: matterport.scan_rank(matterport.to_facts(read_scan(m)[0] or {})), reverse=True,
            )
            model_id = ranked[0] if ranked else ""
        else:
            model_id = best_cached_scan(b) or (scan_ids[0] if scan_ids else "")
    if model_id:
        model, scan_error = read_scan(model_id)
    else:
        model, scan_error = None, (
            "CoStar has no 3D scan tied to this suite." if space else "This building has no scan."
        )
    facts = costar.to_facts(b, matterport.to_facts(model) if model else None)
    if space:
        facts.space_sqft = space["sqft"]
        facts.space_label = f"Suite {space['suite']}" if space["suite"] else space["floor_label"]
    read = panoramas.reading(model_id) if model_id else None
    facts.pano_reading = read
    # The plan shown is the selected suite's own plan. A reading only counts for the image it was read from.
    stand_in = plan_to_read(b)
    image = {"url": space["plan_url"], "caption": facts.space_label, "source": "space"} if space and space["plan_url"] else (
        None if space else stand_in)
    whole_floor = stand_in and stand_in["source"] == "building"
    reading = plan_reading(b) if stand_in and (image and image["url"] == stand_in["url"] or whole_floor) else None
    facts.plan_reading = reading
    outside = read_outside(b)
    if outside.loaded:
        vexcel.to_facts(outside, facts)
    found = read_streets(b, outside)
    add_street_facts(facts, found, bool(found) or (STREET_CACHE / f"{b.property_id}.json").exists())
    year = datetime.date.today().year
    permit_summary, public, plan_summary = evidence.load(b)
    rows = evidence.apply(build_checklist(facts, year), facts, permit_summary, public, space, plan_summary)
    changes = changes_for(facts, rows, year)
    fields = record_fields(b)
    for key, extra in outside_fields(outside).items():
        fields[key] = fields.get(key, []) + extra
    placed = next((s for s in b.scans if s.model_id == model_id), None)
    scan = {
        "model_id": model_id, "loaded": model is not None, "error": scan_error, "reading": read,
        "sheet": bool(model_id) and (panoramas.SHEET_DIR / f"{model_id}.jpg").exists(),
        "suite": placed.suite if placed else "", "floor": placed.floor if placed else None,
        "floor_basis": placed.floor_basis if placed else "",
    }
    if model:
        kinds: dict = {}
        for room in facts.rooms:
            kinds[room.kind or "Unlabelled"] = kinds.get(room.kind or "Unlabelled", 0) + 1
        scan.update(
            name=model.get("name") or "",
            floors=len(facts.floor_areas_sqft),
            area_sqft=sum(a for a in facts.floor_areas_sqft if a),
            room_kinds=kinds,
            windows=sum(r.windows or 0 for r in facts.rooms) if any(r.windows is not None for r in facts.rooms) else None,
            stairs=stairs_by_floor(facts),
            uses=[c.get("classification") for c in model.get("propertyClassifications") or []],
            lines=matterport.plan_lines(model),
        )
    floor = space["floor"] if space else (placed.floor if placed else None)
    return {
        "notice": NOTICE,
        "states": STATES,
        "building": building_card(b),
        "space": space,
        "floor": floor,
        "floor_sources": source_catalog(b),
        "scan": scan,
        "sdk_key": os.environ.get("MATTERPORT_SDK_KEY", ""),
        # Outlines are drawn without tracing jitter; measurements above used the original rings.
        "outside": {**asdict(outside), "loaded": outside.loaded, "context_bbox": context_bbox(outside.bbox),
                    "footprint": [vexcel.simplify_ring(r) for r in outside.footprint],
                    "neighbors": [vexcel.simplify_ring(r) for r in outside.neighbors]},
        "reference_plan": reference_plan(b),
        "plan": {
            "image": image, "reading": reading, "count": len(b.floor_plans),
            "reading_from": stand_in if reading and (not image or image["url"] != stand_in["url"]) else None,
        },
        "top_occupied_ft": top_occupied_ft(facts),
        "measure_lines": measure_lines(outside, found),
        "streets": [asdict(s) | {"public": s.public} for s in found],
        "changes": to_dicts(changes),
        "permits": permit_summary,
        "public_records": public,
        "plan_readings": plan_summary,
        "change_counts": {c: sum(1 for x in changes if x.certainty == c) for c in CERTAINTIES},
        "counts": summary(rows),
        "rows": [
            {
                **asdict(r),
                "view": VIEWS.get(r.key, "none"),
                "fields": [
                    {"label": label, "value": value, "field": field}
                    for label, value, field in fields.get(r.key, [])
                ],
            }
            for r in rows
        ],
        "next_steps": [
            {"who": who, "items": [{"requirement": r.requirement, "state": r.state, "evidence": r.evidence} for r in items]}
            for who, items in next_steps(rows).items()
        ],
    }


def read_scan_plan(model_id: str):
    """Matterport's top-down picture of a scan, cached. None when there is none."""
    cached = SCAN_CACHE / f"{model_id}.plan.jpg"
    if cached.exists():
        return cached.read_bytes()
    if os.environ.get("SECONDSTAY_OFFLINE"):
        return None
    if not matterport_configured():
        return None
    image = matterport.fetch_plan_image(model_id)
    if image:
        SCAN_CACHE.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(image)
    return image


PLAN_READING_DIR = REPO_ROOT / "data" / "raw" / "plan_readings"


def plan_to_read(b: costar.Building):
    """Prefer a building attachment; its coverage must be read from the sheet."""
    attached = [p for p in b.floor_plans if p["source"] == "building"]
    return (attached or b.floor_plans or [None])[0]


def plan_reading(b: costar.Building):
    """What was read from that plan, or None. Stored under data/raw/, which is git-ignored."""
    path = PLAN_READING_DIR / f"{b.property_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return data if isinstance(data.get("stairs"), int) else None


def reference_plan(b: costar.Building):
    """A whole-floor plan of this building, read as showing the full floor with its core.

    Used only as a labelled reference on floors that have no record of their own.
    """
    candidates = []
    first = plan_to_read(b)
    path = PLAN_READING_DIR / f"{b.property_id}.json"
    if first and path.exists():
        candidates.append((first, json.loads(path.read_text())))
    whole = [p for p in b.floor_plans if p["source"] == "building"]
    for k, plan in enumerate(whole):
        read = REPO_ROOT / "data" / "raw" / "plan_readings_all" / f"{b.property_id}__{k}.json"
        if read.exists():
            candidates.append((plan, json.loads(read.read_text())))
    for plan, reading in candidates:
        if reading.get("covers") == "floor":
            return {"url": plan["url"], "caption": plan.get("caption") or "", "floor_named": reading.get("floor_named"),
                    "stairs": reading.get("stairs"), "elevators": reading.get("elevators")}
    return None


PLANS_IN_LIST = True  # the plan gallery reads them from the list


def list_payload(buildings: list) -> dict:
    year = datetime.date.today().year
    spaces = []
    for b in buildings:
        card = building_card(b)
        card["scans"] = len(b.scans)
        card["tours"] = sum(1 for sp in b.spaces if sp["scans"])  # listed spaces with their own Matterport tour
        card["floors_3d"] = floors_3d(b)
        for key in ("aerial_urls", "parcel_numbers"):
            card.pop(key)
        card["floor_plan_count"] = len(b.floor_plans)
        card["plan_to_read"] = plan_to_read(b)
        card["plan_reading"] = plan_reading(b)
        if not PLANS_IN_LIST:
            card.pop("floor_plans")
        facts = costar.to_facts(b)
        facts.plan_reading = plan_reading(b)
        outside = read_outside(b, fetch=False)
        if outside.loaded:
            vexcel.to_facts(outside, facts)
        add_street_facts(facts, read_streets(b, outside, fetch=False), (STREET_CACHE / f"{b.property_id}.json").exists())
        card["height_ft"] = outside.height_ft
        card["footprint_sqft"] = outside.footprint_sqft
        permit_summary, public, plan_summary = evidence.load(b)
        card["counts"] = summary(evidence.apply(build_checklist(facts, year), facts, permit_summary, public, None, plan_summary))
        spaces.append(card)
    spaces.sort(key=showcase_key)
    return {"notice": NOTICE, "states": STATES, "spaces": spaces}


_list_cache = {"at": 0.0, "data": None}


REGION_ZOOM = 14  # about 7 m per pixel: the whole set of buildings on one Vexcel image
REGION_PAD = 0.012  # degrees of margin around the buildings
_city_cache = {"data": None}


def region_box(buildings: list) -> list:
    lats = [b.latitude for b in buildings if b.latitude is not None]
    lons = [b.longitude for b in buildings if b.longitude is not None]
    return [round(min(lons) - REGION_PAD, 6), round(min(lats) - REGION_PAD, 6),
            round(max(lons) + REGION_PAD, 6), round(max(lats) + REGION_PAD, 6)]


def region_image(buildings: list) -> bytes:
    """One Vexcel image under every building on the landing view. Cached under data/raw/ (git-ignored)."""
    box = region_box(buildings)
    cached = OUTSIDE_CACHE / f"region.{'_'.join(map(str, box))}.z{REGION_ZOOM}.jpg"
    if not cached.exists():
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(vexcel.fetch_image(box, zoom=REGION_ZOOM))
    return cached.read_bytes()


def market_minimum(b: costar.Building, book) -> dict:
    """The least the published rules call for, for the space this building has on the market.

    Same checklist and price book as the review screen, without reading scans or calling a model.
    """
    from . import costing
    year = datetime.date.today().year
    facts = costar.to_facts(b)
    facts.plan_reading = plan_reading(b)
    outside = read_outside(b, fetch=False)
    if outside.loaded:
        vexcel.to_facts(outside, facts)
    add_street_facts(facts, read_streets(b, outside, fetch=False), (STREET_CACHE / f"{b.property_id}.json").exists())
    facts.space_sqft, facts.space_label = b.available_sqft or None, "Space on the market"
    permit_summary, public, plan_summary = evidence.load(b)
    rows = evidence.apply(build_checklist(facts, year), facts, permit_summary, public, None, plan_summary)
    changes = changes_for(facts, rows, year)
    estimate = costing.estimate(changes, book, scenario="base")
    homes = next((c.quantity for c in changes if c.key == "units.kitchen"), None)
    low = (estimate.get("total") or {}).get("low")
    return {"minimum": low, "homes": homes, "per_home": low / homes if low and homes else None,
            "to_quote": len(estimate["left_out"]), "to_confirm": sum(1 for c in changes if c.certainty == "possible"),
            "issues": sum(1 for r in rows if r.state == "Possible issue")}


_city_costs = {"data": None, "lock": threading.Lock()}


def city_costs(buildings: list) -> dict:
    """Minimum cost and open items per building, keyed by property id. Takes most of a minute; cached."""
    with _city_costs["lock"]:
        if _city_costs["data"] is None:
            from . import costing
            book = costing.load_prices(finances.PRICE_PATH)
            finances.with_la_prices(book)
            _city_costs["data"] = {str(b.property_id): market_minimum(b, book) for b in buildings}
    return _city_costs["data"]


def city_payload(buildings: list) -> dict:
    """Every building on the market with its measured footprint and height, for the landing view."""
    if _city_cache["data"] is None:
        rows = []
        for b in buildings:
            outside = read_outside(b, fetch=False)
            rows.append({
                "property_id": b.property_id, "name": b.name, "address": b.address,
                "latitude": b.latitude, "longitude": b.longitude, "stories": b.stories,
                "height_ft": outside.height_ft if outside.loaded else None,
                "footprint": [vexcel.simplify_ring(r) for r in outside.footprint] if outside.loaded else [],
                "available_sqft": b.available_sqft, "spaces": len(b.spaces),
                "tours": sum(1 for s in b.spaces if s["scans"]), "plans": sum(1 for s in b.spaces if s["plan_url"]),
                "scans": len(b.scans), "floors_3d": floors_3d(b),
                # Bounds of /api/spaces/<id>/aerial.jpg?context=1, laid in sharp when the camera comes close.
                "photo_bbox": context_bbox(outside.bbox) if outside.loaded else [],
            })
        rows.sort(key=showcase_key)
        _city_cache["data"] = {"bbox": region_box(buildings), "image": "/api/city/aerial.jpg", "buildings": rows,
                               "image_source": "Vexcel aerial imagery"}
    return _city_cache["data"]


def cached_list(buildings: list, keep_seconds: float = 300.0) -> dict:
    """The list takes a few seconds to build (streets are measured for every building), so keep it."""
    import time

    if _list_cache["data"] is None or time.time() - _list_cache["at"] > keep_seconds:
        _list_cache.update(at=time.time(), data=list_payload(buildings))
    return _list_cache["data"]


def next_steps_markdown(payload: dict) -> str:
    b = payload["building"]
    title = b["name"] or b["address"]
    lines = [
        f"# Next steps: {title}", "",
        f"> {payload['notice']}", "",
        f"{b['address']}, Los Angeles · prepared {datetime.date.today().isoformat()}", "",
        "Evidence review so far: " + " · ".join(f"{s} {n}" for s, n in payload["counts"].items()), "",
        "The items below are open. Each is listed under who confirms it.", "",
    ]
    for group in payload["next_steps"]:
        lines += [f"## {group['who']}", ""]
        lines += [f"- **{i['requirement']}** ({i['state']}): {i['evidence']}" for i in group["items"]]
        lines.append("")
    return "\n".join(lines)


class Handler(BaseHTTPRequestHandler):
    buildings: dict = {}

    def log_message(self, fmt, *args):  # keep addresses and ids out of the terminal log
        pass

    def _send(self, status: int, body: bytes, content_type: str, extra: dict = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: int = 200):
        self._send(status, json.dumps(data).encode(), "application/json")

    def _cost(self, url, options):
        """Conversion cost and housing income for one space, from its change list (the teammate's cost model)."""
        match = re.fullmatch(r"/api/spaces/(\d+)/cost", url.path)
        building = self.buildings.get(int(match.group(1))) if match else None
        if building is None:
            return self._json({"error": "Not found"}, 404)
        query = parse_qs(url.query)
        scan, space = (query.get("scan") or [""])[0], (query.get("space") or [""])[0]
        if space and not any(str(s["id"]) == space for s in building.spaces):
            return self._json({"error": "Selected space not found"}, 404)
        try:
            return self._json(finances.calculate(space_payload(building, scan, space), options))
        except ValueError as error:
            return self._json({"error": str(error)}, 400)

    def do_POST(self):
        from . import agent
        # A browser on another origin must not initiate billable local runs.
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if (urlparse("http://" + host).hostname not in ("localhost", "127.0.0.1")
                or (origin and origin != "http://" + host)
                or self.headers.get("Content-Type") != "application/json"):
            return self._json({"error": "Use the local evidence review screen."}, 403)
        if re.fullmatch(r"/api/spaces/\d+/cost", urlparse(self.path).path):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    raise ValueError("Request must contain 1–65536 bytes")
                options = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeError) as error:
                return self._json({"error": str(error)}, 400)
            return self._cost(urlparse(self.path), options)
        match = re.fullmatch(r"/api/spaces/(\d+)/reviews", self.path)
        building = self.buildings.get(int(match.group(1))) if match else None
        if building is None:
            return self._json({"error": "Not found"}, 404)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 2048:
                raise ValueError("Invalid request length.")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict) or set(data) - {"space", "scan"}:
                raise ValueError("Supply only space and scan.")
            if any(not isinstance(value, str) for value in data.values()):
                raise ValueError("Space and scan must be text identifiers.")
            run_id = agent.start_review(building, data.get("space", ""), data.get("scan", ""))
            return self._json({"id": run_id}, 202)
        except agent.ConfigurationError as error:
            return self._json({"error": str(error)}, 503)
        except ValueError:
            return self._json({"error": "Choose a space and scan linked to this building."}, 400)
        except RuntimeError as error:
            return self._json({"error": str(error)}, 409)

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if url.path in ("/costs.js", "/costs.css"):
            kind = "text/javascript" if url.path.endswith(".js") else "text/css"
            return self._send(200, (STATIC / url.path[1:]).read_bytes(), kind + "; charset=utf-8")
        if re.fullmatch(r"/api/spaces/\d+/cost", url.path):
            return self._cost(url, {})
        if url.path in ("/static/floor_explorer.mjs", "/static/floor_motion.mjs", "/static/plan_trace.mjs", "/static/opening_layout.mjs", "/static/floor_accounting.mjs",
                        "/static/permit_years.mjs"):
            return self._send(200, (STATIC / url.path.rsplit("/", 1)[1]).read_bytes(), "text/javascript; charset=utf-8")
        floor_route = re.fullmatch(r"/api/spaces/(\d+)/floor-geometry", url.path)
        if floor_route:
            from .floor_geometry import geometry_for
            building = self.buildings.get(int(floor_route.group(1)))
            if not building:
                return self._json({"error": "Not found"}, 404)
            try:
                result = geometry_for(building, int((query.get("floor") or ["0"])[0]), (query.get("space") or [""])[0], (query.get("scan") or [""])[0])
                return self._json(result)
            except ValueError as error:
                return self._json({"error": str(error)}, 400)
        if url.path == "/api/city":
            return self._json(city_payload(list(self.buildings.values())))
        if url.path == "/api/city/costs":
            return self._json(city_costs(list(self.buildings.values())))
        if url.path == "/api/city/aerial.jpg":
            try:
                return self._send(200, region_image(list(self.buildings.values())), "image/jpeg")
            except Exception as error:  # no key or provider failure: the landing view falls back to a plain ground
                return self._json({"error": f"Regional imagery unavailable ({type(error).__name__})."}, 503)
        if url.path == "/api/spaces":
            return self._json(cached_list(list(self.buildings.values())))
        if url.path == "/api/agent":
            from .agent import configuration
            return self._json(configuration())
        review = re.fullmatch(r"/api/reviews/([a-f0-9]{32})(/report\.md)?", url.path)
        if review:
            from .agent import load_run
            try:
                run = load_run(review.group(1))
            except (ValueError, OSError):
                return self._json({"error": "Not found"}, 404)
            if review.group(2):
                if not run.get("report"):
                    return self._json({"error": "The review has not been recorded yet."}, 409)
                return self._send(200, run["report"].encode(), "text/markdown; charset=utf-8",
                                  {"Content-Disposition": 'attachment; filename="secondstay-agent-review.md"'})
            return self._json(run)
        history = re.fullmatch(r"/api/spaces/(\d+)/reviews", url.path)
        if history:
            from .agent import RUN_DIR, load_run
            if int(history.group(1)) not in self.buildings:
                return self._json({"error": "Not found"}, 404)
            runs = []
            for path in sorted(RUN_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    run = load_run(path.stem)
                except (ValueError, OSError):
                    continue
                if (run['building_id'] == int(history.group(1))
                        and run['space_id'] == (query.get('space') or [''])[0]
                        and (not query.get('scan') or run['scan_id'] == query['scan'][0])):
                    runs.append({k: run[k] for k in ('id', 'status', 'mode', 'started_at')})
            return self._json({"runs": runs[:20]})
        top_down = re.fullmatch(r"/api/scans/([A-Za-z0-9]{6,20})/plan\.jpg", url.path)
        if top_down:
            try:
                image = read_scan_plan(top_down.group(1))
            except Exception:
                image = None
            return self._send(200, image, "image/jpeg") if image else self._json({"error": "Not found"}, 404)
        sheet = re.fullmatch(r"/api/scans/([A-Za-z0-9]{6,20})/sheet\.jpg", url.path)
        if sheet:
            path = panoramas.SHEET_DIR / f"{sheet.group(1)}.jpg"
            if not path.exists():
                return self._json({"error": "Not found"}, 404)
            return self._send(200, path.read_bytes(), "image/jpeg")
        match = re.fullmatch(r"/api/spaces/(\d+)(/next-steps\.md|/aerial\.jpg|/surface\.json|/permit-years\.json)?", url.path)
        building = self.buildings.get(int(match.group(1))) if match else None
        if building is None:
            return self._json({"error": "Not found"}, 404)
        if match.group(2) == "/permit-years.json":
            return self._json(*permit_years(building))
        if match.group(2) == "/surface.json":
            try:
                return self._json(read_surface(building))
            except Exception:
                return self._json({"error": "The surface could not be read"}, 502)
        if match.group(2) == "/aerial.jpg":
            try:
                return self._send(200, read_image(building, context=query.get("context") == ["1"]), "image/jpeg")
            except Exception:
                return self._json({"error": "The image could not be read"}, 502)
        scan = (query.get("scan") or [""])[0]
        space = (query.get("space") or [""])[0]
        payload = space_payload(building, scan if MODEL_ID.match(scan) else "", space if space.isdigit() else "")
        if match.group(2):
            return self._send(
                200, next_steps_markdown(payload).encode(), "text/markdown; charset=utf-8",
                {"Content-Disposition": 'attachment; filename="secondstay-next-steps.md"'},
            )
        return self._json(payload)


_permit_years_cache: dict = {}


def permit_years(b: costar.Building) -> tuple:
    """(payload, status): permits per year on the parcel, from the Tiger Data continuous aggregate."""
    from . import tiger
    if b.property_id not in _permit_years_cache:
        try:
            years = tiger.permit_years(b.property_id)
        except tiger.NotConfigured as error:
            return {"error": str(error)}, 503
        except Exception:
            return {"error": "The permit store could not be read"}, 502
        _permit_years_cache[b.property_id] = {
            "years": years,
            "source": "LADBS permits matched by parcel number · Tiger Data continuous aggregate building_permits_yearly",
        }
    return _permit_years_cache[b.property_id], 200


def _warm_agent() -> None:
    """Import the agent libraries in the background; the first import takes tens of seconds."""
    try:
        import deepagents  # noqa: F401
        import langchain_openai  # noqa: F401
    except ImportError:
        pass  # the agent panel reports missing dependencies itself


def main(port: int = 8000) -> None:
    load_env()
    try:
        buildings = costar.published(costar.load_buildings())
    except FileNotFoundError as error:
        sys.exit(f"CoStar kit not found ({error.filename}). Set COSTAR_KIT_DIR in .env.")
    Handler.buildings = {b.property_id: b for b in buildings}
    # The list endpoint fills its cache on demand; a floor deep link need not wait for all buildings.
    print(f"SecondStay: {len(buildings)} Los Angeles office buildings · http://127.0.0.1:{port}")
    threading.Thread(target=_warm_agent, daemon=True).start()
    # Warm the slow landing data in the background: the building table first, then the per-building costs.
    threading.Thread(target=lambda: (cached_list(buildings), city_costs(buildings)), daemon=True).start()
    # HOST=0.0.0.0 in the container; locally only this machine can reach it.
    ThreadingHTTPServer((os.environ.get("HOST") or "127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PORT") or 8000))
