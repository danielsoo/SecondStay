"""Read one scan from the Matterport Model API and turn it into facts.

Credentials come from the environment (.env, never committed):
MATTERPORT_TOKEN_ID and MATTERPORT_TOKEN_SECRET.
"""

import base64
import json
import os
import urllib.request
from typing import Optional

from .checklist import RoomFact, SpaceFacts

API_URL = os.environ.get("MATTERPORT_API_URL") or "https://api.matterport.com/api/models/graph"

MODEL_QUERY = """
query($id: ID!) {
  model(id: $id) {
    id
    name
    geocoordinates { latitude longitude }
    propertyClassifications { classification }
    floors { id label sequence dimensionEstimates(units: imperial) { area } }
    rooms {
      id
      label
      tags
      keywords
      floor { id label }
      classifications { label confidence }
      dimensionEstimates(units: imperial) { area width depth height }
      boundary { edges { id type vertices { position { x y } } openings { id type width height lowerElevation relativeCenter } } }
    }
    locations { id floor { id label } position { x y z } neighbors }
  }
}
"""

# Room tags that say nothing about what the room is.
GENERIC_TAGS = {"indoor", "unfurnished", "furnished", "other", "nonArea", "hide", "outdoor_other", "house"}
STAIR_CLUSTER_M = 6.0  # links between floors closer than this are taken as one stair


def _post(query: str, variables: dict) -> dict:
    token_id = os.environ.get("MATTERPORT_TOKEN_ID", "placeholder")
    secret = os.environ.get("MATTERPORT_TOKEN_SECRET", "placeholder")
    auth = base64.b64encode(f"{token_id}:{secret}".encode()).decode()
    request = urllib.request.Request(
        API_URL,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        body = json.loads(response.read())
    if body.get("errors"):
        raise RuntimeError(f"Matterport API error: {body['errors'][0].get('message')}")
    return body["data"]


def fetch_model(model_id: str) -> dict:
    return _post(MODEL_QUERY, {"id": model_id})["model"]


def room_kind(room: dict) -> str:
    """The room type: the classifier's label when there is one, else Matterport's room tags."""
    classes = room.get("classifications") or []
    if classes:
        label = max(classes, key=lambda c: c.get("confidence") or 0)["label"]
        if label not in ("Void", "Other", ""):
            return label
    for tag in (room.get("tags") or []) + (room.get("keywords") or []):
        if tag not in GENERIC_TAGS:
            return tag[:1].upper() + tag[1:]
    return classes[0]["label"] if classes else ""


def room_windows(room: dict):
    """Windows on the room's walls, or None when the scan has no wall geometry for it."""
    edges = (room.get("boundary") or {}).get("edges") or []
    if not edges:
        return None
    return sum(1 for e in edges for o in e.get("openings") or [] if o.get("type") == "window")


def stair_links(model: dict) -> dict:
    """Floor label -> number of places where the scan path steps to another floor.

    Each scan position lists its neighbours. A pair of neighbours on different floors is where
    the person scanning walked between floors, which is a stair. Nearby pairs count as one.
    """
    places = {p["id"]: p for p in model.get("locations") or [] if p.get("floor") and p.get("position")}
    found: dict = {}
    for place in places.values():
        for other_id in place.get("neighbors") or []:
            other = places.get(other_id)
            if other is None or other["floor"]["id"] == place["floor"]["id"]:
                continue
            label = place["floor"].get("label") or ""
            x, y = place["position"]["x"], place["position"]["y"]
            spots = found.setdefault(label, [])
            if not any(((x - sx) ** 2 + (y - sy) ** 2) ** 0.5 < STAIR_CLUSTER_M for sx, sy in spots):
                spots.append((x, y))
    return {label: len(spots) for label, spots in found.items()}


PLAN_QUERY = """
query($id: ID!) {
  model(id: $id) { assets { floorplans(formats: ["jpg"], flags: [photogramy]) { flags url floor { label } } } }
}
"""


def plan_lines(model: dict) -> dict:
    """Walls, windows and doors of a scan as line segments in metres, by floor label.

    Each wall is drawn once even when two rooms share it. An opening sits on its wall at
    ``relativeCenter`` (0 to 1 along the wall) and is ``width`` metres long.
    """
    floors: dict = {}
    seen = set()
    for room in model.get("rooms") or []:
        label = (room.get("floor") or {}).get("label") or ""
        for edge in (room.get("boundary") or {}).get("edges") or []:
            points = [v.get("position") for v in edge.get("vertices") or []]
            if edge.get("id") in seen or len(points) != 2 or not all(points):
                continue
            seen.add(edge.get("id"))
            (x1, y1), (x2, y2) = ((p["x"], p["y"]) for p in points)
            length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            lines = floors.setdefault(label, {"walls": [], "windows": [], "doors": []})
            if edge.get("type") == "wall":
                lines["walls"].append([x1, y1, x2, y2])
            for opening in edge.get("openings") or []:
                kind = {"window": "windows", "doorway": "doors"}.get(opening.get("type"))
                centre, width = opening.get("relativeCenter"), opening.get("width")
                if not kind or centre is None or not width or not length:
                    continue
                half = min(0.5, width / length / 2)
                a, c = max(0.0, centre - half), min(1.0, centre + half)
                lines[kind].append([x1 + (x2 - x1) * a, y1 + (y2 - y1) * a, x1 + (x2 - x1) * c, y1 + (y2 - y1) * c])
    return floors


def fetch_plan_image(model_id: str) -> Optional[bytes]:
    """Matterport's top-down picture of the scan's first floor, as JPEG bytes."""
    plans = _post(PLAN_QUERY, {"id": model_id})["model"]["assets"]["floorplans"] or []
    plain = [p for p in plans if p.get("flags") == ["photogramy"] and p.get("url")]
    if not plain:
        return None
    with urllib.request.urlopen(plain[0]["url"], timeout=90) as response:
        return response.read()


def scan_rank(facts: SpaceFacts) -> tuple:
    """How much evidence a scan carries, for choosing which of a building's scans to show."""
    from .checklist import stairs_by_floor, window_share

    return (
        any(stairs_by_floor(facts).values()),
        window_share(facts) is not None,
        any(r.kind not in ("", "Void", "Other") for r in facts.rooms),
        sum(a for a in facts.floor_areas_sqft if a),
    )


def to_facts(model: dict) -> SpaceFacts:
    """Fill in the Matterport part of SpaceFacts. CoStar and Vexcel fields stay empty."""
    rooms = []
    for room in model.get("rooms") or []:
        rooms.append(
            RoomFact(
                floor=(room.get("floor") or {}).get("label") or "",
                kind=room_kind(room),
                area_sqft=(room.get("dimensionEstimates") or {}).get("area"),
                windows=room_windows(room),
            )
        )
    floor_areas = [
        (floor.get("dimensionEstimates") or {}).get("area") or 0.0
        for floor in model.get("floors") or []
    ]
    return SpaceFacts(
        name=model.get("name") or "", floor_areas_sqft=floor_areas, rooms=rooms,
        stair_links=stair_links(model),
    )
