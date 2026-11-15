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
    # A measured tall building is evidence, not a shortfall: the high-rise work goes to the change list.
    assert row.state == FOUND and "high-rise provisions likely apply" in row.evidence
    clash = by_key(build_checklist(two_floor_office(stories=2, height_ft=150), 2026))["height"]
    assert clash.state == ISSUE and "do not fit together" in clash.evidence  # sources that disagree stay open


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


def test_small_scan_is_read_against_the_whole_building():
    small = dict(floor_areas_sqft=[155], rooms=[])
    with_area = by_key(build_checklist(two_floor_office(building_sqft=40000.0, **small), 2026))["units"]
    assert with_area.state == FOUND and "only part of the building" in with_area.evidence
    without = by_key(build_checklist(two_floor_office(**small), 2026))["units"]
    assert without.state == NO_DATA


def test_height_rule_reads_the_highest_occupied_level():
    row = by_key(build_checklist(two_floor_office(stories=6, height_ft=84), 2026))["height"]
    assert row.state == FOUND and "roughly 70 ft" in row.evidence  # roof at 84 ft, top floor one story lower


# --- reading the inside of a scan -------------------------------------------------------------

def wall(*openings):
    return {"edges": [{"id": "e", "type": "wall", "openings": [{"type": t} for t in openings]}]}


def test_room_type_comes_from_tags_when_the_classifier_is_silent():
    from secondstay.matterport import room_kind

    assert room_kind({"classifications": [], "tags": ["indoor", "staircase"]}) == "Staircase"
    assert room_kind({"classifications": [{"label": "Other", "confidence": 1}], "keywords": ["office"]}) == "Office"
    assert room_kind({"classifications": [{"label": "Other", "confidence": 1}], "tags": ["indoor"]}) == "Other"


def test_windows_and_stair_links_are_read_from_the_scan():
    model = {
        "floors": [{"dimensionEstimates": {"area": 2000.0}}],
        "rooms": [
            {"floor": {"label": "Floor 1"}, "tags": ["office"], "dimensionEstimates": {"area": 600.0},
             "boundary": wall("window", "window", "doorway")},
            {"floor": {"label": "Floor 1"}, "tags": ["office"], "dimensionEstimates": {"area": 1400.0},
             "boundary": wall("doorway")},
        ],
        "locations": [
            {"id": "a", "floor": {"id": "1", "label": "Floor 1"}, "position": {"x": 0, "y": 0, "z": 0}, "neighbors": ["b", "c"]},
            {"id": "b", "floor": {"id": "2", "label": "Floor 2"}, "position": {"x": 1, "y": 0, "z": 3}, "neighbors": ["a"]},
            {"id": "c", "floor": {"id": "1", "label": "Floor 1"}, "position": {"x": 2, "y": 0, "z": 0}, "neighbors": ["a", "b"]},
        ],
    }
    facts = to_facts(model)
    assert [r.windows for r in facts.rooms] == [2, 0]
    assert facts.stair_links == {"Floor 1": 1, "Floor 2": 1}  # two links two metres apart are one stair
    rows = by_key(build_checklist(facts, 2026))
    assert rows["escape"].state == ISSUE and "30%" in rows["escape"].evidence
    assert rows["exits"].state == ISSUE and "Floor 1: 1" in rows["exits"].evidence


def test_scan_without_geometry_uses_the_image_reading_and_says_so():
    reading = {"panoramas": 12, "with_windows": 9, "stairs": 1, "exit_doors": 2, "indoor": True}
    rows = by_key(build_checklist(SpaceFacts(pano_reading=reading), 2026))
    assert rows["escape"].state == FOUND and "9 of 12 panoramas" in rows["escape"].evidence
    assert rows["exits"].state == FOUND and "read from images, not measured" in rows["exits"].evidence
    assert "AI model" in rows["exits"].layer
    outdoor = by_key(build_checklist(SpaceFacts(pano_reading={**reading, "indoor": False}), 2026))
    assert outdoor["escape"].state == NO_DATA and outdoor["exits"].state == NO_DATA


def test_new_zoning_code_is_read_by_density_district():
    from secondstay.costar import base_zone

    assert base_zone("[LB-1-WH1-5].[IX2-FA]") == "IX2-FA"
    rows = by_key(build_checklist(SpaceFacts(zone="IX2-FA", zone_recorded="[LB-1-WH1-5].[IX2-FA]"), 2026))
    assert rows["zone"].state == FOUND and "density district FA" in rows["zone"].evidence
    assert by_key(build_checklist(SpaceFacts(zone="IX2-4"), 2026))["zone"].state == ISSUE


def test_street_distance_fills_the_fire_access_row():
    near = by_key(build_checklist(SpaceFacts(street_frontage=True, street_name="Example Ave", street_distance_ft=30.0), 2026))
    assert near["access"].state == FOUND and "Example Ave" in near["access"].evidence
    far = by_key(build_checklist(SpaceFacts(street_frontage=True, street_distance_ft=260.0), 2026))
    assert far["access"].state == ISSUE
    assert by_key(build_checklist(SpaceFacts(), 2026))["access"].state == NO_DATA


def test_floor_plan_reading_decides_the_exits_row_when_it_shows_the_stairs():
    two = by_key(build_checklist(SpaceFacts(plan_reading={"stairs": 2, "elevators": 6, "covers": "floor"}), 2026))["exits"]
    assert two.state == FOUND and "2 stairwells and 6 elevator cars" in two.evidence and "floor plan" in two.layer
    one = by_key(build_checklist(SpaceFacts(plan_reading={"stairs": 1, "elevators": None, "covers": "floor"}), 2026))["exits"]
    assert one.state == ISSUE and "1 stairwell on the floor" in one.evidence
    part = by_key(build_checklist(SpaceFacts(plan_reading={"stairs": 1, "covers": "part"}), 2026))["exits"]
    assert part.state == NO_DATA and "part of the floor it covers" in part.evidence  # one stair on a partial plan settles nothing
    unread = by_key(build_checklist(SpaceFacts(plan_reading={"stairs": None, "covers": "suite"}), 2026))["exits"]
    assert unread.state == NO_DATA and "floor plan" not in unread.evidence


def test_scan_walls_windows_and_doors_become_plan_lines():
    from secondstay.matterport import plan_lines

    def edge(i, a, b, *openings):
        return {"id": i, "type": "wall", "vertices": [{"position": {"x": a[0], "y": a[1]}}, {"position": {"x": b[0], "y": b[1]}}],
                "openings": [{"type": t, "relativeCenter": c, "width": w} for t, c, w in openings]}

    shared = edge("e1", (0, 0), (10, 0), ("window", 0.5, 2.0), ("doorway", 0.9, 1.0))
    model = {"rooms": [
        {"floor": {"label": "Floor 1"}, "boundary": {"edges": [shared, edge("e2", (10, 0), (10, 5))]}},
        {"floor": {"label": "Floor 1"}, "boundary": {"edges": [shared]}},  # the shared wall is drawn once
    ]}
    lines = plan_lines(model)["Floor 1"]
    assert len(lines["walls"]) == 2
    assert lines["windows"] == [[4.0, 0.0, 6.0, 0.0]]  # two metres wide, centred on the wall
    assert [round(v, 2) for v in lines["doors"][0]] == [8.5, 0.0, 9.5, 0.0]


def test_selected_suite_sizes_the_unit_count():
    row = by_key(build_checklist(SpaceFacts(space_label="Suite 300", space_sqft=4200.0, building_sqft=90000.0), 2026))["units"]
    assert row.state == FOUND and "Suite 300 is listed at 4,200 sq ft" in row.evidence and "6 units" in row.evidence
    small = by_key(build_checklist(SpaceFacts(space_label="Suite 510", space_sqft=1800.0), 2026))["units"]
    assert small.state == ISSUE and "part of a larger conversion" in small.evidence
