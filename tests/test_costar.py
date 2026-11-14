"""CoStar adapter tests. Every record here is made up; no kit data is used."""

import json

from secondstay import costar
from secondstay.checklist import FOUND, ISSUE, NO_DATA, REVIEW, build_checklist
from secondstay.costar import base_zone, load_buildings, to_facts


def property_record(pid=1, **overrides):
    record = {
        "id": pid,
        "buildingName": "Sample Plaza",
        "propertyType": 5,
        "constructionStatus": 1,
        "primaryAddress": {
            "researchMarketId": 20, "streetNumber": "100", "streetName": "Example", "streetType": "St",
            "latitude": 34.0, "longitude": -118.0,
        },
        "constructionEvents": [{"eventType": 2, "year": 1985}, {"eventType": 4, "year": 2019}],
        "zoningDescription": "LAC2-1VL, Los Angeles",
        "numStoriesAboveGrade": 3,
        "hasSprinklers": True,
        "sprinklerType": 1,
        "rentableBuildingAreaSquareFeet": 40000.0,
        "propertyOffice": {"structural": {"elevators": [{"elevatorType": 1, "numElevators": 2}]}},
        "attachments": [
            {"videoExternalReferenceType": 36, "videoKey": "MODEL0001", "caption": "Suite tour"},
            {"videoExternalReferenceType": 36, "videoKey": "MODEL0001"},
            {"videoExternalReferenceType": 0, "attachmentType": 1, "attachmentUri": "https://example.com/a.jpg"},
        ],
    }
    record.update(overrides)
    return record


def write_kit(tmp_path, properties, listings=(), tenancies=()):
    data = tmp_path / "data"
    data.mkdir()
    for name, rows in (
        ("commercial-property", properties),
        ("commercial-listing-summary", listings),
        ("location-occupancy", tenancies),
    ):
        (data / f"{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return tmp_path


def load(tmp_path, monkeypatch, *args, **kwargs):
    monkeypatch.setenv("COSTAR_KIT_DIR", str(write_kit(tmp_path, *args, **kwargs)))
    monkeypatch.setattr(costar, "CACHE_PATH", tmp_path / "cache.json")
    return load_buildings()


def test_base_zone_reads_costar_zoning_text():
    assert base_zone("LAC2") == "C2"
    assert base_zone("C2-1VL-O, Los Angeles") == "C2"
    assert base_zone("[Q] M1-2D-SN") == "M1"
    assert base_zone("C1.5,1VL") == "C1.5"
    assert base_zone("LAR3") == "R3"
    assert base_zone("XYZ9*") is None
    assert base_zone(None) is None


def test_building_fields_come_from_the_property_record(tmp_path, monkeypatch):
    (b,) = load(tmp_path, monkeypatch, [property_record()])
    assert b.year_built == 1985  # construction complete, not the renovation
    assert (b.zone, b.stories, b.passenger_elevators) == ("C2", 3, 2)
    assert [s.model_id for s in b.scans] == ["MODEL0001"]
    assert b.aerial_urls == ["https://example.com/a.jpg"]
    assert b.address == "100 Example St"


def test_only_existing_la_offices_with_a_scan_are_listed(tmp_path, monkeypatch):
    houston = property_record(2)
    houston["primaryAddress"] = {**houston["primaryAddress"], "researchMarketId": 14}
    records = [
        property_record(1), houston,
        property_record(3, propertyType=11), property_record(4, constructionStatus=2),
        property_record(5, attachments=[]),
    ]
    assert [b.property_id for b in load(tmp_path, monkeypatch, records)] == [1]


def test_listings_and_tenancies_give_the_leasing_picture(tmp_path, monkeypatch):
    listings = [{
        "propertyId": 1, "listingStatus": 1,
        "forLeaseSummary": {"spaces": [
            {"propertyId": 1, "squareFeetMax": 6000, "rateHigh": 3.0, "rateBasis": 1},
            {"propertyId": 1, "squareFeetMax": 4000, "rateHigh": 30.0, "rateBasis": 2},
            {"propertyId": 1, "squareFeetMax": 9000, "dateOffMarket": "2025-01-01"},
        ]},
    }]
    tenancies = [
        {"propertyId": 1, "spaces": [{"squareFeetOccupied": 10000}]},
        {"propertyId": 1, "toDate": "2020-01-01", "spaces": [{"squareFeetOccupied": 30000}]},
    ]
    (b,) = load(tmp_path, monkeypatch, [property_record()], listings, tenancies)
    assert (b.available_sqft, b.available_spaces) == (10000, 2)
    assert b.asking_rent_per_sqft_year == 33.6  # (36 * 6000 + 30 * 4000) / 10000
    assert b.unaccounted_share == 0.75


def test_cache_round_trip(tmp_path, monkeypatch):
    first = load(tmp_path, monkeypatch, [property_record()])
    assert load_buildings() == first


def test_facts_feed_the_checklist(tmp_path, monkeypatch):
    (b,) = load(tmp_path, monkeypatch, [property_record()])
    rows = {r.key: r for r in build_checklist(to_facts(b), 2026)}
    assert rows["age"].state == FOUND
    assert rows["zone"].state == FOUND and 'recorded as "LAC2-1VL, Los Angeles"' in rows["zone"].evidence
    assert rows["elevator"].state == FOUND
    assert rows["sprinklers"].state == REVIEW and "wet" in rows["sprinklers"].evidence


def test_unmatched_zone_and_missing_sprinklers(tmp_path, monkeypatch):
    record = property_record(zoningDescription="XYZ9*", hasSprinklers=False, numStoriesAboveGrade=12)
    (b,) = load(tmp_path, monkeypatch, [record])
    rows = {r.key: r for r in build_checklist(to_facts(b), 2026)}
    assert rows["zone"].state == NO_DATA
    assert rows["sprinklers"].state == ISSUE
    assert rows["height"].state == ISSUE and "likely 75 ft or above" in rows["height"].evidence
    assert rows["elevator"].state == REVIEW and "Passenger elevators on record: 2" in rows["elevator"].evidence
