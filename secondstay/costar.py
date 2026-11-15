"""Read the CoStar hackathon kit and turn Los Angeles buildings into facts.

The kit is not part of this repo. Point COSTAR_KIT_DIR at it, or leave it next
to the repo folder as ``../costar-hackathon-kit``. Real CoStar records, model
ids and addresses must never be committed: the cache this module writes goes
under ``data/raw/``, which is git-ignored.

Where the fields live (see docs/costar-data-notes.md):

- year built      constructionEvents[] with eventType 2 (ConstructionComplete)
- zone            zoningDescription (free text, normalised by ``base_zone``)
- stories         numStoriesAboveGrade
- height          buildingHeightInFeet (rarely filled)
- sprinklers      hasSprinklers / sprinklerType
- elevators       propertyOffice.structural.elevators[]
- scans           attachments[].videoKey where videoExternalReferenceType is 36 or 234
- location        primaryAddress.latitude / longitude, parcelNumbers
- available space commercial-listing-summary forLeaseSummary.spaces[]
- tenancies       location-occupancy spaces[].squareFeetOccupied where toDate is null
"""

import json
import os
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Optional

from .checklist import SpaceFacts

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = REPO_ROOT / "data" / "raw" / "costar_la.json"

LA_MARKET_ID = 20
PROPERTY_TYPES = {
    1: "Hospitality", 2: "Industrial", 3: "Land", 5: "Office", 6: "Retail", 7: "Flex",
    9: "Mixed use", 10: "Specialty", 11: "Multifamily", 13: "Healthcare",
}
OFFICE = 5
EXISTING = 1
CONSTRUCTION_COMPLETE = 2
MATTERPORT_REFERENCE_TYPES = (36, 234)
AERIAL_ATTACHMENT = 1
FLOOR_PLAN_ATTACHMENTS = (10, 12)  # FloorPlan, TypicalFloorPlan
PASSENGER_ELEVATOR = 1
SPRINKLER_TYPES = {1: "wet", 2: "dry", 3: "ESFR"}
ACTIVE_LISTING = 1
RATE_MONTHLY, RATE_YEARLY = 1, 2

# Los Angeles zone classes we recognise when reading CoStar's free-text zoning.
LA_ZONE_CLASSES = {
    "A1", "A2", "RA", "RE", "RS", "R1", "RU", "RZ", "RW1", "R2", "RD1.5", "RD2", "RD3", "RD4",
    "RD5", "RD6", "RMP", "RW2", "R3", "RAS3", "R4", "RAS4", "R5", "CR", "C1", "C1.5", "C2",
    "C4", "C5", "CM", "CW", "MR1", "M1", "MR2", "M2", "M3", "P", "PB", "PF", "OS", "LAX",
    "ADP", "HJ", "HR", "HI", "WC", "USC",
}


FLOOR_WORDS = {22: "Lobby", 23: "Ground", 26: "Mezzanine", 20: "Basement", 18: "Lower level", 150: "Penthouse"}
SPACE_USES = {1: "Office", 2: "Office/Medical", 3: "Office/Retail", 4: "Medical", 5: "Retail", 6: "Flex", 7: "Industrial"}


def floor_number(code) -> Optional[int]:
    """CoStar's FloorName code as a story number: 24 is the first floor, 25 the second, 27 the third."""
    if code in (22, 23, 24):
        return 1
    if code == 25:
        return 2
    if isinstance(code, int) and 27 <= code <= 149:
        return code - 24
    return None


def floor_label(code) -> str:
    number = floor_number(code)
    if code in FLOOR_WORDS:
        return FLOOR_WORDS[code]
    return f"Floor {number}" if number else "Floor not recorded"


def suite_key(text) -> str:
    """Suite numbers compared without spaces, case or a leading 'Suite'."""
    return re.sub(r"[^A-Z0-9]", "", re.sub(r"(?i)\b(suite|ste|unit)\b", "", str(text or "")).upper())


def scan_place(caption: str, stories: Optional[int]) -> tuple:
    """(suite, floor, how we know) read from a scan's caption."""
    suite = re.search(r"(?i)\b(?:suite|ste\.?|unit)\s*#?\s*([A-Za-z]?\d+[A-Za-z]?(?:-\d+)?)", caption or "")
    named = re.search(r"(?i)\b(\d{1,3})(?:st|nd|rd|th)\s+fl|\b(?:floor|level)\s+(\d{1,3})\b", caption or "")
    if named:
        return (suite.group(1) if suite else ""), int(named.group(1) or named.group(2)), "named in the scan's caption"
    if suite:
        digits = re.sub(r"\D", "", suite.group(1))
        floor = int(digits[:-2]) if len(digits) >= 3 else None
        if floor and (not stories or floor <= stories):
            return suite.group(1), floor, "read from the suite number"
        return suite.group(1), None, ""
    return "", None, ""


def base_zone(recorded: Optional[str]) -> Optional[str]:
    """Reduce CoStar's zoning text to a Los Angeles zone class, or None.

    "LAC2" -> "C2", "C2-1VL-O, Los Angeles" -> "C2", "[Q] M1-2D-SN" -> "M1".
    """
    if not recorded:
        return None
    text = recorded.upper()
    # New zoning code: [form-frontage-standards][use-density][overlays], with or without dots between
    new_code = re.search(r"\[([A-Z]{2}\d)-(FA|\d+)\]", text)
    if new_code:
        return f"{new_code.group(1)}-{new_code.group(2)}"
    plan_zone = re.match(r"\s*([A-Z]{2})\(([A-Z]{2,4})\)", text)  # specific plan zones such as MU(EC)
    if plan_zone:
        return f"{plan_zone.group(1)}({plan_zone.group(2)})"
    text = re.sub(r"[\[(][A-Z]+[\])]", " ", text)  # [Q], (T) qualifiers
    token = re.split(r"[,\s&/]+", text.strip())[0] if text.strip() else ""
    token = token.split("-")[0].rstrip("*")
    if token in LA_ZONE_CLASSES:
        return token
    if token.startswith("LA") and token[2:] in LA_ZONE_CLASSES:
        return token[2:]
    return None


@dataclass
class Scan:
    model_id: str
    caption: str = ""
    suite: str = ""
    floor: Optional[int] = None
    floor_basis: str = ""  # how the floor is known: a space on the market, the caption, the suite number


@dataclass
class Building:
    property_id: int
    name: str = ""
    address: str = ""
    property_type: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    parcel_numbers: list = field(default_factory=list)
    year_built: Optional[int] = None
    zone_recorded: Optional[str] = None
    stories: Optional[int] = None
    record_height_ft: Optional[float] = None
    has_sprinklers: Optional[bool] = None
    sprinkler_type: str = ""
    passenger_elevators: Optional[int] = None
    rentable_sqft: Optional[float] = None
    typical_floor_sqft: Optional[float] = None
    scans: list = field(default_factory=list)  # list[Scan]
    photo_url: str = ""
    aerial_urls: list = field(default_factory=list)
    # Architect's floor plans CoStar holds: {"url", "caption", "source"}; source is "building" or "space"
    floor_plans: list = field(default_factory=list)
    # Spaces on the market, one per suite: {"id", "suite", "floor", "floor_label", "sqft", "use",
    # "rent_per_sqft_year", "plan_url", "full_floor", "available_on", "scans": [model ids]}
    spaces: list = field(default_factory=list)
    # Floors on record: {"id", "floor", "label", "sqft", "occupied_sqft", "tenancies"}; occupancy is
    # summed from current tenancies whose space names that floor
    floors: list = field(default_factory=list)
    # Leasing picture. "Available" is marketed space, which is not the same as vacant.
    available_sqft: float = 0.0
    available_spaces: int = 0
    asking_rent_per_sqft_year: Optional[float] = None
    occupied_sqft: float = 0.0
    current_tenancies: int = 0

    @property
    def zone(self) -> Optional[str]:
        return base_zone(self.zone_recorded)

    @property
    def unaccounted_share(self) -> Optional[float]:
        """Share of rentable area with no current tenancy on record (0-1).

        An indication of vacancy only: tenancy areas are missing for some tenants.
        """
        if not self.rentable_sqft:
            return None
        return max(0.0, min(1.0, 1 - self.occupied_sqft / self.rentable_sqft))


def kit_dir() -> Path:
    return Path(os.environ.get("COSTAR_KIT_DIR") or REPO_ROOT.parent / "costar-hackathon-kit")


def _jsonl(path: Path):
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _address(addr: dict) -> str:
    parts = [addr.get(k) for k in ("streetNumber", "streetDirection", "streetName", "streetType")]
    return " ".join(str(p) for p in parts if p)


def _year_built(record: dict) -> Optional[int]:
    years = [
        e["year"] for e in record.get("constructionEvents") or []
        if e.get("eventType") == CONSTRUCTION_COMPLETE and e.get("year")
    ]
    return min(years) if years else None


def _passenger_elevators(record: dict) -> Optional[int]:
    for block in ("propertyOffice", "propertyRetail", "propertyIndustrial", "propertyFlex"):
        structural = (record.get(block) or {}).get("structural") or {}
        counts = [
            e.get("numElevators") for e in structural.get("elevators") or []
            if e.get("elevatorType") == PASSENGER_ELEVATOR and e.get("numElevators")
        ]
        if counts:
            return sum(counts)
    return None


def _building(record: dict) -> Building:
    addr = record.get("primaryAddress") or {}
    attachments = record.get("attachments") or []
    seen, scans = set(), []
    for a in attachments:
        key = a.get("videoKey")
        if a.get("videoExternalReferenceType") in MATTERPORT_REFERENCE_TYPES and key and key not in seen:
            seen.add(key)
            scans.append(Scan(key, a.get("caption") or ""))
    stories = record.get("numStoriesAboveGrade") or None
    for scan in scans:
        scan.suite, scan.floor, scan.floor_basis = scan_place(scan.caption, stories)
    floors = sorted(
        (
            {"id": f.get("propertyFloorId"), "floor": floor_number(f.get("floorName")), "label": floor_label(f.get("floorName")),
             "sqft": (f.get("floorSize") or {}).get("squareFeet"), "occupied_sqft": 0.0, "tenancies": 0}
            for f in record.get("floors") or []
        ),
        key=lambda f: (f["floor"] is None, f["floor"] or 0),
    )
    return Building(
        floors=floors,
        property_id=record["id"],
        name=record.get("buildingName") or "",
        address=_address(addr),
        property_type=PROPERTY_TYPES.get(record.get("propertyType"), "Other"),
        latitude=addr.get("latitude"),
        longitude=addr.get("longitude"),
        parcel_numbers=record.get("parcelNumbers") or [],
        year_built=_year_built(record),
        zone_recorded=record.get("zoningDescription") or None,
        stories=record.get("numStoriesAboveGrade") or None,
        record_height_ft=record.get("buildingHeightInFeet") or None,
        has_sprinklers=record.get("hasSprinklers"),
        sprinkler_type=SPRINKLER_TYPES.get(record.get("sprinklerType"), ""),
        passenger_elevators=_passenger_elevators(record),
        rentable_sqft=record.get("rentableBuildingAreaSquareFeet") or None,
        typical_floor_sqft=record.get("grossTypicalFloorSquareFeet") or None,
        scans=scans,
        photo_url=(record.get("primaryPhoto") or {}).get("attachmentUri") or "",
        aerial_urls=[
            a["attachmentUri"] for a in attachments
            if a.get("attachmentType") == AERIAL_ATTACHMENT and a.get("attachmentUri")
        ][:4],
        floor_plans=[
            {"url": a["attachmentUri"], "caption": a.get("caption") or "Floor plan", "source": "building"}
            for a in attachments
            if a.get("attachmentType") in FLOOR_PLAN_ATTACHMENTS and a.get("attachmentUri")
        ],
    )


def _add_listings(buildings: dict, kit: Path) -> None:
    rent_area: dict = {}
    rent_total: dict = {}
    for listing in _jsonl(kit / "data" / "commercial-listing-summary.jsonl"):
        lease = listing.get("forLeaseSummary")
        if not lease or listing.get("listingStatus") != ACTIVE_LISTING:
            continue
        for space in lease.get("spaces") or []:
            b = buildings.get(space.get("propertyId") or listing.get("propertyId"))
            plan = (space.get("floorPlan") or {}).get("attachmentUri")
            if b is not None and plan and all(p["url"] != plan for p in b.floor_plans):
                where = " ".join(
                    part for part in (
                        f"Suite {space['suite']}" if space.get("suite") else "",
                        f"floor {space['floorName']}" if space.get("floorName") else "",
                    ) if part
                )
                b.floor_plans.append({"url": plan, "caption": where or "Space for lease", "source": "space"})
            if b is None or space.get("dateOffMarket"):
                continue
            area = space.get("squareFeetMax") or space.get("squareFeetMin") or 0
            code = space.get("floorName")
            rate = space.get("rateHigh") or space.get("rateLow") or 0
            yearly = rate * 12 if space.get("rateBasis") == RATE_MONTHLY else rate
            b.spaces.append({
                "id": space.get("id"), "suite": space.get("suite") or "", "floor": floor_number(code),
                "floor_label": floor_label(code), "sqft": area or None,
                "use": SPACE_USES.get(space.get("spaceUse"), ""),
                "rent_per_sqft_year": round(yearly, 2) if rate and space.get("rateBasis") in (RATE_MONTHLY, RATE_YEARLY) else None,
                "plan_url": plan or "", "full_floor": bool(space.get("isFullFloor")),
                "available_on": (space.get("availableOnDate") or "")[:10], "scans": [],
            })
            b.available_sqft += area
            b.available_spaces += 1
            rate = space.get("rateHigh") or space.get("rateLow") or 0
            if rate and area and space.get("rateBasis") in (RATE_MONTHLY, RATE_YEARLY):
                yearly = rate * 12 if space["rateBasis"] == RATE_MONTHLY else rate
                rent_area[b.property_id] = rent_area.get(b.property_id, 0) + area
                rent_total[b.property_id] = rent_total.get(b.property_id, 0) + yearly * area
    for pid, area in rent_area.items():
        # Area-weighted asking rent. Service types are mixed, so this is indicative only.
        buildings[pid].asking_rent_per_sqft_year = round(rent_total[pid] / area, 2)


def _link_scans(buildings: dict) -> None:
    """Tie each scan to the space it shows: same suite number first, else the same floor."""
    for b in buildings.values():
        b.spaces.sort(key=lambda s: (-(s["floor"] or 0), s["suite"]))
        by_suite = {suite_key(s["suite"]): s for s in b.spaces if s["suite"]}
        for scan in b.scans:
            space = by_suite.get(suite_key(scan.suite)) if scan.suite else None
            if space:
                space["scans"].append(scan.model_id)
                if space["floor"]:
                    scan.floor, scan.floor_basis = space["floor"], "the floor of that suite in the listing"


def _add_occupancy(buildings: dict, kit: Path) -> None:
    for tenancy in _jsonl(kit / "data" / "location-occupancy.jsonl"):
        b = buildings.get(tenancy.get("propertyId"))
        if b is None or tenancy.get("toDate"):
            continue
        b.current_tenancies += 1
        b.occupied_sqft += sum(s.get("squareFeetOccupied") or 0 for s in tenancy.get("spaces") or [])
        by_id = {f["id"]: f for f in b.floors if f.get("id")}
        for space in tenancy.get("spaces") or []:
            floor = by_id.get(space.get("propertyFloorId"))
            if floor:
                floor["tenancies"] += 1
                floor["occupied_sqft"] += space.get("squareFeetOccupied") or 0


def load_buildings(property_types=(OFFICE,), use_cache: bool = True) -> list:
    """Existing Los Angeles buildings of the given types that have at least one scan."""
    if use_cache and CACHE_PATH.exists():
        raw = json.loads(CACHE_PATH.read_text())
        if raw.get("property_types") == list(property_types):
            return [
                Building(**{**b, "scans": [Scan(**s) for s in b["scans"]]}) for b in raw["buildings"]
            ]
    kit = kit_dir()
    buildings = {}
    for record in _jsonl(kit / "data" / "commercial-property.jsonl"):
        addr = record.get("primaryAddress") or {}
        if (
            addr.get("researchMarketId") == LA_MARKET_ID
            and record.get("propertyType") in property_types
            and record.get("constructionStatus") == EXISTING
        ):
            b = _building(record)
            if b.scans:
                buildings[b.property_id] = b
    _add_listings(buildings, kit)
    _link_scans(buildings)
    _add_occupancy(buildings, kit)
    result = sorted(buildings.values(), key=lambda b: (-b.available_sqft, b.property_id))
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps({"property_types": list(property_types), "buildings": [asdict(b) for b in result]})
    )
    return result


def to_facts(b: Building, scan: Optional[SpaceFacts] = None) -> SpaceFacts:
    """Fill the CoStar part of SpaceFacts, keeping any Matterport facts already read."""
    facts = scan or SpaceFacts()
    facts.name = b.name or b.address or facts.name
    facts.year_built = b.year_built
    facts.zone = b.zone
    facts.zone_recorded = b.zone_recorded
    facts.stories = b.stories
    facts.record_height_ft = b.record_height_ft
    facts.has_sprinklers = b.has_sprinklers
    facts.sprinkler_type = b.sprinkler_type
    facts.passenger_elevators = b.passenger_elevators
    facts.building_sqft = b.rentable_sqft
    facts.typical_floor_sqft = b.typical_floor_sqft
    return facts


def published(buildings: list) -> list:
    """Only spaces the owner published a plan or a 3D tour for, and only buildings left with one.

    A listing with neither is read as not offered for this review.
    """
    kept = []
    for b in buildings:
        spaces = [s for s in b.spaces if s["plan_url"] or s["scans"]]
        if spaces:
            kept.append(replace(b, spaces=spaces, available_spaces=len(spaces),
                                available_sqft=sum(s["sqft"] or 0 for s in spaces)))
    return kept
