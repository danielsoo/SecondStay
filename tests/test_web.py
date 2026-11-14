"""Screen payload tests. The building here is made up; no kit data or keys are used."""

import re
from pathlib import Path

from secondstay import web
from secondstay.checklist import NOTICE, STATES
from secondstay.costar import Building, Scan

BANNED = re.compile(
    r"\b(legal|illegal|compliant|approved|eligible|pass|passes|fail|fails|verdict)\b"
    r"|can be converted|cannot be converted",
    re.I,
)


def building():
    return Building(
        property_id=1, name="Sample Plaza", address="100 Example St", property_type="Office",
        latitude=34.0, longitude=-118.0, year_built=1985, zone_recorded="LAC2", stories=3,
        has_sprinklers=True, sprinkler_type="wet", rentable_sqft=40000.0, scans=[Scan("MODEL0001", "Tour")],
    )


def payload(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "SCAN_CACHE", tmp_path)
    monkeypatch.setattr(web, "OUTSIDE_CACHE", tmp_path)
    monkeypatch.delenv("MATTERPORT_TOKEN_ID", raising=False)
    monkeypatch.delenv("VEXCEL_API_KEY", raising=False)
    return web.space_payload(building())


def test_space_payload_without_keys_keeps_scan_rows_open(tmp_path, monkeypatch):
    data = payload(tmp_path, monkeypatch)
    rows = {r["key"]: r for r in data["rows"]}
    assert data["scan"]["loaded"] is False and "not set" in data["scan"]["error"]
    assert rows["units"]["state"] == "Not enough data" and rows["units"]["view"] == "scan"
    assert rows["age"]["view"] == "record" and rows["age"]["fields"][0]["value"] == 1985
    assert sum(data["counts"].values()) == len(rows) and set(data["counts"]) == set(STATES)
    assert "score" not in data


def test_list_payload_has_counts_and_no_model_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "OUTSIDE_CACHE", tmp_path)
    (space,) = web.list_payload([building()])["spaces"]
    assert space["scans"] == 1 and sum(space["counts"].values()) == 14


def test_next_steps_export_follows_the_wording_rules(tmp_path, monkeypatch):
    text = web.next_steps_markdown(payload(tmp_path, monkeypatch))
    assert NOTICE in text and "## Structural engineer" in text
    assert not BANNED.search(text.replace(NOTICE, ""))


def test_screen_text_follows_the_wording_rules():
    html = (Path(web.__file__).parent / "static" / "index.html").read_text()
    assert NOTICE in html
    visible = re.sub(r"<style>.*?</style>", "", html, flags=re.S).replace(NOTICE, "")
    assert not BANNED.search(visible), BANNED.search(visible).group(0)


def test_cached_imagery_fills_height_and_separation(tmp_path, monkeypatch):
    from secondstay import vexcel

    square = [(-118.0, 34.0), (-117.9995, 34.0), (-117.9995, 34.0005), (-118.0, 34.0005), (-118.0, 34.0)]
    outside = vexcel.Outside(height_ft=42, neighbor_gap_ft=12.0, footprint_sqft=9000, footprint=[square],
                             bbox=[-118.001, 33.999, -117.999, 34.001], captured="2026-07-03")
    (tmp_path / "1.json").write_text(vexcel.dump(outside))
    data = payload(tmp_path, monkeypatch)
    rows = {r["key"]: r for r in data["rows"]}
    assert data["outside"]["loaded"] is True
    assert rows["height"]["state"] == "Evidence found" and "about 42 ft" in rows["height"]["evidence"]
    assert rows["separation"]["state"] == "Needs professional review" and "12 ft" in rows["separation"]["evidence"]
    assert any(f["value"] == "about 42 ft" for f in rows["height"]["fields"])


def test_payload_lists_the_work_the_rules_call_for(tmp_path, monkeypatch):
    data = payload(tmp_path, monkeypatch)
    keys = {c["key"] for c in data["changes"]}
    assert {"seismic.evaluate", "sprinklers.verify_coverage", "units.fitout"} <= keys
    assert sum(data["change_counts"].values()) == len(data["changes"])
    assert data["top_occupied_ft"] == 20  # 3 stories, no height: two stories at 10 ft


def test_the_most_informative_cached_scan_opens_first(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(web, "SCAN_CACHE", tmp_path)
    monkeypatch.setattr(web, "OUTSIDE_CACHE", tmp_path)
    monkeypatch.delenv("VEXCEL_API_KEY", raising=False)
    b = building()
    b.scans = [Scan("EMPTY00001"), Scan("LABELLED01"), Scan("BIGGER0001")]
    room = {"floor": {"label": "Floor 1"}, "classifications": [{"label": "Office", "confidence": 0.9}],
            "dimensionEstimates": {"area": 200.0}}
    models = {
        "EMPTY00001": {"floors": [{"dimensionEstimates": {"area": 0}}], "rooms": []},
        "LABELLED01": {"floors": [{"dimensionEstimates": {"area": 900.0}}], "rooms": [room]},
        "BIGGER0001": {"floors": [{"dimensionEstimates": {"area": 5000.0}}], "rooms": []},
    }
    for model_id, model in models.items():
        (tmp_path / f"{model_id}.json").write_text(json.dumps(model))
    assert web.space_payload(b)["scan"]["model_id"] == "LABELLED01"
    assert web.space_payload(b, "BIGGER0001")["scan"]["model_id"] == "BIGGER0001"
