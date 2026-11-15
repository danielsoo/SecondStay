"""Synthetic changes and prices: no market records or real prices."""

import json
import random
import re
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from secondstay.changes import CATALOG, load_changes
from secondstay.costing import compare_scenarios, estimate, load_prices, print_prices, sensitivity
from secondstay.economics import LEVELS, NOTICE, entry_issue, spread
from secondstay.rents import apartment_rent, build_income, office_income, vacancy_indicators

SAMPLE = Path(__file__).parent / "fixtures/sample_changes.json"
BANNED = re.compile(r"\b(legal|illegal|compliant|approved|eligible|pass|passes|fail|fails|verdict)\b|can be converted|cannot be converted", re.I)


@pytest.fixture
def changes():
    return load_changes(SAMPLE)


@pytest.fixture
def prices():
    data = {key: {"unit": unit, "fixed": spread(10, 20, 30), "rate": spread(1, 2, 3),
                  "source": "Synthetic price", "confidence": "estimated"} for key, unit in CATALOG.items()}
    for key, values in {"soft_cost_share": spread(.1, .2, .3), "contingency": spread(.05, .1, .2),
                        "months_to_convert": spread(3, 6, 9), "occupancy": spread(.8, .9, 1),
                        "operating_cost_share": spread(.2, .3, .4)}.items():
        data[key] = {**values, "source": "Synthetic global", "confidence": "estimated"}
    return data


@pytest.fixture
def income():
    return {"units": 25, "monthly_rent_per_unit": spread(1800, 2000, 2200)}


def test_sample_scenarios_and_exact_removal(changes, prices, income):
    compared = compare_scenarios(changes, prices, income, selected_keys=[c.key for c in changes])
    results = compared["scenarios"]
    assert list(results) == ["base", "with_possible", "everything", "custom"]
    base, possible, everything = (results[name] for name in ("base", "with_possible", "everything"))
    assert len(base["not_in_scenario"]) == 3
    assert everything["lines"][-1]["status"] == "quantity unknown"
    assert everything["lines"][-1]["reason"].endswith("Not measured")
    assert len(everything["left_out"]) == 1
    for k in LEVELS:
        assert base["subtotal"][k] == sum(prices[c.key]["fixed"][k] + prices[c.key]["rate"][k] * c.quantity for c in changes[:2])
        assert base["total"][k] <= possible["total"][k] <= everything["total"][k]
        assert possible["difference_from_base"][k] == pytest.approx(possible["total"][k] - base["total"][k])
    reduced = estimate(changes, prices, income, "custom", selected_keys=[c.key for c in changes[1:]])
    for k in LEVELS:
        assert everything["total"][k] - reduced["total"][k] == pytest.approx(everything["lines"][0]["cost_with_allowances"][k])


def test_unknown_empty_mismatch_and_partition(changes, prices):
    unknown = replace(changes[0], key="future.work", quantity=None)
    result = estimate([unknown, *changes], prices, scenario="everything")
    assert result["lines"][0]["status"] == "not priced"
    assert "no price for this change key" in result["lines"][0]["reason"]
    assert "quantity unknown" in result["lines"][0]["reason"]
    assert result["total"] == estimate(changes, prices, scenario="everything")["total"]
    assert estimate(changes, {})["total"] is None
    assert estimate([], prices)["total"] is None
    prices[changes[0].key]["unit"] = "lump"
    line = estimate(changes, prices)["lines"][0]
    assert line["status"] == "not priced" and "sqft" in line["reason"] and "lump" in line["reason"]
    for scenario in ("base", "with_possible", "everything", "custom"):
        result = estimate(changes, prices, scenario=scenario)
        priced = sum(line["in_scenario"] and line["status"] == "priced" for line in result["lines"])
        assert priced + len(result["left_out"]) + len(result["not_in_scenario"]) == len(changes)
    custom = estimate(changes, prices, scenario="custom", selected_keys=["not.present"])
    assert custom["unknown_selection"] == [{"key": "not.present", "reason": "not in the change list"}]
    with pytest.raises(ValueError, match="base, with_possible, everything, custom"):
        estimate(changes, prices, scenario="other")


@pytest.mark.parametrize("quantity", [-1, float("inf"), float("nan"), "ten", True])
def test_bad_quantities_are_visible_and_json_safe(changes, prices, quantity):
    result = estimate([replace(changes[0], quantity=quantity)], prices)
    assert result["lines"][0]["status"] == "quantity unknown"
    assert result["total"] is None
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("entry", [None, [], "price", 7, {}, {"source": "x", "fixed": None},
                                    {"source": "x", "fixed": spread(0), "rate": "x"}])
def test_malformed_entries_never_crash(changes, prices, entry):
    prices[changes[0].key] = entry
    result = estimate(changes, prices)
    assert result["lines"][0]["status"] == "not priced"


@pytest.mark.parametrize("values,expected", [(spread(None), "price not filled in"),
    (spread(-1), "negative price"), (spread(3, 2, 1), "range out of order"),
    (spread(float("inf")), "finite number"), (spread(True), "finite number"), (spread("2"), "finite number")])
def test_price_validation(values, expected):
    assert expected in entry_issue({"source": "test", "fixed": spread(0), "rate": values}, "units.fitout")


def test_round_trip_preserves_everything(tmp_path, prices):
    prices.update(_about="notes", _version=2)
    prices["units.fitout"]["future_field"] = [1, "preserve"]
    prices["units.kitchen"]["rate"]["low"] = None
    path = tmp_path / "prices.json"
    path.write_text(json.dumps(prices), encoding="utf-8")
    book = load_prices(path)
    assert book.notes == {"_about": "notes", "_version": 2}
    assert "price not filled in" in book.issues["units.kitchen"]
    assert json.loads(print_prices(book)) == prices
    path.write_text(print_prices(book), encoding="utf-8")
    assert load_prices(path) == book
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError, match="prices.json"):
        load_prices(path)
    with pytest.raises(ValueError, match="missing.json"):
        load_prices(tmp_path / "missing.json")


def test_missing_globals_and_deliberately_unpriced(changes, prices):
    prices["soft_cost_share"]["high"] = None
    result = estimate(changes, prices)
    assert result["total"] is None and "soft_cost_share" in result["total_reason"]
    prices[changes[0].key]["unpriced_reason"] = "Site quote needed"
    assert estimate(changes, prices)["lines"][0]["reason"] == "Site quote needed"
    for key, value, reason in [("occupancy", 2, "share outside"), ("months_to_convert", -1, "negative duration")]:
        assert reason in entry_issue({**spread(value), "source": "test"}, key)


def test_zero_quantity_is_fixed_cost_and_repeated_keys_move_together(changes, prices):
    zero = replace(changes[0], quantity=0)
    result = estimate([zero], prices)
    assert result["lines"][0]["cost"] == prices[zero.key]["fixed"]
    repeated = estimate([zero, zero], prices, scenario="custom", selected_keys=[zero.key])
    for k in LEVELS:
        assert repeated["total"][k] == pytest.approx(result["total"][k] * 2)


def test_invariants_purity_and_order(changes, prices, income):
    before = deepcopy((changes, prices, income))
    reference = estimate(changes, prices, income, "everything")
    rng = random.Random(17)
    for _ in range(20):
        shuffled = rng.sample(changes, len(changes))
        result = estimate(shuffled, prices, income, "everything")
        assert result["total"] == pytest.approx(reference["total"], rel=1e-9)
        assert list(result["total"].values()) == sorted(result["total"].values())
        subset = [c.key for c in rng.sample(changes[:4], 2)]
        small = estimate(changes, prices, scenario="custom", selected_keys=subset)
        assert all(small["total"][k] <= reference["total"][k] for k in LEVELS)
    assert estimate(changes, prices, income, "everything") == reference
    assert (changes, prices, income) == before


def test_sensitivity_matches_hand_calculation(changes, prices, income):
    rows = sensitivity(changes, prices, income, count=100)["ranking"]
    assert len(rows) == 9
    assert [r["swing_years"] for r in rows] == sorted((r["swing_years"] for r in rows), reverse=True)
    row = next(r for r in rows if r["name"] == "sprinklers.install")
    monthly = 25 * 2000 * .9 * .7
    delta_cost = ((30 + 3 * 40000) - (10 + 40000)) * 1.2 * 1.1
    assert row["swing_years"] == pytest.approx(delta_cost / monthly / 12)
    assert sensitivity(changes, prices, income)["ranking"] == rows[:3]
    assert sensitivity(changes, {}, income)["ranking"] == []
    assert sensitivity(changes, prices, income, count=0)["ranking"] == []


def test_sensitivity_no_payback_end_ranks_first(changes, prices, income):
    income["current_monthly_income"] = spread(0, 100, 100000)
    result = sensitivity(changes, prices, income)
    assert result["ranking"][0]["name"] == "current_monthly_income"
    assert result["ranking"][0]["payback_at_high"] is None
    assert result["ranking"][0]["high_reason"] == "no payback at this value"


def listings():
    return [{"propertyId": 1, "primarySubmarketId": 9, "monetaryUnit": 1,
             "address": {"latitude": 0, "longitude": 0},
             "apartmentModels": [{"minRent": rent, "maxRent": rent, "rentPricingType": 1, "numBeds": 1}
                                  for rent in (1000, 2000, 3000, 4000)]}]


def office_spaces(*spaces):
    return [{"listingStatus": 1, "forLeaseSummary": {"spaces": list(spaces)}}]


def test_apartment_percentiles_normalization_and_filters():
    records = listings()
    records[0]["apartmentModels"] += [
        {"minRent": 0, "rentPricingType": 1, "numBeds": 1},
        {"minRent": 500, "rentPricingType": 2, "numBeds": 1},
        {"minRent": 900, "rentPricingType": 99, "numBeds": 1}]
    space = {"latitude": 0, "longitude": 0, "primarySubmarketId": 9}
    result = apartment_rent(records, space, bedrooms=1)
    assert result["monthly_rent_per_unit"] == spread(1750, 2500, 3250)
    assert result["count"] == 4 and sum(result["excluded"].values()) == 3
    assert apartment_rent(records, space, method="submarket")["count"] == 4
    assert apartment_rent(records, space, bedrooms=0)["monthly_rent_per_unit"] is None
    assert apartment_rent(records, space, min_comparables=5)["reason"] == "only 4 comparables; need 5"
    per_room = deepcopy(records[:1])
    per_room[0]["apartmentModels"] = [{"minRent": 500, "rentPricingType": 3, "numBeds": 2}]
    assert apartment_rent(per_room, space, min_comparables=1)["monthly_rent_per_unit"] == spread(1000)
    assert apartment_rent(records, {})["reason"] == "space coordinates not available"


def test_distance_radius_monotonic_and_property_join():
    records = listings()
    records[0]["address"]["longitude"] = .02
    space = {"latitude": 0, "longitude": 0}
    small = apartment_rent(records, space, radius_miles=1)
    large = apartment_rent(records, space, radius_miles=2)
    assert small["count"] == 0 and large["count"] == 4
    assert 1.3 < large["comparables"][0]["distance_miles"] < 1.5
    prop = {"id": 1, "primaryAddress": records[0].pop("address"), "propertyApartment": {"apartmentMeteringType": 2}}
    assert apartment_rent(records, space, properties=[prop], metering_type=2)["count"] == 4
    assert apartment_rent(records, space, properties=[prop], metering_type=1)["count"] == 0


@pytest.mark.parametrize("address", [{"city": "Synthetic"}, {"latitude": None, "longitude": 0},
                                    {"latitude": 100, "longitude": 0}])
def test_incomplete_listing_coordinates_use_joined_property(address):
    records = listings()
    records[0]["address"] = address
    space = {"latitude": 0, "longitude": 0}
    prop = {"id": 1, "primaryAddress": space}
    result = apartment_rent(records, space, properties=[prop])
    assert result["count"] == 4 and result["monthly_rent_per_unit"] == spread(1750, 2500, 3250)
    records[0]["address"] = {"latitude": 10, "longitude": 10}
    assert apartment_rent(records, space, properties=[prop])["count"] == 0


def test_office_income_and_vacancy():
    records = office_spaces(
        {"rateLow": 2, "rateHigh": 4, "rateBasis": 1, "squareFeetMax": 1000, "serviceType": 1},
        {"rateLow": 60, "rateBasis": 2, "squareFeetMax": 3000, "serviceType": 2},
        {"rateLow": 10000, "rateBasis": 2, "squareFeetMax": 9000, "dateOffMarket": "2020-01-01"})
    income = office_income(records, 1200, vacant=False)
    assert income["current_monthly_income"] == spread(2400, 5400, 6000)
    assert income["service_label"] == "mixed service types"
    assert office_income(records, None, vacant=True)["current_monthly_income"] == spread(0)
    assert office_income([], 1200, vacant=False)["current_monthly_income"] is None
    assert office_income(records, 1200, vacant=None)["reason"] == "vacancy assumption not available"
    tenancies = [{"spaces": [{"squareFeetOccupied": 2500}]}, {"spaces": []},
                 {"toDate": "2020-01-01", "spaces": [{"squareFeetOccupied": 99999}]}]
    result = vacancy_indicators(records, tenancies, 5000)
    assert result["marketed_area_sqft"] == 4000 and result["share_no_tenancy"] == .5
    assert result["tenancies_missing_area"] == 1
    assert vacancy_indicators(records, tenancies, 0)["share_no_tenancy"] is None
    assert vacancy_indicators(records, tenancies, 100)["share_no_tenancy"] == 0


def test_office_quotes_without_listing_areas_still_produce_income():
    records = office_spaces({"rateLow": 60, "rateBasis": 2})
    result = office_income(records, 1200, vacant=False)
    assert result["current_monthly_income"] == spread(6000)
    assert "Team assumption: unweighted median" in result["notes"]
    records[0]["forLeaseSummary"]["spaces"].append(
        {"rateLow": 2, "rateHigh": 4, "rateBasis": 1, "squareFeetMax": 1000})
    result = office_income(records, 1200, vacant=False)
    assert result["current_monthly_income"] == spread(2400, 4800, 6000)
    assert "some listing areas are missing" in result["notes"]


def assert_wording(value):
    if isinstance(value, dict):
        for key, item in value.items():
            assert not BANNED.search(key)
            assert_wording(item)
    elif isinstance(value, list):
        for item in value:
            assert_wording(item)
    elif isinstance(value, str) and value != NOTICE:
        assert not BANNED.search(value), value
        assert not value.startswith(("Convert", "Do not convert"))


def test_json_wording_and_real_price_book(changes, prices, income):
    inputs = build_income(listings(), {"latitude": 0, "longitude": 0}, units=25, vacant=True)
    results = [inputs, estimate(changes, prices, inputs), compare_scenarios(changes, prices, income),
               sensitivity(changes, prices, income), estimate(changes, load_prices(), income)]
    for result in results:
        assert json.loads(json.dumps(result, allow_nan=False)) == result
        assert result["notice"] == NOTICE
        assert_wording(result)
    data = json.loads(print_prices(load_prices()))
    assert set(load_prices().entries) == set(CATALOG)
    for key, unit in CATALOG.items():
        assert data[key]["unit"] == unit
        assert not entry_issue(data[key], key) or data[key].get("unpriced_reason")
        assert data[key]["confidence"] in ("observed", "estimated", "needs inspection")
        assert all(field in data[key] for field in ("published", "accessed", "source", "notes", "excludes"))
    assert_wording(data)
    assert not BANNED.search(Path("docs/cost-sources.md").read_text(encoding="utf-8").replace(NOTICE, ""))
