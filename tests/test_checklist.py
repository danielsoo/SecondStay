import re

from secondstay.checklist import (
    FOUND, ISSUE, NO_DATA, NOTICE, REVIEW, STATES,
    RoomFact, SpaceFacts, build_checklist, next_steps, summary,
)
from secondstay.matterport import to_facts

BANNED = re.compile(
    r"\b(legal|illegal|compliant|approved|eligible|pass|passes|fail|fails|verdict)\b"
    r"|can be converted|cannot be converted",
    re.I,
)


def two_floor_office(**overrides):
    rooms = []
    for floor in ("Floor 1", "Floor 2"):
        rooms += [RoomFact(floor, "Office", 300) for _ in range(6)]
        rooms += [RoomFact(floor, "Staircase", 80), RoomFact(floor, "Staircase", 80)]
        rooms += [RoomFact(floor, "Bathroom", 60)]
    fields = dict(
        name="Demo office", year_built=1987, zone="C2", stories=2,
        floor_areas_sqft=[8000, 8000], rooms=rooms,
    )
    fields.update(overrides)
    return SpaceFacts(**fields)


def by_key(rows):
    return {r.key: r for r in rows}


def test_well_documented_space():
    rows = by_key(build_checklist(two_floor_office(), 2026))
    assert rows["age"].state == FOUND and "39 years" in rows["age"].evidence
    assert rows["zone"].state == FOUND
    assert rows["units"].state == FOUND and "25 units" in rows["units"].evidence
    assert rows["height"].state == FOUND
    assert rows["exits"].state == FOUND
    assert rows["elevator"].state == FOUND
    assert rows["stay"].state == FOUND


def test_items_data_cannot_answer_always_go_to_review():
    rows = by_key(build_checklist(two_floor_office(), 2026))
    for key in ("sprinklers", "alarm", "seismic", "historic"):
        assert rows[key].state == REVIEW


def test_young_building_and_unlisted_zone_are_flagged():
    rows = by_key(build_checklist(two_floor_office(year_built=2018, zone="M2"), 2026))
    assert rows["age"].state == ISSUE
    assert rows["zone"].state == ISSUE


def test_single_stair_floor_is_flagged():
    facts = two_floor_office()
    facts.rooms = [r for r in facts.rooms if not (r.floor == "Floor 2" and r.kind == "Staircase")]
    facts.rooms.append(RoomFact("Floor 2", "Staircase", 80))
    assert by_key(build_checklist(facts, 2026))["exits"].state == ISSUE


def test_scan_without_room_types_says_not_enough_data():
    facts = two_floor_office(rooms=[RoomFact("Floor 1", "Void"), RoomFact("Floor 2", "Other")])
    assert by_key(build_checklist(facts, 2026))["exits"].state == NO_DATA


def test_empty_facts_never_claim_evidence():
    rows = build_checklist(SpaceFacts(), 2026)
    assert all(r.state in (NO_DATA, REVIEW) for r in rows if r.key != "stay")


def test_tall_building_notes_additional_systems():
    row = by_key(build_checklist(two_floor_office(stories=12, height_ft=150), 2026))["height"]
    assert row.state == ISSUE and "may apply" in row.evidence


def test_summary_counts_only_states_and_has_no_score():
    rows = build_checklist(two_floor_office(), 2026)
    counts = summary(rows)
    assert set(counts) == set(STATES)
    assert sum(counts.values()) == len(rows)


def test_next_steps_groups_open_items_by_who_confirms():
    steps = next_steps(build_checklist(two_floor_office(), 2026))
    assert "Structural engineer" in steps
    assert all(r.state != FOUND for items in steps.values() for r in items)


def test_wording_rules_hold_for_every_row():
    for facts in (SpaceFacts(), two_floor_office(), two_floor_office(year_built=2020, zone="M1", stories=20, height_ft=250)):
        for r in build_checklist(facts, 2026):
            text = " ".join([r.requirement, r.rule, r.evidence, r.confirmed_by])
            assert not BANNED.search(text), (r.key, BANNED.search(text).group(0))
            assert r.state in STATES
    assert "not a legal or code determination" in NOTICE


def test_matterport_model_to_facts():
    model = {
        "name": "Sample",
        "floors": [{"dimensionEstimates": {"area": 1000.0}}, {"dimensionEstimates": None}],
        "rooms": [
            {"floor": {"label": "Floor 1"},
             "classifications": [{"label": "Other", "confidence": 0.2}, {"label": "Office", "confidence": 0.9}],
             "dimensionEstimates": {"area": 250.0}},
            {"floor": None, "classifications": [], "dimensionEstimates": None},
        ],
    }
    facts = to_facts(model)
    assert facts.floor_areas_sqft == [1000.0, 0.0]
    assert facts.rooms[0].kind == "Office" and facts.rooms[0].area_sqft == 250.0
    assert facts.rooms[1].kind == "" and facts.rooms[1].floor == ""
