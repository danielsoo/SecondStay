"""Read one scan from the Matterport Model API and turn it into facts.

Credentials come from the environment (.env, never committed):
MATTERPORT_TOKEN_ID and MATTERPORT_TOKEN_SECRET.
"""

import base64
import json
import os
import urllib.request

from .checklist import RoomFact, SpaceFacts

API_URL = os.environ.get("MATTERPORT_API_URL") or "https://api.matterport.com/api/models/graph"

MODEL_QUERY = """
query($id: ID!) {
  model(id: $id) {
    id
    name
    geocoordinates { latitude longitude }
    propertyClassifications { classification }
    floors { id label dimensionEstimates(units: imperial) { area } }
    rooms {
      id
      floor { id label }
      classifications { label confidence }
      dimensionEstimates(units: imperial) { area width depth height }
    }
  }
}
"""


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


def to_facts(model: dict) -> SpaceFacts:
    """Fill in the Matterport part of SpaceFacts. CoStar and Vexcel fields stay empty."""
    rooms = []
    for room in model.get("rooms") or []:
        classes = room.get("classifications") or []
        kind = max(classes, key=lambda c: c.get("confidence") or 0)["label"] if classes else ""
        rooms.append(
            RoomFact(
                floor=(room.get("floor") or {}).get("label") or "",
                kind=kind,
                area_sqft=(room.get("dimensionEstimates") or {}).get("area"),
            )
        )
    floor_areas = [
        (floor.get("dimensionEstimates") or {}).get("area") or 0.0
        for floor in model.get("floors") or []
    ]
    return SpaceFacts(name=model.get("name") or "", floor_areas_sqft=floor_areas, rooms=rooms)
