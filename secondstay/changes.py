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
    "sprinklers.install": "sqft",
    "sprinklers.verify_coverage": "lump",
    "fire_alarm.install": "sqft",
    "seismic.evaluate": "lump",
    "seismic.strengthen": "sqft",
    "highrise.systems": "lump",
    "egress.add_stair": "story",
    "escape.add_openings": "each",
    "elevator.upgrade": "each",
    "separation.wall_upgrade": "linear_ft",
    "historic.review": "lump",
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
