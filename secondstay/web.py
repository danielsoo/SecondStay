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
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import costar, matterport, panoramas, streets, vexcel
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
        if fetch and outside.neighbors and not outside.neighbor_heights_ft and vexcel.configured():
            try:  # caches written before the 3D view have no neighbour heights
                cached.write_text(vexcel.dump(vexcel.add_neighbor_heights(outside)))
            except Exception:
                pass
        return outside
    if b.latitude is None or b.longitude is None:
        return vexcel.Outside(error="The record has no location, so imagery could not be looked up.")
    if not vexcel.configured():
        return vexcel.Outside(error="The Vexcel key is not set in .env, so nothing has been measured from the air.")
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


def read_image(b: costar.Building) -> bytes:
    cached = OUTSIDE_CACHE / f"{b.property_id}.z{vexcel.IMAGE_ZOOM}.jpg"
    if cached.exists():
        return cached.read_bytes()
    image = vexcel.fetch_image(read_outside(b).bbox)
    OUTSIDE_CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(image)
    return image


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


def building_card(b: costar.Building) -> dict:
    card = asdict(b)
    card["zone"] = b.zone
    card["unaccounted_share"] = b.unaccounted_share
    return card


def space_payload(b: costar.Building, model_id: str = "", space_id: str = "") -> dict:
    """Everything the screen shows for one building, for one suite on the market when one is chosen."""
    space = next((s for s in b.spaces if str(s["id"]) == str(space_id)), None)
    scan_ids = [s.model_id for s in b.scans]
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
    rows = build_checklist(facts, year)
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
        "scan": scan,
        "sdk_key": os.environ.get("MATTERPORT_SDK_KEY", ""),
        "outside": {**asdict(outside), "loaded": outside.loaded},
        "plan": {
            "image": image, "reading": reading, "count": len(b.floor_plans),
            "reading_from": stand_in if reading and (not image or image["url"] != stand_in["url"]) else None,
        },
        "top_occupied_ft": top_occupied_ft(facts),
        "streets": [asdict(s) | {"public": s.public} for s in found],
        "changes": to_dicts(changes),
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
    if not matterport_configured():
        return None
    image = matterport.fetch_plan_image(model_id)
    if image:
        SCAN_CACHE.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(image)
    return image


PLAN_READING_DIR = REPO_ROOT / "data" / "raw" / "plan_readings"


def plan_to_read(b: costar.Building):
    """The floor plan that stands for the building: a whole-floor plan if CoStar has one, else a suite plan."""
    whole = [p for p in b.floor_plans if p["source"] == "building"]
    return (whole or b.floor_plans or [None])[0]


def plan_reading(b: costar.Building):
    """What was read from that plan, or None. Stored under data/raw/, which is git-ignored."""
    path = PLAN_READING_DIR / f"{b.property_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return data if isinstance(data.get("stairs"), int) else None


PLANS_IN_LIST = True  # the plan gallery reads them from the list


def list_payload(buildings: list) -> dict:
    year = datetime.date.today().year
    spaces = []
    for b in buildings:
        card = building_card(b)
        card["scans"] = len(b.scans)
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
        card["counts"] = summary(build_checklist(facts, year))
        spaces.append(card)
    return {"notice": NOTICE, "states": STATES, "spaces": spaces}


_list_cache = {"at": 0.0, "data": None}


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

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if url.path == "/api/spaces":
            return self._json(cached_list(list(self.buildings.values())))
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
        match = re.fullmatch(r"/api/spaces/(\d+)(/next-steps\.md|/aerial\.jpg)?", url.path)
        building = self.buildings.get(int(match.group(1))) if match else None
        if building is None:
            return self._json({"error": "Not found"}, 404)
        if match.group(2) == "/aerial.jpg":
            try:
                return self._send(200, read_image(building), "image/jpeg")
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


def main(port: int = 8000) -> None:
    load_env()
    try:
        buildings = costar.load_buildings()
    except FileNotFoundError as error:
        sys.exit(f"CoStar kit not found ({error.filename}). Set COSTAR_KIT_DIR in .env.")
    Handler.buildings = {b.property_id: b for b in buildings}
    cached_list(buildings)  # build the list once before the first visitor arrives
    print(f"SecondStay: {len(buildings)} Los Angeles office buildings · http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PORT") or 8000))
