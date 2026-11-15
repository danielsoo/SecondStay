"""Income research tests. Communities, places and the model are made up; no network or API call is made."""

import json

import pytest

from secondstay import income_research as ir

HERE = (34.0, -118.0)
STATION = {"kind": "rail_station", "name": "Test Station", "lat": 34.003, "lon": -118.0}  # about 0.2 mi north
PLACES = [STATION, {"kind": "fire_station", "name": "Station 9", "lat": 34.0, "lon": -118.02},
          {"kind": "park", "name": "A park", "lat": 34.001, "lon": -118.0}, {"kind": "park", "name": "Far park", "lat": 34.05, "lon": -118.0}]


def community(n, miles_north, rent, sqft=500, style="high-rise", lifestyle="general market", vacancy=5, units=100):
    return {"id": n, "property_id": n, "lat": HERE[0] + miles_north / 69.0, "lon": HERE[1], "year": 2010, "units": units,
            "lifestyle": lifestyle, "style": style, "stories": 20, "class": "A", "rating": 4, "vacancy": vacancy,
            "rent_type": "market rent", "plans": [{"beds": 0, "sqft": sqft, "rent": rent}, {"beds": 1, "sqft": 700, "rent": rent * 1.3}]}


@pytest.fixture
def inputs(monkeypatch):
    index = [community(1, 0.1, 2500), community(2, 0.4, 2700), community(3, 1.0, 3000),
             community(4, 2.0, 2000, lifestyle="senior"), community(5, 5.0, 9000)]  # the last is out of range
    monkeypatch.setattr(ir, "apartment_index", lambda: tuple(index))
    monkeypatch.setattr(ir, "rental_listings", lambda: ({"lat": 34.01, "lon": -118.0, "rent": 3000, "leased": True, "beds": 1, "sqft": 600},))
    building = {"latitude": HERE[0], "longitude": HERE[1], "stories": 19, "year_built": 1971, "zone": "C2", "property_id": 1}
    return ir.gather(building, 300, places=PLACES)


def test_profile_reads_nearest_facilities_and_walkable_counts():
    p = ir.profile(HERE, PLACES)
    assert p["rail_station"]["name"] == "Test Station" and 0.15 < p["rail_station"]["miles"] < 0.25
    assert p["park"]["within_walk"] == 1 and p["police"]["miles"] is None


def test_gather_keeps_communities_in_range_with_their_neighbourhood(inputs):
    labels = {c["label"]: c for c in inputs["candidates"]}
    assert len(labels) == 4 and inputs["communities_in_range"] == 4
    assert all("profile" in c for c in labels.values())
    assert inputs["rentals"][0]["leased"] is True
    assert "rail station 0.2 mi" in ir.prompt(inputs)


def test_estimate_uses_only_chosen_plans_and_weights_partial_half(inputs):
    choice = {"comparables": [{"label": "C1", "match": "close", "reason": "tower nearby"},
                              {"label": "C2", "match": "partial", "reason": "tower, a little farther"}], "notes": "test"}
    result = ir.estimate(inputs, choice)
    rent = result["rent"]["monthly_rent_per_unit"]
    # C1: 2,500 for 500 sf and 3,250 for 700 sf (2,321 per 500 sf); C2: 2,700 and 3,510 (2,507). Senior and C3 are not used.
    assert rent["low"] <= rent["typical"] <= rent["high"] and 2300 <= rent["low"] and rent["high"] <= 2700
    assert result["rent"]["count"] == 4 and result["vacancy_percent"] == 5.0
    assert {c["label"] for c in result["comparables"]} == {"C1", "C2"}
    assert any(p["match"] == "not used" for p in result["points"])


def test_estimate_needs_three_plans(inputs):
    result = ir.estimate(inputs, {"comparables": [{"label": "C3", "match": "close", "reason": "only one"}], "notes": ""})
    assert result["rent"]["monthly_rent_per_unit"] is None and result["rent"]["reason"]


class FakeModel:
    name = "fake"

    def __init__(self, reply):
        self.reply = reply

    def invoke(self, messages):
        return type("Reply", (), {"content": self.reply})()


def test_choose_drops_unknown_labels_and_blocks_banned_wording(inputs):
    reply = json.dumps({"comparables": [{"label": "C1", "match": "close", "reason": "tower"},
                                        {"label": "C99", "match": "close", "reason": "made up"}], "notes": "ok"})
    assert [p["label"] for p in ir.choose(inputs, FakeModel(reply))["comparables"]] == ["C1"]
    banned = json.dumps({"comparables": [{"label": "C1", "match": "close", "reason": "approved building"}], "notes": ""})
    with pytest.raises(ValueError):
        ir.choose(inputs, FakeModel(banned))


def test_reading_waits_for_a_request_and_caches(tmp_path, monkeypatch, inputs):
    monkeypatch.setattr(ir, "RAW_DIR", tmp_path)
    building = {"latitude": HERE[0], "longitude": HERE[1], "stories": 19, "year_built": 1971, "zone": "C2", "property_id": 7}
    assert ir.reading(building)["read"] is False
    monkeypatch.setattr(ir, "fetch_places", lambda lat, lon: PLACES)
    reply = json.dumps({"comparables": [{"label": "C1", "match": "close", "reason": "tower"},
                                        {"label": "C2", "match": "close", "reason": "tower"}], "notes": "n"})
    result = ir.research(building, 300, model=FakeModel(reply))
    assert result["read"] and (tmp_path / "7.json").exists() and ir.reading(building)["rent"]["monthly_rent_per_unit"]
