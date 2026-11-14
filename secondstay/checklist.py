"""Requirement-by-requirement evidence review for one space.

This module never states a conclusion about whether a conversion is allowed.
Each row reports what the published rule says, what the data shows, one of
four evidence states, and who confirms it. See PRD.md, "Wording rules".
"""

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
STORY_FT_RANGE = (8.0, 25.0)  # outside this, imagery height and stories on record do not fit together
TYPICAL_STORY_FT = 10.0  # our assumption for reading stories as height, not a rule


@dataclass
class RoomFact:
    floor: str
    kind: str  # Matterport room classification, e.g. "Office", "Staircase", "Bathroom"
    area_sqft: Optional[float] = None


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
    # Matterport
    floor_areas_sqft: list = field(default_factory=list)
    rooms: list = field(default_factory=list)  # list[RoomFact]
    # Vexcel
    height_ft: Optional[float] = None
    neighbor_gap_ft: Optional[float] = None
    street_frontage: Optional[bool] = None
    # Product settings
    min_stay_days: int = 31
    planning_unit_sqft: float = 500.0  # our planning assumption, not a rule


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
    rule = "Buildings at least 15 years old use the streamlined path; 5 to 15 years goes to discretionary review."
    if f.year_built is None:
        state, ev = NO_DATA, "No year built on record."
    else:
        age = year - f.year_built
        ev = f"Year built on record: {f.year_built} ({age} years)."
        if age >= 15:
            state = FOUND
        else:
            state = ISSUE
            ev += " This is under the 15-year threshold for the streamlined path."
    return Row("age", "Building age", rule, ARO_URL, state, ev, "CoStar", "LADBS building records")


def _zone(f: SpaceFacts) -> Row:
    rule = "The ordinance names Multifamily Residential, Commercial, Parking and Public Facilities zones."
    shown = f.zone or ""
    if f.zone_recorded and f.zone_recorded != f.zone:
        shown += f' (recorded as "{f.zone_recorded}")'
    if not f.zone and f.zone_recorded:
        state = NO_DATA
        ev = f'Zoning on record is "{f.zone_recorded}", which we could not match to a Los Angeles zone class.'
    elif not f.zone:
        state, ev = NO_DATA, "No zoning value on record."
    elif f.zone.upper() in ARO_ZONES:
        state, ev = FOUND, f"Zone on record: {shown}, which is among the zones the city lists."
    else:
        state, ev = ISSUE, f"Zone on record: {shown}, which is not among the zones the city lists."
    return Row("zone", "Zone", rule, ARO_URL, state, ev, "CoStar", "City zoning lookup (ZIMAS)")


def _units(f: SpaceFacts) -> Row:
    rule = "The ordinance covers conversions that create five or more residential units."
    area = sum(a for a in f.floor_areas_sqft if a)
    if area <= 0:
        state, ev = NO_DATA, "No floor area measured in the scan."
    else:
        units = int(area * 0.8 / f.planning_unit_sqft)
        ev = (
            f"Scan measures about {area:,.0f} sq ft. At our planning assumption of "
            f"{f.planning_unit_sqft:.0f} sq ft per unit and 80% usable area, that is about {units} units."
        )
        state = FOUND if units >= 5 else ISSUE
    return Row("units", "Unit count", rule, ARO_URL, state, ev, "Matterport", "Architect's layout")


def _height(f: SpaceFacts) -> Row:
    rule = "Additional systems apply at 75 feet and above (smokeproof stairs, fire pumps, emergency power)."
    stories = f" Stories on record: {f.stories}." if f.stories is not None else ""
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
            height, ev = f.height_ft, f"Height seen in aerial imagery: about {f.height_ft:.0f} ft."
        else:
            height, ev = f.record_height_ft, f"Height on record: {f.record_height_ft:.0f} ft."
        ev += stories
        per_story = f.height_ft / f.stories if f.height_ft is not None and f.stories else None
        if per_story is not None and not STORY_FT_RANGE[0] <= per_story <= STORY_FT_RANGE[1]:
            state = ISSUE
            ev += (
                f" The two sources do not fit together: that is {per_story:.0f} ft per story,"
                " so they may not describe the same structure."
            )
        elif height < HIGH_RISE_FT:
            state = FOUND
        else:
            state = ISSUE
            ev += " The additional high-rise systems may apply."
    elif f.stories is not None and f.stories <= 4:
        state, ev = FOUND, f"Stories on record: {f.stories}. Height not yet measured from imagery."
    elif f.stories is not None and f.stories * TYPICAL_STORY_FT >= HIGH_RISE_FT:
        state = ISSUE
        ev = (
            f"Stories on record: {f.stories}. At {TYPICAL_STORY_FT:.0f} ft or more per story (our assumption) "
            "that is likely 75 ft or above, so the additional high-rise systems may apply. Height not yet measured."
        )
    elif f.stories is not None:
        state, ev = NO_DATA, f"Stories on record: {f.stories}. Height not yet measured from imagery."
    else:
        state, ev = NO_DATA, "No stories on record and no height measured."
    return Row("height", "Height", rule, BULLETIN_URL, state, ev, "CoStar, Vexcel", "Survey or building records")


def _exits(f: SpaceFacts) -> Row:
    rule = "Residential egress standards set the number of exits per story and the distance between them."
    if not _has_room_types(f):
        state, ev = NO_DATA, "The scan has no room types, so stairs could not be identified."
    else:
        floors = sorted({r.floor for r in f.rooms})
        stairs = {fl: sum(1 for r in f.rooms if r.floor == fl and r.kind == "Staircase") for fl in floors}
        listing = ", ".join(f"{fl}: {n}" for fl, n in stairs.items())
        ev = f"Stairs identified in the scan by floor: {listing}. The scan may not cover every stair."
        if len(floors) < 2:
            state = NO_DATA
            ev = "Single floor in the scan. Exterior exit doors are not identified in the scan data."
        elif all(n >= 2 for n in stairs.values()):
            state = FOUND
        else:
            state = ISSUE
    return Row("exits", "Exits per story", rule, BULLETIN_URL, state, ev, "Matterport", "Architect and LADBS plan check")


def _escape(f: SpaceFacts) -> Row:
    rule = "Each sleeping room needs an emergency escape and rescue opening to the outside."
    return Row(
        "escape", "Escape openings for sleeping rooms", rule, BULLETIN_URL, NO_DATA,
        "Exterior walls and windows have not been read from the scan yet.",
        "Matterport, Vexcel", "Architect on site",
    )


def _separation(f: SpaceFacts) -> Row:
    rule = "Exterior wall and opening requirements depend on the distance to neighbouring buildings."
    if f.neighbor_gap_ft is None:
        state, ev = NO_DATA, "Distance to neighbouring buildings has not been measured from imagery yet."
    else:
        state, ev = REVIEW, f"Closest neighbouring building seen in imagery: about {f.neighbor_gap_ft:.0f} ft."
    return Row("separation", "Fire separation distance", rule, BULLETIN_URL, state, ev, "Vexcel", "Survey")


def _access(f: SpaceFacts) -> Row:
    rule = "Exits lead to a public way and fire vehicles can reach the building."
    if f.street_frontage is None:
        state, ev = NO_DATA, "Street frontage has not been checked from imagery yet."
    elif f.street_frontage:
        state, ev = FOUND, "Imagery shows the building fronting a public street."
    else:
        state, ev = ISSUE, "Imagery does not show the building fronting a public street."
    return Row("access", "Fire access and exit discharge", rule, BULLETIN_URL, state, ev, "Vexcel", "Fire Department review")


def _elevator(f: SpaceFacts) -> Row:
    rule = "Buildings of four stories or fewer may not need a gurney-sized elevator."
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
    rule = "Residential occupancy requires full sprinkler coverage."
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
        ("alarm", "Fire alarm", "A fire alarm is required throughout the building.", "Fire protection engineer"),
        ("seismic", "Seismic", "Analysis at 75% of design ground motion, with strengthening as required.", "Structural engineer"),
    ]
    rows = [
        Row(k, name, rule, BULLETIN_URL, REVIEW, "Not available in our data.", "None", who)
        for k, name, rule, who in items
    ]
    rows.append(
        Row(
            "historic", "Historic status",
            "Surveyed or designated historic resources follow a different review.",
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
