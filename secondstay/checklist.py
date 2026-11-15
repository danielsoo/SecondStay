"""Requirement-by-requirement evidence review for one space.

This module never states a conclusion about whether a conversion is allowed.
Each row reports what the published rule says, what the data shows, one of
four evidence states, and who confirms it. See PRD.md, "Wording rules".
"""

import re
from dataclasses import dataclass, field
from typing import Optional

FOUND = "Evidence found"
ISSUE = "Possible issue"
NO_DATA = "Not enough data"
REVIEW = "Needs professional review"
STATES = (FOUND, ISSUE, NO_DATA, REVIEW)

NOTICE = (
    "This is a preliminary evidence review, not a legal or code determination. "
    "Final decisions are made by LADBS and licensed professionals."
)

ARO_URL = "https://planning.lacity.gov/project-review/adaptive-reuse"
BULLETIN_URL = (
    "https://dbs.lacity.gov/sites/default/files/efs/forms_and_publications/publications/"
    "information-bulletins/building-code/2026/IB-BC-2026-164-Change_Occupancy_Office_Residential.pdf"
)
HOME_SHARING_URL = "https://planning.lacity.gov/ordinances/docs/HomeSharing/FAQ.pdf"

# Zones named on the City Planning adaptive reuse page.
ARO_ZONES = {
    "R2", "RD1.5", "RD2", "RD3", "RD4", "RD5", "RD6", "RW2", "R3", "RAS3", "R4", "RAS4",
    "R5", "CR", "C1", "C1.5", "C4", "C2", "C5", "CM", "P", "PB", "PF",
}

HIGH_RISE_FT = 75.0
DIRECT_AGE_YEARS = 15
MIN_AGE_YEARS = 5
STORY_FT_RANGE = (8.0, 25.0)  # outside this, imagery height and stories on record do not fit together
TYPICAL_STORY_FT = 10.0  # our assumption for reading stories as height, not a rule


@dataclass
class RoomFact:
    floor: str
    kind: str  # Matterport room classification, e.g. "Office", "Staircase", "Bathroom"
    area_sqft: Optional[float] = None
    windows: Optional[int] = None  # windows on the room's walls; None when the scan has no wall geometry


@dataclass
class SpaceFacts:
    """Everything we know about one space, from all three layers."""

    name: str = ""
    # CoStar
    year_built: Optional[int] = None
    zone: Optional[str] = None  # Los Angeles zone class, e.g. "C2"
    zone_recorded: Optional[str] = None  # zoning text as CoStar holds it, e.g. "LAC2-1VL"
    stories: Optional[int] = None
    record_height_ft: Optional[float] = None
    has_sprinklers: Optional[bool] = None
    sprinkler_type: str = ""
    passenger_elevators: Optional[int] = None
    building_sqft: Optional[float] = None  # rentable building area
    typical_floor_sqft: Optional[float] = None
    # Matterport
    floor_areas_sqft: list = field(default_factory=list)
    rooms: list = field(default_factory=list)  # list[RoomFact]
    stair_links: dict = field(default_factory=dict)  # floor label -> places the scan path changes floor
    # What a vision model read from a sheet of the scan's panoramas, when the scan has no geometry:
    # {"panoramas", "with_windows", "stairs", "exit_doors", "indoor", "space", "notes"}
    pano_reading: Optional[dict] = None
    # What was read from an architect's floor plan CoStar holds for the building:
    # {"stairs", "elevators", "covers": "floor" | "part" | "suite" | "diagram", "notes"}
    plan_reading: Optional[dict] = None
    # Vexcel
    height_ft: Optional[float] = None
    neighbor_gap_ft: Optional[float] = None
    street_frontage: Optional[bool] = None  # False when streets were read and none is public
    street_name: Optional[str] = None
    street_distance_ft: Optional[float] = None  # footprint to the closest public street
    # Product settings
    min_stay_days: int = 31
    planning_unit_sqft: float = 500.0  # our planning assumption, not a rule
    # The space being looked at, when one suite on the market is selected
    space_label: str = ""
    space_sqft: Optional[float] = None


@dataclass
class Row:
    key: str
    requirement: str
    rule: str
    source_url: Optional[str]
    state: str
    evidence: str
    layer: str
    confirmed_by: str


def _has_room_types(facts: SpaceFacts) -> bool:
    return any(r.kind not in ("Void", "Other", "") for r in facts.rooms)


def _age(f: SpaceFacts, year: int) -> Row:
    rule = (
        "Buildings at least 15 years old qualify directly. Buildings at least 5 but under 15 years old "
        "need Zoning Administrator approval (a Class 1 Conditional Use Permit)."
    )
    if f.year_built is None:
        state, ev = NO_DATA, "No year built on record."
    else:
        age = year - f.year_built
        ev = f"Year built on record: {f.year_built} ({age} years)."
        if age >= 15:
            state = FOUND
        elif age >= MIN_AGE_YEARS:
            state = ISSUE
            ev += " This is under the 15-year threshold, so Zoning Administrator approval would be needed."
        else:
            state = ISSUE
            ev += " This is under the 5-year minimum the city describes for any adaptive reuse path."
    return Row("age", "Building age", rule, ARO_URL, state, ev, "CoStar", "LADBS building records")


NEW_CODE_ZONE = re.compile(r"^([A-Z]+)(\d*)-([A-Z0-9]+)$")  # use district, then density district
STREET_REACH_FT = 150.0  # our working distance for "fronts a public street", not a rule we have read


def _zone(f: SpaceFacts) -> Row:
    rule = (
        "The ordinance names Multifamily Residential, Commercial, Parking and Public Facilities zones. "
        "Under the city's new zoning code it covers Commercial-Mixed use districts and any lot in "
        "density district 2 or FA."
    )
    shown = f.zone or ""
    if f.zone_recorded and f.zone_recorded != f.zone:
        shown += f' (recorded as "{f.zone_recorded}")'
    new_code = NEW_CODE_ZONE.match(f.zone or "")
    if not f.zone and f.zone_recorded:
        state = NO_DATA
        ev = f'Zoning on record is "{f.zone_recorded}", which we could not match to a Los Angeles zone class.'
    elif not f.zone:
        state, ev = NO_DATA, "No zoning value on record."
    elif new_code:
        use, density = new_code.group(1) + new_code.group(2), new_code.group(3)
        ev = f"Zoning on record uses the new zoning code: use district {use}, density district {density}."
        if density in ("2", "FA") or new_code.group(1) == "CX":
            state = FOUND
            ev += " That is among the districts the city lists for the new code."
        else:
            state = ISSUE
            ev += " That is not among the districts the city lists for the new code."
    elif f.zone.upper() in ARO_ZONES:
        state, ev = FOUND, f"Zone on record: {shown}, which is among the zones the city lists."
    else:
        state, ev = ISSUE, f"Zone on record: {shown}, which is not among the zones the city lists."
    return Row("zone", "Zone", rule, ARO_URL, state, ev, "CoStar", "City zoning lookup (ZIMAS)")


def _units(f: SpaceFacts) -> Row:
    rule = "The ordinance covers conversions that create five or more residential units."
    area = sum(a for a in f.floor_areas_sqft if a)
    if area <= 0 and f.space_sqft:
        units = int(f.space_sqft * 0.8 / f.planning_unit_sqft)
        ev = (
            f"{f.space_label or 'The space'} is listed at {f.space_sqft:,.0f} sq ft. At our planning assumption "
            f"of {f.planning_unit_sqft:.0f} sq ft per unit and 80% usable area, that is about {units} units."
        )
        if units < 5:
            ev += " The ordinance covers projects of five or more units, so this space would be part of a larger conversion."
        return Row("units", "Unit count", rule, ARO_URL, FOUND if units >= 5 else ISSUE, ev, "CoStar listing", "Architect's layout")
    if area <= 0 and f.building_sqft:
        whole = int(f.building_sqft * 0.8 / f.planning_unit_sqft)
        ev = (
            f"No floor area is measured in the scan. On the {f.building_sqft:,.0f} sq ft of rentable area on "
            f"record, at our planning assumption of {f.planning_unit_sqft:.0f} sq ft per unit and 80% usable "
            f"area, that is about {whole} units."
        )
        state = FOUND if whole >= 5 else ISSUE
        return Row("units", "Unit count", rule, ARO_URL, state, ev, "CoStar", "Architect's layout")
    if area <= 0:
        state, ev = NO_DATA, "No floor area measured in the scan, and no building area on record."
    else:
        units = int(area * 0.8 / f.planning_unit_sqft)
        ev = (
            f"Scan measures about {area:,.0f} sq ft. At our planning assumption of "
            f"{f.planning_unit_sqft:.0f} sq ft per unit and 80% usable area, that is about {units} units."
        )
        whole = int(f.building_sqft * 0.8 / f.planning_unit_sqft) if f.building_sqft else None
        if units >= 5:
            state = FOUND
        elif whole is not None and whole >= 5:
            # The scan covers one suite or floor. The building as a whole is what gets converted.
            state = FOUND
            ev += (
                f" The scan covers only part of the building: on the {f.building_sqft:,.0f} sq ft of "
                f"rentable area on record, the same assumption gives about {whole} units."
            )
        elif whole is None:
            state = NO_DATA
            ev += " The scan covers too small an area to tell, and no building area is on record."
        else:
            state = ISSUE
    return Row("units", "Unit count", rule, ARO_URL, state, ev, "Matterport, CoStar", "Architect's layout")


def top_occupied_ft(f: SpaceFacts) -> Optional[float]:
    """Rough height of the highest occupied floor, which is what the high-rise rule measures.

    Roof height from imagery includes the top story and rooftop equipment, so the top
    floor level is taken as the roof height less one story. This is our estimate.
    """
    roof = f.height_ft if f.height_ft is not None else f.record_height_ft
    if roof is not None and f.stories:
        return roof * (f.stories - 1) / f.stories
    if roof is not None:
        return max(0.0, roof - TYPICAL_STORY_FT)
    if f.stories:
        return (f.stories - 1) * TYPICAL_STORY_FT
    return None


def _height(f: SpaceFacts) -> Row:
    rule = (
        "High-rise provisions (smokeproof stair enclosures, fire pumps, emergency power, fire command "
        "center) apply where the highest occupied level is more than 75 feet above fire department access."
    )
    stories = f" Stories on record: {f.stories}." if f.stories is not None else ""
    top = top_occupied_ft(f)
    if f.height_ft is not None and f.record_height_ft is not None and (
        (f.height_ft < HIGH_RISE_FT) != (f.record_height_ft < HIGH_RISE_FT)
    ):
        state = ISSUE
        ev = (
            f"The two sources disagree. Height seen in aerial imagery: about {f.height_ft:.0f} ft. "
            f"Height on record: {f.record_height_ft:.0f} ft.{stories}"
        )
    elif f.height_ft is not None or f.record_height_ft is not None:
        if f.height_ft is not None:
            ev = f"Height seen in aerial imagery: about {f.height_ft:.0f} ft to the highest roof point."
        else:
            ev = f"Height on record: {f.record_height_ft:.0f} ft."
        ev += stories
        per_story = f.height_ft / f.stories if f.height_ft is not None and f.stories else None
        if per_story is not None and not STORY_FT_RANGE[0] <= per_story <= STORY_FT_RANGE[1]:
            state = ISSUE
            ev += (
                f" The two sources do not fit together: that is {per_story:.0f} ft per story,"
                " so they may not describe the same structure."
            )
        else:
            ev += f" That puts the highest occupied level at roughly {top:.0f} ft (our estimate)."
            if top < HIGH_RISE_FT:
                state = FOUND
            else:
                state = ISSUE
                ev += " The high-rise provisions may apply."
    elif f.stories is not None and f.stories <= 4:
        state, ev = FOUND, f"Stories on record: {f.stories}. Height not yet measured from imagery."
    elif f.stories is not None and top >= HIGH_RISE_FT:
        state = ISSUE
        ev = (
            f"Stories on record: {f.stories}. At {TYPICAL_STORY_FT:.0f} ft or more per story (our assumption) "
            "the highest occupied level is likely 75 ft or above, so the high-rise provisions may apply. "
            "Height not yet measured."
        )
    elif f.stories is not None:
        state, ev = NO_DATA, f"Stories on record: {f.stories}. Height not yet measured from imagery."
    else:
        state, ev = NO_DATA, "No stories on record and no height measured."
    return Row("height", "Height", rule, BULLETIN_URL, state, ev, "CoStar, Vexcel", "Survey or building records")


READ_NOTE = "This is read from images, not measured."
NOT_LIVING_SPACE = {"Staircase", "Hallway", "Corridor", "Closet", "Bathroom", "Laundry", "Utility", "Garage",
                    "Lobby", "Entrance", "Patio", "Basement", "Elevator"}


def stairs_by_floor(f: SpaceFacts) -> dict:
    """Floor label -> stairs seen in the scan: labelled stair rooms, or places the scan path
    steps to another floor, whichever is more."""
    floors = {r.floor for r in f.rooms} | set(f.stair_links)
    return {
        fl: max(sum(1 for r in f.rooms if r.floor == fl and r.kind == "Staircase"), f.stair_links.get(fl, 0))
        for fl in sorted(floors)
    }


def _exits(f: SpaceFacts) -> Row:
    """Exits per story: the architect's floor plan when it shows the stairs, else the scan."""
    row = _exits_from_scan(f)
    plan = f.plan_reading or {}
    stairs = plan.get("stairs")
    if not isinstance(stairs, int):
        return row
    whole = plan.get("covers") == "floor"
    cars = plan.get("elevators")
    plan_source = "Matterport" if plan.get("source") == "Matterport" else "CoStar"
    seen = (
        f"The floor plan on record shows {stairs} stairwell{'s' if stairs != 1 else ''}"
        + (f" and {cars} elevator cars" if isinstance(cars, int) else "")
        + (" on the floor." if whole else " on the part of the floor it covers.")
        + f" {READ_NOTE}"
    )
    if stairs >= 2:
        row.state, row.evidence, row.layer = FOUND, seen, f"{plan_source} floor plan, read by an AI model"
    elif whole and row.state != FOUND:
        row.state, row.evidence, row.layer = ISSUE, seen, f"{plan_source} floor plan, read by an AI model"
    else:
        row.evidence += " " + seen
        row.layer += f", {plan_source} floor plan"
    return row


def _exits_from_scan(f: SpaceFacts) -> Row:
    rule = (
        "Means of egress follow CBC Chapter 10: exits per story, distance between exits, travel distance, "
        "and enclosed exit stairways. An existing fire escape in good condition may serve as a second exit."
    )
    stairs = stairs_by_floor(f)
    read = f.pano_reading if f.pano_reading and f.pano_reading.get("indoor", True) else None
    layer = "Matterport"
    if not any(stairs.values()) and read:
        layer = "Matterport panoramas, read by an AI model"
        n, seen_stairs, doors = read["panoramas"], read.get("stairs", 0), read.get("exit_doors", 0)
        ev = (
            f"In {n} panoramas of the scan, {seen_stairs} staircases and {doors} doors marked EXIT are visible. "
            f"{READ_NOTE} The scan may not cover every exit."
        )
        state = FOUND if seen_stairs + doors >= 2 else ISSUE if seen_stairs + doors == 1 else NO_DATA
        if state == NO_DATA:
            ev = (
                f"No staircase or door marked EXIT is visible in the {n} panoramas read from the scan. "
                f"{READ_NOTE} The scan covers part of the building."
            )
    elif not f.rooms and not f.stair_links:
        state, ev = NO_DATA, "No scan has been read, so stairs could not be identified."
    elif not any(stairs.values()) and not _has_room_types(f):
        state, ev = NO_DATA, "The scan has no room types and stays on one floor, so stairs could not be identified."
    elif not any(stairs.values()):
        state = NO_DATA
        ev = "No stair lies inside the scanned area. The scan covers a suite, and the building's stairs are outside it."
    else:
        listing = ", ".join(f"{fl or 'Floor'}: {n}" for fl, n in stairs.items())
        ev = (
            f"Stairs seen in the scan by floor: {listing}. They are found from stair rooms and from where "
            "the scan path steps between floors. The scan may not cover every stair."
        )
        state = FOUND if all(n >= 2 for n in stairs.values()) else ISSUE
    return Row("exits", "Exits per story", rule, BULLETIN_URL, state, ev, layer, "Architect and LADBS plan check")


def window_share(f: SpaceFacts):
    """(share of living-space floor area in rooms with a window, rooms with a window, rooms without, windows).

    None when the scan carries no wall geometry.
    """
    rooms = [r for r in f.rooms if r.windows is not None and r.kind not in NOT_LIVING_SPACE]
    if not rooms:
        return None
    lit = [r for r in rooms if r.windows > 0]
    total = sum(r.area_sqft or 0 for r in rooms)
    share = sum(r.area_sqft or 0 for r in lit) / total if total else len(lit) / len(rooms)
    return share, len(lit), len(rooms) - len(lit), sum(r.windows for r in rooms)


def _escape(f: SpaceFacts) -> Row:
    rule = (
        "Emergency escape and rescue openings for sleeping rooms, where the change of occupancy "
        "calls for them, follow CEBC 506.4 or 1011.5.6; existing window openings get size tolerances."
    )
    found = window_share(f)
    read = f.pano_reading
    layer = "Matterport"
    if found is None and read and not read.get("indoor", True):
        state, ev = NO_DATA, "The scan is mostly outdoors, so it says nothing about windows inside the building."
    elif found is None and read:
        layer = "Matterport panoramas, read by an AI model"
        n, lit = read["panoramas"], read.get("with_windows", 0)
        ev = f"A window to the outside is visible in {lit} of {n} panoramas read from the scan. {READ_NOTE}"
        if lit / n >= 0.5:
            state = FOUND
        else:
            state = ISSUE
            ev += " Sleeping rooms would have to be placed in the part with windows."
    elif found is None:
        state, ev = NO_DATA, "The scan has no wall and window geometry, so windows could not be read."
    else:
        share, lit, dark, windows = found
        ev = (
            f"The scan records {windows} windows. {lit} of {lit + dark} rooms have at least one, "
            f"covering {share:.0%} of the scanned floor area. Whether they open is not recorded."
        )
        if share >= 0.5:
            state = FOUND
        else:
            state = ISSUE
            ev += " Sleeping rooms would have to be placed in the part with windows."
    return Row("escape", "Escape openings for sleeping rooms", rule, BULLETIN_URL, state, ev, layer, "Architect on site")


def _separation(f: SpaceFacts) -> Row:
    rule = (
        "Exterior wall ratings depend on fire separation distance (CBC 705.5). The bulletin says a change "
        "from office to residential generally does not call for a higher rating, and existing unrated "
        "openings may stay."
    )
    if f.neighbor_gap_ft is None:
        state, ev = NO_DATA, "Distance to neighbouring buildings has not been measured from imagery yet."
    else:
        state, ev = REVIEW, f"Closest neighbouring building seen in imagery: about {f.neighbor_gap_ft:.0f} ft."
    return Row("separation", "Fire separation distance", rule, BULLETIN_URL, state, ev, "Vexcel", "Survey")


def _access(f: SpaceFacts) -> Row:
    rule = "Exits lead to a public way and fire vehicles can reach the building."
    if f.street_distance_ft is None and f.street_frontage is None:
        state, ev = NO_DATA, "Streets around the building have not been read yet."
    elif f.street_distance_ft is None:
        state, ev = ISSUE, "No public street was found within 500 ft of the building."
    else:
        name = f.street_name or "an unnamed public street"
        ev = f"Closest public street: {name}, about {f.street_distance_ft:.0f} ft from the building footprint."
        if f.street_distance_ft <= STREET_REACH_FT:
            state = FOUND
        else:
            state = ISSUE
            ev += f" That is beyond the {STREET_REACH_FT:.0f} ft we use as a working reach (our assumption)."
    return Row("access", "Fire access and exit discharge", rule, BULLETIN_URL, state, ev,
               "Vexcel, OpenStreetMap", "Fire Department review")


def _elevator(f: SpaceFacts) -> Row:
    rule = (
        "At least one gurney-sized elevator car must serve all occupied levels (CBC 3002.4.1a). "
        "Buildings of four stories or fewer may not need one."
    )
    if f.stories is None:
        state, ev = NO_DATA, "No stories on record."
    elif f.stories <= 4:
        state, ev = FOUND, f"Stories on record: {f.stories}."
    else:
        ev = f"Stories on record: {f.stories}."
        if f.passenger_elevators:
            ev += f" Passenger elevators on record: {f.passenger_elevators}; cab size is not recorded."
        state, ev = REVIEW, ev + " Elevator requirements to be reviewed."
    return Row("elevator", "Elevator", rule, BULLETIN_URL, state, ev, "CoStar", "LADBS plan check")


def _stay(f: SpaceFacts) -> Row:
    rule = "Rentals longer than 30 consecutive days are outside the city's short-term rental rules."
    if f.min_stay_days > 30:
        state, ev = FOUND, f"Planned minimum stay: {f.min_stay_days} days."
    else:
        state, ev = ISSUE, f"Planned minimum stay: {f.min_stay_days} days, which is within short-term rental rules."
    return Row("stay", "Stay length", rule, HOME_SHARING_URL, state, ev, "Product setting", "City Planning guidance")


def _sprinklers(f: SpaceFacts) -> Row:
    rule = "The new residential occupancy must be fully sprinklered (NFPA 13, or 13R where permitted)."
    kind = f" ({f.sprinkler_type})" if f.sprinkler_type else ""
    if f.has_sprinklers is None:
        state, ev, layer = REVIEW, "Not available in our data.", "None"
    elif f.has_sprinklers:
        state, layer = REVIEW, "CoStar"
        ev = f"A sprinkler system{kind} is on record. Whether it covers the whole building is not recorded."
    else:
        state, ev, layer = ISSUE, "The record shows no sprinkler system.", "CoStar"
    return Row("sprinklers", "Sprinklers", rule, BULLETIN_URL, state, ev, layer, "Fire protection engineer")


def _review_rows() -> list:
    items = [
        ("alarm", "Fire alarm", "A fire alarm is required throughout the building (NFPA 72, CBC 907.2).", "Fire protection engineer"),
        ("seismic", "Seismic", "The building is analysed at 75% of the design earthquake ground motion and strengthened as required (CEBC 506.5.3 or 1006.3).", "Structural engineer"),
    ]
    rows = [
        Row(k, name, rule, BULLETIN_URL, REVIEW, "Not available in our data.", "None", who)
        for k, name, rule, who in items
    ]
    rows.append(
        Row(
            "historic", "Historic status",
            "Surveyed historic resources need Administrative Review; designated resources and HPOZ properties need a Conditional Use Permit.",
            ARO_URL, REVIEW, "Not available in our data.", "None", "Office of Historic Resources",
        )
    )
    return rows


def build_checklist(facts: SpaceFacts, current_year: int) -> list:
    return [
        _age(facts, current_year),
        _zone(facts),
        _units(facts),
        _height(facts),
        _exits(facts),
        _escape(facts),
        _separation(facts),
        _access(facts),
        _elevator(facts),
        _stay(facts),
        _sprinklers(facts),
        *_review_rows(),
    ]


def summary(rows: list) -> dict:
    """Count per state. There is deliberately no score and no overall result."""
    return {state: sum(1 for r in rows if r.state == state) for state in STATES}


def next_steps(rows: list) -> dict:
    """Open items grouped by who confirms them."""
    grouped: dict = {}
    for r in rows:
        if r.state in (NO_DATA, REVIEW, ISSUE):
            grouped.setdefault(r.confirmed_by, []).append(r)
    return grouped
