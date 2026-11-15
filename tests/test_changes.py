"""The change-list contract. The sample list is a made-up building."""

import re
from pathlib import Path

import pytest

from secondstay.changes import (
    CATALOG, CERTAINTIES, UNITS, Change, from_dicts, load_changes, to_dicts,
)
from secondstay.checklist import build_checklist, SpaceFacts

SAMPLE = Path(__file__).parent / "fixtures" / "sample_changes.json"
BANNED = re.compile(
    r"\b(legal|illegal|compliant|approved|eligible|pass|passes|fail|fails|verdict)\b"
    r"|can be converted|cannot be converted",
    re.I,
)


def test_sample_list_loads_and_round_trips():
    changes = load_changes(SAMPLE)
    assert len(changes) == 5
    assert {c.certainty for c in changes} == set(CERTAINTIES)
    assert any(c.quantity is None for c in changes)  # the cost model must cope with this
    assert from_dicts(to_dicts(changes)) == changes


def test_sample_list_uses_the_catalog_and_real_requirement_keys():
    rows = {r.key for r in build_checklist(SpaceFacts(), 2026)}
    for change in load_changes(SAMPLE):
        assert CATALOG[change.key] == change.unit
        assert change.requirement in rows


def test_catalog_units_are_known():
    assert set(CATALOG.values()) <= set(UNITS)


def test_unknown_fields_are_ignored_and_bad_values_refused():
    item = to_dicts(load_changes(SAMPLE))[0]
    assert from_dicts([{**item, "added_later": 1}])[0].key == item["key"]
    for field, value in (("certainty", "certain"), ("unit", "m2"), ("scope", "floor")):
        with pytest.raises(ValueError):
            Change(**{**item, field: value})


def test_sample_wording_follows_the_rules():
    for change in load_changes(SAMPLE):
        text = " ".join([change.title, change.reason, change.quantity_basis, change.confirmed_by])
        assert not BANNED.search(text), (change.key, BANNED.search(text).group(0))


# --- changes_for, on made-up buildings ---------------------------------------------------------

from secondstay.changes import CALLED_FOR, POSSIBLE, UNKNOWN, changes_for
from secondstay.checklist import RoomFact


def changes(**facts):
    f = SpaceFacts(**facts)
    found = changes_for(f, build_checklist(f, 2026), 2026)
    return {c.key: c for c in found}, found


def low_rise(**overrides):
    rooms = []
    for floor in ("Floor 1", "Floor 2"):
        rooms += [RoomFact(floor, "Office", 300) for _ in range(6)]
        rooms += [RoomFact(floor, "Staircase", 80), RoomFact(floor, "Staircase", 80), RoomFact(floor, "Bathroom", 60)]
    facts = dict(year_built=1987, zone="C2", stories=2, has_sprinklers=True, building_sqft=20000.0,
                 height_ft=28.0, floor_areas_sqft=[8000, 8000], rooms=rooms)
    facts.update(overrides)
    return facts


def test_low_rise_with_everything_on_record():
    by_key, found = changes(**low_rise())
    assert "planning.conditional_use_permit" not in by_key
    assert not any(k.startswith("highrise.") or k.startswith("elevator.") for k in by_key)
    assert "egress.add_stair" not in by_key  # two stairs on each floor in the scan
    assert by_key["sprinklers.verify_coverage"].certainty == POSSIBLE
    assert by_key["seismic.evaluate"].certainty == CALLED_FOR
    assert by_key["seismic.strengthen"].quantity == 20000.0
    assert (by_key["units.fitout"].quantity, by_key["units.fitout"].scope) == (16000, "space")
    assert by_key["units.kitchen"].quantity == 25
    assert by_key["units.bathroom"].quantity == 23 and "minus 2 bathrooms" in by_key["units.bathroom"].quantity_basis


def test_tall_building_brings_high_rise_and_elevator_changes():
    by_key, _ = changes(year_built=1975, zone="C4", stories=20, height_ft=280.0, passenger_elevators=8,
                        building_sqft=400000.0)
    for key in ("highrise.smokeproof_stairs", "highrise.fire_pump_water_supply", "highrise.emergency_power",
                "highrise.fire_command_center", "highrise.smoke_control", "elevator.fire_service_access"):
        assert by_key[key].certainty == POSSIBLE, key
    assert by_key["highrise.smokeproof_stairs"].quantity is None
    # CBC 403.6.1: two fire service access cars, which also meet the stretcher rule, so no separate gurney car
    assert by_key["elevator.fire_service_access"].quantity == 2
    assert "8 passenger elevators" in by_key["elevator.fire_service_access"].reason
    assert "elevator.gurney_car" not in by_key
    one_car, _ = changes(year_built=1975, zone="C4", stories=20, height_ft=280.0, passenger_elevators=1)
    assert one_car["elevator.fire_service_access"].quantity == 1  # all elevators, when fewer than two
    mid, _ = changes(year_built=1975, zone="C4", stories=8, height_ft=100.0, passenger_elevators=3)
    assert "elevator.fire_service_access" not in mid and mid["elevator.gurney_car"].quantity == 1
    assert by_key["units.fitout"].scope == "building"  # no scan, so sized on the whole building


def test_height_near_the_threshold_or_in_doubt_is_unknown():
    near, _ = changes(stories=6, height_ft=80.0)  # top floor at about 67 ft
    assert near["highrise.fire_pump_water_supply"].certainty == UNKNOWN
    clash, _ = changes(stories=2, height_ft=190.0)  # imagery and record do not fit together
    assert clash["highrise.fire_pump_water_supply"].certainty == UNKNOWN


def test_sprinkler_record_decides_the_change():
    assert changes(has_sprinklers=False, building_sqft=5000.0)[0]["sprinklers.install"].certainty == CALLED_FOR
    assert changes(building_sqft=5000.0)[0]["sprinklers.install"].certainty == UNKNOWN
    assert changes(building_sqft=None)[0]["sprinklers.install"].quantity is None


def test_planning_path_follows_age_and_zone():
    assert changes(year_built=2016, zone="C2")[0]["planning.conditional_use_permit"].certainty == CALLED_FOR
    assert changes(year_built=1980, zone="M2")[0]["planning.conditional_use_permit"].certainty == POSSIBLE
    assert "planning.conditional_use_permit" not in changes(year_built=2024, zone="C2")[0]  # under 5 years: no path


def test_scan_without_room_types_leaves_stairs_unknown():
    by_key, _ = changes(floor_areas_sqft=[3000], rooms=[RoomFact("Floor 1", "Void"), RoomFact("Floor 1", "Other")])
    assert by_key["egress.add_stair"].certainty == UNKNOWN and by_key["egress.add_stair"].quantity is None
    assert by_key["units.bathroom"].quantity == by_key["units.kitchen"].quantity == 4


def test_one_stair_floor_is_a_possible_second_stair():
    facts = low_rise()
    facts["rooms"] = [r for r in facts["rooms"] if not (r.floor == "Floor 2" and r.kind == "Staircase")]
    by_key, _ = changes(**facts)
    assert (by_key["egress.add_stair"].certainty, by_key["egress.add_stair"].quantity) == (POSSIBLE, 1)


def test_every_change_fits_the_contract_and_the_wording_rules():
    cases = (low_rise(), dict(), dict(year_built=2016, zone="M1", stories=30, height_ft=400.0, has_sprinklers=False))
    for facts in cases:
        f = SpaceFacts(**facts)
        rows = {r.key for r in build_checklist(f, 2026)}
        for c in changes(**facts)[1]:
            assert CATALOG[c.key] == c.unit and c.requirement in rows
            text = " ".join([c.title, c.reason, c.quantity_basis])
            assert not BANNED.search(text), (c.key, BANNED.search(text).group(0))
