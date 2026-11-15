"""Public-record evidence laid onto a finished checklist.

``build_checklist`` reads CoStar, Matterport and Vexcel. This module adds what the city,
county and state publish about the same building (see ``permits`` and ``public_records``)
and adjusts the rows they speak to:

| Row | Added evidence |
| --- | --- |
| Zone | The City Planning zoning map, which overrides CoStar's zoning text |
| Height | LA County's measured building height, cross-checked against Vexcel |
| Exits per story | Stairs named in permits |
| Elevator | Elevator permits |
| Sprinklers, Fire alarm | Sprinkler and alarm permits, by floor and suite |
| Seismic | Retrofit permits, the non-ductile concrete list, liquefaction and fault zones |
| Historic status | City, state and national designations |

It runs after ``build_checklist`` and before ``changes_for``, so the change list follows
the adjusted rows. Nothing here states a conclusion; permits record work that was filed,
not what is installed today.
"""

import dataclasses
from typing import Optional

from . import permits as permit_records
from . import public_records
from .checklist import (
    FOUND, HIGH_RISE_FT, HIGH_RISE_NOTE, ISSUE, NO_DATA, REVIEW, SpaceFacts, _zone,
)
from .costar import base_zone

PERMIT_NOTE = "Permits record work that was filed, not what is installed today."
READ_NOTE = "This is read from images, not measured."
PLAN_DIR = public_records.REPO_ROOT / "data" / "raw" / "plan_readings"
ALL_PLANS_DIR = public_records.REPO_ROOT / "data" / "raw" / "plan_readings_all"
PLAN_LAYER = "CoStar floor plans, read by an AI model"
PERMIT_LAYER = "LADBS permits"
DISAGREE_FT = 30.0
WHOLE_FLOOR_SHARE = 0.8  # a scan covering this share of a typical floor is read as showing the whole floor  # two height measurements further apart than this are shown as disagreeing


def plan_readings(property_id) -> list:
    """Every reading of a whole-floor plan CoStar holds for the building."""
    import json

    found = []
    first = PLAN_DIR / f"{property_id}.json"
    if first.exists():
        found.append(json.loads(first.read_text()))
    for path in sorted(ALL_PLANS_DIR.glob(f"{property_id}__*.json")):
        found.append(json.loads(path.read_text()))
    return [r for r in found if isinstance(r, dict) and "stairs" in r]


def plan_summary(readings: list) -> Optional[dict]:
    """What all the plans of one building show together."""
    if not readings:
        return None
    core = [r for r in readings if r.get("covers") in ("floor", "part") and isinstance(r.get("stairs"), int)]
    whole = [r for r in core if r.get("covers") == "floor"]
    cars = [r["elevators"] for r in readings if isinstance(r.get("elevators"), int)]
    labels = sorted({w.upper() for r in readings for w in r.get("elevator_labels") or [] if isinstance(w, str)})
    return {
        "read": len(readings),
        "with_core": len(core),
        "most_stairs": max((r["stairs"] for r in core), default=None),
        "whole_floor_stairs": sorted(r["stairs"] for r in whole),
        "most_elevators": max(cars, default=None),
        "elevator_labels": labels,
        "floors_named": sorted({r["floor_named"] for r in readings if isinstance(r.get("floor_named"), int)}),
    }


def load(b) -> tuple:
    """(permit summary, public records, plan summary) for a building, from the cache. Any may be None."""
    records = permit_records.cached(b.property_id)
    summary = permit_records.summarize(records, b.stories) if records is not None else None
    return summary, public_records.cached(b.property_id), plan_summary(plan_readings(b.property_id))


def _topic(summary: Optional[dict], key: str) -> Optional[dict]:
    return ((summary or {}).get("topics") or {}).get(key)


def permit_sentence(summary: Optional[dict], key: str, noun: str, stories: Optional[int], space: Optional[dict]) -> str:
    """'City permit records show 41 fire sprinkler permits, 1987 to 2025, with work named on 12 of 19 floors.'"""
    t = _topic(summary, key)
    if not t:
        return ""
    years = f"{t['first']} to {t['latest'][:4]}" if t.get("first") and t.get("latest") else "dates not recorded"
    text = f"City permit records show {t['count']} {noun} permit{'s' if t['count'] != 1 else ''}, {years}"
    floors = t.get("floors") or {}
    if floors:
        text += f", with work named on {len(floors)} of {stories} floors" if stories else f", with work named on {len(floors)} floors"
    text += "."
    if space and space.get("floor"):
        label = f"Suite {space['suite']}" if space.get("suite") else space.get("floor_label") or "this space"
        suite = (space.get("suite") or "").lstrip("0").upper()
        here = floors.get(str(space["floor"]), 0)
        if suite and suite in (t.get("suites") or []):
            text += f" {label} itself is named in {noun} permits."
        elif here:
            text += f" {here} of them name floor {space['floor']}, where {label} is."
        else:
            text += f" None of them names floor {space['floor']}, where {label} is."
    return text


def _set(row, state=None, evidence=None, layer=None):
    if state is not None:
        row.state = state
    if evidence is not None:
        row.evidence = evidence
    if layer is not None:
        row.layer = layer


def _add_layer(row, name: str) -> None:
    if name not in row.layer:
        row.layer = name if row.layer in ("", "None") else f"{row.layer}, {name}"


def apply(rows: list, facts: SpaceFacts, summary: Optional[dict] = None, records: Optional[dict] = None,
          space: Optional[dict] = None, plans: Optional[dict] = None) -> list:
    """Adjust rows in place with permit and public-record evidence, and return them."""
    row = {r.key: r for r in rows}
    stories = facts.stories
    records = records or {}

    # Zone: the city's map is the authority; CoStar's text is shown when it differs.
    city = (records.get("zoning") or [{}])[0].get("zone") if records.get("zoning") else None
    if city and "zone" in row:
        recalculated = _zone(dataclasses.replace(facts, zone=base_zone(city), zone_recorded=city))
        ev = recalculated.evidence.replace("Zone on record", "Zone on the City Planning zoning map").replace(
            "Zoning on record", "Zoning on the City Planning zoning map").replace("recorded as", "full zone")
        if "(" in (base_zone(city) or ""):
            ev += (" It is a specific plan zone the ordinance list does not name; whether the ordinance reaches it "
                   "is to be confirmed with City Planning.")
        if facts.zone and base_zone(city) and facts.zone != base_zone(city):
            ev += f" CoStar records the zone as {facts.zone_recorded or facts.zone}, which differs from the city's map."
        _set(row["zone"], recalculated.state, ev, "City Planning zoning map")

    # Height: LA County's survey, against Vexcel.
    county = records.get("county_height")
    if county and "height" in row:
        h = row["height"]
        sentence = (f" LA County's {county['year']} building survey measures it at about {county['feet']:.0f} ft "
                    "to the highest major feature, rooftop equipment excluded.")
        if facts.height_ft is not None and abs(facts.height_ft - county["feet"]) > DISAGREE_FT:
            _set(h, ISSUE, h.evidence + sentence + f" The two measurements differ by {abs(facts.height_ft - county['feet']):.0f} ft.")
        elif facts.height_ft is None:
            top = county["feet"] * (stories - 1) / stories if stories else county["feet"]
            ev = (f"LA County's {county['year']} building survey measures the building at about {county['feet']:.0f} ft."
                  + (f" Stories on record: {stories}." if stories else "")
                  + f" That puts the highest occupied level at roughly {top:.0f} ft (our estimate).")
            if top >= HIGH_RISE_FT:
                ev += HIGH_RISE_NOTE
            _set(h, FOUND, ev)
        else:
            _set(h, evidence=h.evidence + sentence + " The two measurements agree within 30 ft.")
        _add_layer(h, "LA County")
        systems = [f"{t['label'].lower()} ({t['count']})" for k in ("smoke_control", "fire_pump", "standpipe", "generator")
                   for t in [_topic(summary, k)] if t]
        if systems and "high-rise provisions" in h.evidence:
            h.evidence += f" City permit records show work on high-rise systems already: {', '.join(systems)}."
            _add_layer(h, PERMIT_LAYER)

    # Exits: every floor plan CoStar holds, read together.
    if plans and plans.get("most_stairs") is not None and "exits" in row:
        most, whole = plans["most_stairs"], plans["whole_floor_stairs"]
        seen = (f"{plans['with_core']} of the {plans['read']} floor plans on record show the building core; "
                f"the most stairwells drawn on one plan is {most}.")
        if whole:
            seen += f" Whole-floor plans show {', '.join(str(n) for n in whole)} stairwells."
        if most >= 2:
            _set(row["exits"], FOUND, f"{seen} {READ_NOTE}", PLAN_LAYER)
        elif whole and max(whole) == 1 and row["exits"].state != FOUND:
            _set(row["exits"], ISSUE, f"{seen} {READ_NOTE} One stairwell on a whole floor is fewer than residential egress usually calls for.",
                 PLAN_LAYER)

    # Exits: stairs named in permits.
    named = (summary or {}).get("stairs_named") or []
    if len(named) >= 2 and "exits" in row and row["exits"].state != FOUND:
        labels = ", ".join(("#" + n) if n.isdigit() else n for n in named)
        _set(row["exits"], FOUND, f"City permit records name {len(named)} stairs in this building ({labels}). {PERMIT_NOTE}",
             PERMIT_LAYER)

    # Exits: one stair seen in a scan or photos of one suite is not a count for the floor.
    if "exits" in row and row["exits"].state == ISSUE and PLAN_LAYER not in row["exits"].layer:
        r = row["exits"]
        scanned = max((a for a in facts.floor_areas_sqft if a), default=0)
        typical = facts.typical_floor_sqft or (facts.building_sqft / stories if facts.building_sqft and stories else None)
        share = scanned / typical if scanned and typical else None
        if share is not None and share >= WHOLE_FLOOR_SHARE:
            r.evidence += f" The scan covers about {min(share, 1):.0%} of a typical floor, so it shows most of the floor."
        elif share is not None:
            _set(r, NO_DATA, r.evidence + (
                f" The scan covers only about {share:.0%} of a typical floor, so stairs outside it are not seen. "
                "This is not a stair count for the floor."))
        else:
            _set(r, NO_DATA, r.evidence + (
                " The images show part of the building only, so stairs outside them are not seen. "
                "This is not a stair count for the floor."))

    # Elevator: what the floor plans draw. Cab size is not legible on any of them.
    if plans and plans.get("most_elevators") is not None and "elevator" in row:
        text = f" Floor plans on record draw up to {plans['most_elevators']} elevator cars"
        if plans["elevator_labels"]:
            text += f", labelled {', '.join(w.lower() for w in plans['elevator_labels'])}"
        row["elevator"].evidence += text + f". Cab size cannot be read from them. {READ_NOTE}"
        _add_layer(row["elevator"], "CoStar floor plans")

    # Elevator: permits as added evidence.
    text = permit_sentence(summary, "elevator", "elevator", stories, space)
    if text and "elevator" in row:
        row["elevator"].evidence += " " + text
        _add_layer(row["elevator"], PERMIT_LAYER)

    # Sprinklers.
    text = permit_sentence(summary, "sprinklers", "fire sprinkler", stories, space)
    if text and "sprinklers" in row:
        r = row["sprinklers"]
        if facts.has_sprinklers is False:
            _set(r, ISSUE, f"The two sources disagree. The CoStar record shows no sprinkler system. {text} {PERMIT_NOTE}")
        else:
            prefix = f"A sprinkler system{f' ({facts.sprinkler_type})' if facts.sprinkler_type else ''} is on record. " if facts.has_sprinklers else ""
            _set(r, FOUND, prefix + text + f" {PERMIT_NOTE} Whether coverage is complete is to be confirmed by a fire protection engineer.")
        _add_layer(r, PERMIT_LAYER)

    # Fire alarm.
    text = permit_sentence(summary, "alarm", "fire alarm", stories, space)
    if "alarm" in row:
        if text:
            _set(row["alarm"], FOUND, f"{text} {PERMIT_NOTE} Whether the system covers the whole building is to be confirmed.",
                 PERMIT_LAYER)
        elif summary is not None:
            _set(row["alarm"], evidence="Not available in our data, and no fire alarm permits were found for the parcel.")

    # Seismic: always the engineer's call; the records say what is already known.
    if "seismic" in row:
        r = row["seismic"]
        parts = ["Analysis is called for in every conversion."]
        ndc = records.get("ndc")
        if ndc:
            step = f"retrofit due {ndc['retrofit_due']}" if ndc.get("retrofit_due") else "no due date listed"
            done = f", work completed {ndc['work_completion']}" if ndc.get("work_completion") else ""
            parts.append(f"The building is on LADBS's non-ductile concrete retrofit list ({step}{done}).")
            _add_layer(r, "LADBS retrofit list")
        elif ndc is False:
            parts.append("It is not on LADBS's non-ductile concrete retrofit list.")
        if records.get("liquefaction"):
            parts.append("It sits in a state liquefaction zone of required investigation.")
            _add_layer(r, "California Geological Survey")
        if records.get("fault_zone"):
            parts.append(f"It sits in an Alquist-Priolo fault zone ({records['fault_zone'].get('quad')} map).")
            _add_layer(r, "California Geological Survey")
        text = permit_sentence(summary, "seismic", "seismic", stories, space)
        if text:
            parts.append(f"{text} {PERMIT_NOTE}")
            _add_layer(r, PERMIT_LAYER)
        if len(parts) > 1:
            _set(r, REVIEW, " ".join(parts))

    # Historic status.
    historic = records.get("historic")
    if historic is not None and "historic" in row:
        r = row["historic"]
        if historic:
            names = []
            for h in historic:
                label = h["kind"] + (f" #{h['number']}" if h.get("number") and h["kind"] == "Historic-Cultural Monument" else "")
                names.append(f"{label}: {h['name']}" if h.get("name") else label)
            designated = any(h["kind"] in ("Historic-Cultural Monument", "Historic Preservation Overlay Zone") for h in historic)
            ev = "The site falls within: " + "; ".join(dict.fromkeys(names)) + "."
            ev += (" Designated resources and HPOZ properties need a Conditional Use Permit." if designated
                   else " Listed resources follow Administrative Review.")
            _set(r, ISSUE, ev, "City Planning historic layers")
        else:
            _set(r, evidence=("No Historic-Cultural Monument, HPOZ, National Register or California Register "
                              "listing covers the site. SurveyLA surveyed resources were not checked."),
                 layer="City Planning historic layers")
    return rows
