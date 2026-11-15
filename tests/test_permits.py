"""City permit records and public records. Every record here is made up; no request is made."""

import re

from secondstay import evidence, permits
from secondstay.checklist import FOUND, ISSUE, NO_DATA, REVIEW, SpaceFacts, build_checklist

BANNED = re.compile(
    r"\b(legal|illegal|compliant|approved|eligible|pass|passes|fail|fails|verdict)\b"
    r"|can be converted|cannot be converted",
    re.I,
)


def record(work, kind="Building", ptype="Bldg-Alter/Repair", issued="2019-05-02"):
    return {"number": "X", "kind": kind, "type": ptype, "issued": issued, "status": "Issued", "work": work, "apn": "1"}


# --- reading permit descriptions --------------------------------------------------------------

def test_floors_and_suites_are_read_from_descriptions():
    assert permits.floors_named("RELOCATE FIRE HOSE VALVE IN STAIRWAY-2ND FLR THRU 7TH FLR.", 12) == set(range(2, 8))
    assert permits.floors_named("INSTALL 6 SMOKE DETECTORS ON SUITE 820 & CORRIDOR", 12) == {8}
    assert permits.floors_named("TENANT IMPROVEMENT AT 15TH FLOOR", 12) == set()  # no 15th floor in a 12-story building
    assert permits.floors_named("NEW SPRINKLER HEADS, FLOORS 4-6", 20) == {4, 5, 6}
    assert permits.floors_named("NEW RESTROOM ON SECOND FLOOR", 4) == {2}
    assert permits.suites_named("SUITE #0415 AND STE 900") == {"415", "900"}


def test_stairs_and_stories_named():
    assert permits.stairs_named("STAIRWELL PRESSURIZATION FOR STAIR #1-2 AND #3") == {"1", "2", "3"}
    assert permits.stairs_named("REPAIR HANDRAIL AT STAIR B") == {"B"}
    assert permits.stairs_named("NEW 2-HR STAIRWAY ENCLOSURE") == set()  # a fire rating is not a stair number
    assert permits.stories_named("EXISTING 16 STORY HIGH-RISE") == 16


def test_topics_follow_permit_type_and_description():
    assert permits.topics_of(record("RELOCATE HEADS", "Mechanical", "Fire Sprinkler")) == {"sprinklers"}
    assert permits.topics_of(record("ADD ONE STROBE TO AN EXISTING SYSTEM", "Electrical", "Electrical")) == {"alarm"}
    assert "seismic" not in permits.topics_of(record("(1) EARTHQUAKE VALVE"))  # a gas shut-off valve
    assert permits.topics_of(record("CHANGE OF USE FROM OFFICE TO CLINIC")) == {"change_of_use"}


def summary(*records, stories=12):
    return permits.summarize(list(records), stories)


def test_summary_counts_years_floors_and_suites():
    s = summary(
        record("RELOCATE HEADS ON 3RD FLOOR", "Mechanical", "Fire Sprinkler", "1998-01-04"),
        record("NEW HEADS IN SUITE 820", "Mechanical", "Fire Sprinkler", "2021-07-09"),
        record("TI ON 5TH FLOOR", "Building", "Bldg-Alter/Repair"),
    )
    t = s["topics"]["sprinklers"]
    assert (t["count"], t["first"], t["latest"]) == (2, "1998", "2021-07-09")
    assert t["floors"] == {"3": 1, "8": 1} and t["suites"] == ["820"]
    assert s["total"] == 3 and "alarm" not in s["topics"]


# --- the rows they change ---------------------------------------------------------------------

def rows(s=None, records=None, space=None, plans=None, **facts):
    f = SpaceFacts(**facts)
    return {r.key: r for r in evidence.apply(build_checklist(f, 2026), f, s, records, space, plans)}


SUITE_820 = {"suite": "820", "floor": 8, "floor_label": "Floor 8"}


def test_sprinkler_and_alarm_rows_use_the_permits():
    s = summary(
        record("RELOCATE HEADS ON 3RD FLOOR", "Mechanical", "Fire Sprinkler", "1998-01-04"),
        record("ADD 2 STROBES IN SUITE 820", "Electrical", "Electrical", "2016-12-16"),
    )
    r = rows(s, space=SUITE_820, stories=12)
    assert r["sprinklers"].state == FOUND and "1 fire sprinkler permit, 1998 to 1998" in r["sprinklers"].evidence
    assert "None of them names floor 8" in r["sprinklers"].evidence
    assert r["alarm"].state == FOUND and "Suite 820 itself is named" in r["alarm"].evidence
    assert "not what is installed today" in r["alarm"].evidence
    disagree = rows(s, stories=12, has_sprinklers=False)["sprinklers"]
    assert disagree.state == ISSUE and "disagree" in disagree.evidence
    none = rows(summary(), stories=12)
    assert none["sprinklers"].state == REVIEW and none["alarm"].state == REVIEW


def test_permits_naming_two_stairs_settle_the_exits_row():
    exits = rows(summary(record("PLAN CHECK FOR STAIRWELL PRESSURIZATION FOR STAIR #1-2 AND #3")), stories=16)["exits"]
    assert exits.state == FOUND and "#1, #2, #3" in exits.evidence
    assert rows(summary(record("REPAIR STAIR #1 HANDRAIL")), stories=16)["exits"].state == NO_DATA


def test_city_zoning_map_overrides_costar_and_says_so():
    zone = rows(records={"zoning": [{"zone": "C2-2D-SN-CPIO"}]}, zone="C4", zone_recorded="LAC4")["zone"]
    assert zone.state == FOUND and "City Planning zoning map" in zone.evidence and "differs from the city's map" in zone.evidence
    industrial = rows(records={"zoning": [{"zone": "M2-1"}]}, zone="C2")["zone"]
    assert industrial.state == ISSUE and industrial.layer == "City Planning zoning map"


def test_county_height_fills_or_checks_the_height_row():
    county = {"county_height": {"feet": 306.0, "year": "2023"}}
    agree = rows(records=county, stories=19, height_ft=300.0)["height"]
    assert "agree within 30 ft" in agree.evidence and "LA County" in agree.layer
    clash = rows(records=county, stories=19, height_ft=190.0)["height"]
    assert clash.state == ISSUE and "differ by 116 ft" in clash.evidence
    alone = rows(records={"county_height": {"feet": 40.0, "year": "2023"}}, stories=3)["height"]
    assert alone.state == FOUND and "roughly 27 ft" in alone.evidence


def test_seismic_row_collects_retrofit_list_hazard_zones_and_permits():
    records = {"ndc": {"retrofit_due": "2042-12-05", "work_completion": None}, "liquefaction": True,
               "fault_zone": {"quad": "Beverly Hills"}}
    s = summary(record("SEISMIC RETROFIT PER ORDINANCE 183893", issued="2017-03-01"))
    row = rows(s, records, stories=4)["seismic"]
    assert row.state == REVIEW
    for words in ("non-ductile concrete retrofit list (retrofit due 2042-12-05)", "liquefaction zone",
                  "Alquist-Priolo fault zone (Beverly Hills map)", "1 seismic permit, 2017 to 2017"):
        assert words in row.evidence


def test_historic_designations_fill_the_historic_row():
    listed = rows(records={"historic": [{"kind": "National Register of Historic Places", "name": "Sample District",
                                          "number": "1", "status": "1S", "since": None}]})["historic"]
    assert listed.state == ISSUE and "Sample District" in listed.evidence and "Administrative Review" in listed.evidence
    monument = rows(records={"historic": [{"kind": "Historic-Cultural Monument", "name": "Sample Building",
                                            "number": "238", "status": "", "since": None}]})["historic"]
    assert "#238" in monument.evidence and "Conditional Use Permit" in monument.evidence
    clear = rows(records={"historic": []})["historic"]
    assert clear.state == REVIEW and "SurveyLA surveyed resources were not checked" in clear.evidence


def test_added_wording_follows_the_rules():
    s = summary(record("SEISMIC RETROFIT", issued="2017-03-01"),
                record("RELOCATE HEADS ON 3RD FLOOR", "Mechanical", "Fire Sprinkler", "1998-01-04"))
    records = {"zoning": [{"zone": "C2-1"}], "county_height": {"feet": 90.0, "year": "2023"}, "ndc": False,
               "liquefaction": True, "fault_zone": False,
               "historic": [{"kind": "Historic Preservation Overlay Zone", "name": "Sample", "number": "", "status": "", "since": None}]}
    for r in rows(s, records, SUITE_820, stories=12, height_ft=40.0).values():
        assert not BANNED.search(r.evidence), (r.key, BANNED.search(r.evidence).group(0))


def test_zone_reader_handles_the_new_code_and_specific_plan_zones():
    from secondstay.costar import base_zone

    assert base_zone("[HB5-SH1-5][CX3-FA][CPIO]") == "CX3-FA"
    assert base_zone("[LB-1-WH1-5].[IX2-FA]") == "IX2-FA"
    assert base_zone("MU(EC)-O") == "MU(EC)"
    downtown = rows(records={"zoning": [{"zone": "[HB5-SH1-5][CX3-FA][CPIO]"}]})["zone"]
    assert downtown.state == FOUND and "density district FA" in downtown.evidence
    plan = rows(records={"zoning": [{"zone": "NI(EC)"}]})["zone"]
    assert plan.state == ISSUE and "specific plan zone" in plan.evidence


def test_all_floor_plans_of_a_building_are_read_together():
    readings = [
        {"stairs": None, "elevators": None, "covers": "suite", "elevator_labels": []},
        {"stairs": 1, "elevators": 4, "covers": "part", "elevator_labels": ["passenger"], "floor_named": 3},
        {"stairs": 2, "elevators": 6, "covers": "floor", "elevator_labels": ["Freight"], "floor_named": 8},
    ]
    plans = evidence.plan_summary(readings)
    assert (plans["read"], plans["with_core"], plans["most_stairs"], plans["most_elevators"]) == (3, 2, 2, 6)
    assert plans["elevator_labels"] == ["FREIGHT", "PASSENGER"] and plans["floors_named"] == [3, 8]
    r = rows(plans=plans, stories=12)
    assert r["exits"].state == FOUND and "most stairwells drawn on one plan is 2" in r["exits"].evidence
    assert "up to 6 elevator cars, labelled freight, passenger" in r["elevator"].evidence
    one = rows(plans=evidence.plan_summary([{"stairs": 1, "covers": "floor"}]), stories=12)["exits"]
    assert one.state == ISSUE and "Whole-floor plans show 1 stairwells" in one.evidence
    assert evidence.plan_summary([]) is None


def _one_stair_scan(area):
    from secondstay.checklist import RoomFact

    return dict(stories=10, typical_floor_sqft=20000.0, floor_areas_sqft=[area],
                rooms=[RoomFact("Floor 1", "Staircase", 200.0), RoomFact("Floor 1", "Office", 800.0)],
                stair_links={"Floor 1": 1})


def test_one_stair_in_a_partial_scan_is_not_a_count_for_the_floor():
    partial = rows(**_one_stair_scan(3000.0))["exits"]
    assert partial.state == NO_DATA and "about 15% of a typical floor" in partial.evidence
    whole = rows(**_one_stair_scan(19000.0))["exits"]
    assert whole.state == ISSUE and "about 95% of a typical floor" in whole.evidence
    photos = SpaceFacts(stories=10, pano_reading={"panoramas": 12, "with_windows": 6, "stairs": 1, "exit_doors": 0, "indoor": True})
    seen = {r.key: r for r in evidence.apply(build_checklist(photos, 2026), photos)}["exits"]
    assert seen.state == NO_DATA and "part of the building only" in seen.evidence
    plan = rows(plans=evidence.plan_summary([{"stairs": 1, "covers": "floor"}]), **_one_stair_scan(3000.0))["exits"]
    assert plan.state == ISSUE  # a whole-floor plan with one stairwell still counts
