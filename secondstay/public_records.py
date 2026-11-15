"""Public records about each building, from city, county and state open data.

All of these are looked up by the building's CoStar location or parcel number:

| Record | Source | Matched by |
| --- | --- | --- |
| Zoning | City of LA Planning zoning map (ArcGIS) | point |
| Historic-Cultural Monuments, HPOZ, National and California registers | City of LA Planning layers | point |
| Measured building height | LA County building outlines (LARIAC 2023, City copy from 2008 as fallback) | point |
| Liquefaction zone | California Geological Survey | point |
| Alquist-Priolo fault zone | California Geological Survey | point |
| Non-ductile concrete retrofit list | LADBS on data.lacity.org | street address |
| Certificates of occupancy | LADBS on data.lacity.org | parcel number |

Cached under data/raw/public/, which is git-ignored. A layer that could not be read is
recorded as unread, never as "nothing found".
"""

import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from . import costar, permits

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "data" / "raw" / "public"
CITY = "https://services5.arcgis.com/7nsPwEMP38bSkCjy/ArcGIS/rest/services/{}/FeatureServer/{}"

LAYERS = {
    "zoning": "https://services5.arcgis.com/7nsPwEMP38bSkCjy/ArcGIS/rest/services/Zoning/FeatureServer/15",
    "hcm": CITY.format("Historic_Cultural_Monuments", 4),
    "hpoz": CITY.format("Historic_Preservation_Overlay_Zones", 5),
    "national_register": CITY.format("National_Register_of_Historic_Places", 63),
    "ca_register": CITY.format("California_State_Historic_Resources", 4),
    "county_2023": "https://public.gis.lacounty.gov/arcgis/rest/services/DRP/GISNET_Public/MapServer/434",
    "city_footprints": CITY.format("Building_Footprints", 0),
    "liquefaction": "https://services.gis.ca.gov/arcgis/rest/services/GeoscientificInformation/Liquefaction/MapServer/0",
    "fault_zone": "https://services2.arcgis.com/zr3KAIbsRSUyARHG/ArcGIS/rest/services/CGS_Alquist_Priolo_Fault_Zones/FeatureServer/0",
}
SOURCES = {
    "zoning": ("City of LA Planning zoning map", "https://planning.lacity.gov/zoning"),
    "historic": ("City of LA Planning historic resource layers", "https://planning.lacity.gov/preservation-design/historic-resources"),
    "height": ("LA County building outlines (LARIAC)", "https://egis-lacounty.hub.arcgis.com/"),
    "liquefaction": ("California Geological Survey liquefaction zones", "https://maps.conservation.ca.gov/cgs/EQZApp/app/"),
    "fault_zone": ("California Geological Survey Alquist-Priolo fault zones", "https://maps.conservation.ca.gov/cgs/EQZApp/app/"),
    "ndc": ("LADBS non-ductile concrete building list", "https://data.lacity.org/d/ke3z-xgni"),
    "cofo": ("LADBS certificates of occupancy", "https://data.lacity.org/d/3f9m-afei"),
}
NDC_DATASET, COFO_DATASET = "ke3z-xgni", "3f9m-afei"
NOT_SET = (None, "", " ", -9999)


def _get(url: str, params: dict):
    request = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers={"User-Agent": "secondstay-precheck"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read())


def at_point(layer: str, lat: float, lon: float) -> list:
    """Attributes of every feature of a layer that contains the point."""
    body = _get(LAYERS[layer] + "/query", {
        "f": "json", "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "outFields": "*", "returnGeometry": "false",
    })
    if body.get("error"):
        raise RuntimeError(body["error"].get("message") or "layer error")
    return [f.get("attributes") or {} for f in body.get("features") or []]


def _date(ms) -> Optional[str]:
    import datetime

    if not isinstance(ms, (int, float)) or ms in NOT_SET:
        return None
    return datetime.datetime.utcfromtimestamp(ms / 1000).date().isoformat()


def _clean(rows: list, keep: dict) -> list:
    return [{new: (r.get(old) if r.get(old) not in NOT_SET else None) for new, old in keep.items()} for r in rows]


def read_layers(b: costar.Building) -> dict:
    """Everything that is looked up by location, for one building."""
    out, unread = {}, []
    if b.latitude is None or b.longitude is None:
        return {"unread": list(LAYERS)}

    def one(name):
        try:
            return name, at_point(name, b.latitude, b.longitude)
        except Exception:
            return name, None

    with ThreadPoolExecutor(max_workers=len(LAYERS)) as pool:
        found = dict(pool.map(one, LAYERS))
    for name, rows in found.items():
        if rows is None:
            unread.append(name)
    z = found.get("zoning")
    out["zoning"] = None if z is None else _clean(z, {"zone": "Zoning", "category": "CATEGORY"})
    historic = []
    for name, kind in (("hcm", "Historic-Cultural Monument"), ("hpoz", "Historic Preservation Overlay Zone"),
                       ("national_register", "National Register of Historic Places"),
                       ("ca_register", "California Register of Historical Resources")):
        for r in found.get(name) or []:
            historic.append({
                "kind": kind, "name": r.get("NAME") or "", "number": r.get("MNT_NUM") or "",
                "status": r.get("STATUS") or "", "since": _date(r.get("DATE_ACTIVE")),
            })
    out["historic"] = None if all(found.get(n) is None for n in ("hcm", "hpoz", "national_register", "ca_register")) else historic
    heights = [r.get("HEIGHT") for r in found.get("county_2023") or [] if r.get("HEIGHT") not in NOT_SET]
    year = "2023"
    if not heights:
        heights = [r.get("HEIGHT") for r in found.get("city_footprints") or [] if r.get("HEIGHT") not in NOT_SET]
        year = next((r.get("LARIAC_DATE") for r in found.get("city_footprints") or [] if r.get("LARIAC_DATE")), "2008")
    out["county_height"] = {"feet": round(max(heights), 1), "year": str(year)} if heights else None
    out["liquefaction"] = None if found.get("liquefaction") is None else bool(found["liquefaction"])
    fz = found.get("fault_zone")
    out["fault_zone"] = None if fz is None else (
        {"quad": fz[0].get("QUAD_NAME"), "released": fz[0].get("ZN_RELEASED"), "map": fz[0].get("GEOPDFLINK")} if fz else False
    )
    out["unread"] = unread
    return out


def _socrata(dataset: str, where: str) -> list:
    return _get(f"https://data.lacity.org/resource/{dataset}.json", {"$where": where, "$limit": 50000})


def read_city_lists(buildings: list) -> dict:
    """Non-ductile concrete list (by address) and certificates of occupancy (by parcel), for all buildings."""
    kit = costar.kit_dir()
    wanted = {b.property_id for b in buildings}
    address = {}
    with open(kit / "data" / "commercial-property.jsonl", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            a = record.get("primaryAddress") or {}
            if record["id"] in wanted and a.get("streetNumber") and a.get("streetName"):
                address[record["id"]] = (str(a["streetNumber"]).split("-")[0], a["streetName"].upper().replace("'", ""))
    result = {pid: {"ndc": False, "cofo": []} for pid in wanted}
    names = sorted({name for _, name in address.values()})
    ndc_rows = []
    for i in range(0, len(names), 25):
        ndc_rows += _socrata(NDC_DATASET, " OR ".join(f"upper(address) like '%{n}%'" for n in names[i:i + 25]))
    for row in ndc_rows:
        text = (row.get("address") or "").upper()
        for pid, (number, name) in address.items():
            if re.match(rf"\s*{re.escape(number)}\b", text) and name in text:
                result[pid]["ndc"] = {
                    "address_on_list": row.get("address"),
                    "checklist": (row.get("checklist") or "")[:10] or None,
                    "plan_submittal": (row.get("plan_submittal") or "")[:10] or None,
                    "work_completion": (row.get("work_completion") or "")[:10] or None,
                    "retrofit_due": (row.get("step_3_due_date") or "")[:10] or None,
                }
    owner = {permits.apn_key(p): b.property_id for b in buildings for p in b.parcel_numbers if permits.apn_key(p)}
    keys = sorted(owner)
    for i in range(0, len(keys), 40):
        part = keys[i:i + 40]
        where = " OR ".join(
            f"(assessor_book='{k[:4]}' AND assessor_page='{k[4:7]}' AND assessor_parcel='{k[7:]}')" for k in part
        )
        for row in _socrata(COFO_DATASET, where):
            pid = owner.get(f"{row.get('assessor_book', '')}{row.get('assessor_page', '')}{row.get('assessor_parcel', '')}")
            if pid:
                result[pid]["cofo"].append({
                    "number": row.get("cofo_number"), "issued": (row.get("cofo_issue_date") or "")[:10],
                    "work": (row.get("work_description") or "").strip(), "stories": row.get("of_stories"),
                    "units": row.get("of_residential_dwelling_units"),
                })
    for value in result.values():
        value["cofo"].sort(key=lambda c: c["issued"] or "", reverse=True)
    return result


def fetch_all(buildings: list) -> None:
    """Read every source for every building and cache it. Run from prefetch."""
    lists = read_city_lists(buildings)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        for b, layers in zip(buildings, pool.map(read_layers, buildings)):
            record = {**layers, **lists.get(b.property_id, {"ndc": None, "cofo": None})}
            (CACHE_DIR / f"{b.property_id}.json").write_text(json.dumps(record))


def cached(property_id) -> Optional[dict]:
    path = CACHE_DIR / f"{property_id}.json"
    return json.loads(path.read_text()) if path.exists() else None
