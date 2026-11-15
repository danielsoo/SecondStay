"""The change list: the one format shared by the rules work and the cost model.

A change is one piece of physical or professional work that the published
rules call for, with a quantity the cost model can multiply by a unit price.
This module never puts a price on anything and never states whether a
conversion is allowed. See PRD.md, "Wording rules".

The shape of ``Change`` is a contract. Fields may be added with a default;
none may be renamed or removed.
"""

import json
from dataclasses import asdict, dataclass, fields
from typing import Optional

from .checklist import (
    ISSUE, NO_DATA, DIRECT_AGE_YEARS, HIGH_RISE_FT, MIN_AGE_YEARS, SpaceFacts, stairs_by_floor, top_occupied_ft,
    window_share,
)

# How sure the evidence is that the work applies.
CALLED_FOR = "called_for"  # the rule calls for it and the evidence shows it applies
POSSIBLE = "possible"  # the evidence points to it but could be wrong
UNKNOWN = "unknown"  # the data cannot say either way
CERTAINTIES = (CALLED_FOR, POSSIBLE, UNKNOWN)

UNITS = ("sqft", "each", "linear_ft", "story", "lump")
SCOPES = ("building", "space")  # "space" is the scanned suite

# Starting catalog: change key -> unit. The rules work owns this list and may add to it.
# The cost model prices every key here and shows any other key as "not priced".
CATALOG = {
    # Planning path
    "planning.conditional_use_permit": "lump",
    "historic.review": "lump",
    # Fire protection
    "sprinklers.install": "sqft",
    "sprinklers.verify_coverage": "lump",
    "fire_alarm.install": "sqft",
    # High-rise provisions (highest occupied level more than 75 ft up)
    "highrise.smokeproof_stairs": "each",
    "highrise.fire_pump_water_supply": "lump",
    "highrise.emergency_power": "lump",
    "highrise.fire_command_center": "lump",
    "highrise.smoke_control": "lump",
    # Elevators
    "elevator.gurney_car": "each",
    "elevator.fire_service_access": "each",
    # Structure
    "seismic.evaluate": "lump",
    "seismic.strengthen": "sqft",
    # Egress
    "egress.add_stair": "story",
    "escape.add_openings": "each",
    # Building the homes
    "units.fitout": "sqft",
    "units.bathroom": "each",
    "units.kitchen": "each",
    "units.plumbing_run": "linear_ft",
}


@dataclass
class Change:
    key: str  # from CATALOG, e.g. "sprinklers.install"
    requirement: str  # checklist row key it comes from, e.g. "sprinklers"
    title: str  # shown to the owner: "Install sprinkler coverage"
    certainty: str  # one of CERTAINTIES
    quantity: Optional[float]  # None when the data cannot size it
    unit: str  # one of UNITS
    quantity_basis: str  # where the quantity came from, in words
    scope: str  # one of SCOPES
    reason: str  # the evidence that triggered it
    source_url: Optional[str]  # the published rule
    confirmed_by: str  # who confirms it

    def __post_init__(self):
        if self.certainty not in CERTAINTIES:
            raise ValueError(f"certainty must be one of {CERTAINTIES}, got {self.certainty!r}")
        if self.unit not in UNITS:
            raise ValueError(f"unit must be one of {UNITS}, got {self.unit!r}")
        if self.scope not in SCOPES:
            raise ValueError(f"scope must be one of {SCOPES}, got {self.scope!r}")


def from_dicts(items: list) -> list:
    """Build changes from plain dicts, ignoring fields this version does not know."""
    known = {f.name for f in fields(Change)}
    return [Change(**{k: v for k, v in item.items() if k in known}) for item in items]


def to_dicts(changes: list) -> list:
    return [asdict(change) for change in changes]


def load_changes(path) -> list:
    with open(path, encoding="utf-8") as handle:
        return from_dicts(json.load(handle))


# --- from evidence to changes -----------------------------------------------------------------

# Manufacturing zones are outside the city's list; the Planning page describes a Conditional Use
# path for them only inside an Adaptive Reuse Subarea.
MANUFACTURING_ZONES = {"MR1", "M1", "MR2", "M2", "M3"}
FIRE_SERVICE_ELEVATOR_FT = 120.0  # occupiable level above this needs a fire service access elevator
NEAR_HIGH_RISE_FT = 60.0  # between this and 75 ft our height estimate cannot settle the question
USABLE_SHARE = 0.8  # our planning assumption, matching the unit count row


def _rooms_labelled(f: SpaceFacts) -> bool:
    return any(r.kind not in ("Void", "Other", "") for r in f.rooms)


def changes_for(facts: SpaceFacts, rows: list, current_year: int) -> list:
    """The work the published rules call for, given the evidence. No prices, no conclusion.

    A requirement whose evidence already fits the rule produces nothing. See
    docs/requirements-research.md for the source behind each branch.
    """
    row = {r.key: r for r in rows}
    out = []

    def add(key, requirement, title, certainty, quantity, basis, scope, reason):
        r = row[requirement]
        out.append(Change(
            key=key, requirement=requirement, title=title, certainty=certainty,
            quantity=quantity, unit=CATALOG[key], quantity_basis=basis, scope=scope,
            reason=reason, source_url=r.source_url, confirmed_by=r.confirmed_by,
        ))

    whole = facts.building_sqft
    whole_basis = "Rentable building area on record" if whole else "Building area not on record"

    # Planning path: age and zone
    age = current_year - facts.year_built if facts.year_built is not None else None
    if age is not None and MIN_AGE_YEARS <= age < DIRECT_AGE_YEARS:
        add("planning.conditional_use_permit", "age", "Zoning Administrator approval (Conditional Use Permit)",
            CALLED_FOR, 1, "One application", "building",
            f"The building is {age} years old, under the 15-year threshold for the direct path.")
    elif facts.zone in MANUFACTURING_ZONES:
        add("planning.conditional_use_permit", "zone", "Zoning Administrator approval (Conditional Use Permit)",
            POSSIBLE, 1, "One application", "building",
            f"Zone {facts.zone} is a manufacturing zone. The city describes a path for these only inside "
            "an Adaptive Reuse Subarea, which our data does not show.")
    add("historic.review", "historic", "Historic resource check and review", UNKNOWN, 1, "One review",
        "building", "Historic status is not in our data.")

    # Sprinklers and fire alarm
    if facts.has_sprinklers is False:
        add("sprinklers.install", "sprinklers", "Install sprinkler coverage", CALLED_FOR, whole, whole_basis,
            "building", "The record shows no sprinkler system.")
    elif facts.has_sprinklers:
        add("sprinklers.verify_coverage", "sprinklers", "Confirm and adapt sprinkler coverage", POSSIBLE, 1,
            "One study", "building",
            "A sprinkler system is on record. Its coverage and whether it suits a residential layout are not recorded.")
    else:
        add("sprinklers.install", "sprinklers", "Install sprinkler coverage", UNKNOWN, whole, whole_basis,
            "building", "The record does not say whether the building has sprinklers.")
    add("fire_alarm.install", "alarm", "Fire alarm throughout the building", UNKNOWN, whole, whole_basis,
        "building", "The existing fire alarm, if any, is not in our data.")

    # High-rise provisions. The rule measures to the highest occupied level, which we estimate.
    top = top_occupied_ft(facts)
    if top is not None and top >= NEAR_HIGH_RISE_FT:
        over = top >= HIGH_RISE_FT
        # When imagery and the record do not fit together, the estimate cannot be relied on.
        clash = "do not fit together" in row["height"].evidence or "disagree" in row["height"].evidence
        certainty = POSSIBLE if over and not clash else UNKNOWN
        where = (
            f"The highest occupied level is at roughly {top:.0f} ft by our estimate, "
            + ("above the 75 ft threshold. " if over else "close to the 75 ft threshold. ")
            + "Systems already in the building are not in our data."
        )
        add("highrise.smokeproof_stairs", "height", "Smokeproof or pressurised exit stairs", certainty, None,
            "Number of exit stairs not known", "building", where)
        add("highrise.fire_pump_water_supply", "height", "Fire pump and secondary water supply", certainty, 1,
            "One system", "building", where)
        add("highrise.emergency_power", "height", "Emergency generator", certainty, 1, "One system",
            "building", where)
        add("highrise.fire_command_center", "height", "Fire command center", certainty, 1, "One room",
            "building", where)
        add("highrise.smoke_control", "height", "Smoke control system", certainty, 1, "One system",
            "building", where)
        if top > FIRE_SERVICE_ELEVATOR_FT:
            add("elevator.fire_service_access", "elevator", "Fire service access elevator", POSSIBLE, 1,
                "At least one", "building",
                f"The highest occupied level is at roughly {top:.0f} ft by our estimate, above 120 ft.")

    # Gurney-sized elevator
    if facts.stories is not None and facts.stories > 4:
        cars = (f"{facts.passenger_elevators} passenger elevators are on record; cab size is not."
                if facts.passenger_elevators else "No passenger elevator is on record.")
        add("elevator.gurney_car", "elevator", "Gurney-sized elevator car", POSSIBLE, 1, "At least one",
            "building", f"The building has {facts.stories} stories. {cars}")

    # Structure
    add("seismic.evaluate", "seismic", "Seismic analysis", CALLED_FOR, 1, "One study", "building",
        "The bulletin calls for every converted building to be analysed.")
    add("seismic.strengthen", "seismic", "Seismic strengthening", UNKNOWN, whole, whole_basis, "building",
        "Whether strengthening is needed is known only after the analysis.")

    # Egress
    stairs = stairs_by_floor(facts)
    exits = row["exits"]
    if exits.state == ISSUE:
        short = [fl or "Floor" for fl, n in stairs.items() if n < 2]
        add("egress.add_stair", "exits", "Second exit stair", POSSIBLE, len(short) or 1,
            "Stories with fewer than two exits seen in the scan", "building", exits.evidence)
    elif exits.state == NO_DATA:
        add("egress.add_stair", "exits", "Second exit stair", UNKNOWN, None, "Exits not identified in the scan",
            "building", exits.evidence)
    escape, windows = row["escape"], window_share(facts)
    if escape.state == ISSUE:
        add("escape.add_openings", "escape", "Escape openings for sleeping rooms", POSSIBLE,
            windows[2] if windows else None,
            "Rooms without a window in the scan" if windows else "Not measured; read from images",
            "space", escape.evidence)
    elif escape.state == NO_DATA:
        add("escape.add_openings", "escape", "Escape openings for sleeping rooms", UNKNOWN, None, "Not measured",
            "space", escape.evidence)

    # Building the homes
    scanned = sum(a for a in facts.floor_areas_sqft if a)
    area, scope, basis = (scanned, "space", "Floor area measured in the scan") if scanned else (
        whole, "building", whole_basis)
    if area:
        units = int(area * USABLE_SHARE / facts.planning_unit_sqft)
        sized = (f"{units} units at our planning assumption of {facts.planning_unit_sqft:.0f} sq ft each "
                 f"and {USABLE_SHARE:.0%} usable area")
        add("units.fitout", "units", "Residential fit-out", CALLED_FOR, area, basis, scope,
            f"About {area:,.0f} sq ft would be converted.")
        if units:
            baths = sum(1 for r in facts.rooms if r.kind == "Bathroom") if _rooms_labelled(facts) else 0
            found = f" minus {baths} bathrooms in the scan" if baths else ""
            add("units.kitchen", "units", "Kitchens", CALLED_FOR, units, sized, scope,
                "Each home needs a kitchen.")
            add("units.bathroom", "units", "Bathrooms", CALLED_FOR, max(units - baths, 0), sized + found, scope,
                "Each home needs a bathroom.")
    else:
        add("units.fitout", "units", "Residential fit-out", UNKNOWN, None, "No area measured or on record",
            "space", "Neither a scan area nor a building area is available.")
    return out
