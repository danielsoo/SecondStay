"""Synthetic integration checks across evidence, money inputs and HTTP."""

import json
import threading
from copy import deepcopy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from secondstay import finances, web
from secondstay.economics import spread
from test_web import building, payload


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setattr(finances.costar, "kit_dir", lambda: tmp_path)
    return payload(tmp_path, monkeypatch)


def test_defaults_unknown_income_and_partial_totals(context):
    result = finances.calculate(context, {})
    assert result["income"]["units"] == 64
    assert result["income"]["current_monthly_income"] is None
    assert result["scenarios"]["base"]["partial"]
    assert result["scenarios"]["base"]["payback"]["payback_years"] is None
    assert "unavailable" in result["rent"]["reason"]
    assert "comparables" not in result["rent"]


def test_session_edits_price_unknown_work_and_compare(context):
    options = {"scenario": "custom", "selected_keys": ["units.fitout"],
               "quantities": {"units.fitout": 1000},
               "prices": {"units.fitout": {"fixed": spread(0), "rate": spread(10, 20, 30)}},
               "income": {"units": 2, "monthly_rent_per_unit": spread(1500, 2000, 2500),
                          "current_monthly_income": spread(0)}}
    result = finances.calculate(context, options)
    custom = result["scenarios"]["custom"]
    assert custom["subtotal"] == spread(10000, 20000, 30000)
    assert custom["partial"] is False
    assert custom["payback"]["payback_years"]["typical"] > 0
    assert len(result["sensitivity"]["ranking"]) == 3
    line = next(x for x in custom["lines"] if x["key"] == "units.fitout")
    assert line["source"].startswith("Team assumption")
    assert line["quantity_basis"].startswith("Team assumption")
    assert line["excludes"] == "Scope and exclusions for this edited price need confirmation."
    assert finances.calculate(context, {})["scenarios"]["base"]["partial"]


def test_browser_roundtrip_preserves_unpriced_and_provenance(context):
    defaults = finances.calculate(context, {})["defaults"]
    options = {"prices": {k: {p: v[p] for p in ("fixed", "rate")} for k, v in defaults["prices"].items()},
               "globals": {k: {p: v[p] for p in ("low", "typical", "high")} for k, v in defaults["globals"].items()},
               "income": {k: v for k, v in defaults["income"].items() if k != "sources"}}
    result = finances.calculate(context, options)
    assert result["income"]["sources"] == defaults["income"]["sources"]
    bathroom = next(x for x in result["scenarios"]["base"]["lines"] if x["key"] == "units.bathroom")
    assert bathroom["source"].startswith("https://")


@pytest.mark.parametrize("options", [
    [], {"extra": 1}, {"scenario": []}, {"selected_keys": ["bogus"]}, {"selected_keys": [True]},
    {"income": {"units": True}}, {"income": {"units": 1.2}}, {"income": {"horizon_years": None}},
    {"income": {"monthly_rent_per_unit": spread(float("inf"))}},
    {"income": {"current_monthly_income": spread(100, 50, 10)}},
    {"globals": {"occupancy": spread(1.1)}}, {"globals": {"months_to_convert": {"low": 1}}},
    {"prices": {"units.fitout": {"fixed": spread(0), "rate": spread(-1)}}},
    {"quantities": {"units.fitout": float("nan")}}, {"quantities": {"unknown": 3}},
])
def test_invalid_inputs_are_rejected(context, options):
    with pytest.raises(ValueError):
        finances.calculate(context, options)


def test_suite_without_scan_never_prices_whole_building(context, monkeypatch):
    b = building()
    b.spaces = [{"id": 11, "suite": "300", "floor": 3, "floor_label": "Floor 3", "sqft": 4200,
                 "plan_url": "", "scans": []}]
    # Even an explicit scan from a different suite must not be used.
    data = web.space_payload(b, "MODEL0001", "11")
    assert data["scan"]["model_id"] == ""
    changes = {c["key"]: c for c in data["changes"]}
    assert changes["units.fitout"]["quantity"] == 4200
    assert changes["units.fitout"]["scope"] == "space"
    assert finances.calculate(data, {})["income"]["units"] == 6
    b.spaces[0]["sqft"] = None
    data = web.space_payload(b, "", "11")
    fitout = next(c for c in data["changes"] if c["key"] == "units.fitout")
    assert fitout["quantity"] is None
    assert finances.calculate(data, {})["income"]["units"] is None
    assert next(r for r in data["rows"] if r["key"] == "units")["state"] == "Not enough data"


def test_apartment_file_supplies_studio_rent(context, tmp_path, monkeypatch):
    folder = tmp_path / "data"
    folder.mkdir()
    records = [{"address": {"latitude": 34.0, "longitude": -118.0}, "monetaryUnit": 1,
                "apartmentModels": [{"numBeds": 0, "rentPricingType": 1, "minRent": rent, "maxRent": rent}]} for rent in (1000, 1500, 2000)]
    # Match the kit structure used by rents.apartment_rent.
    (folder / "apartment-listing.jsonl").write_text("\n".join(json.dumps(x) for x in records))
    result = finances.calculate(context, {})
    assert result["rent"]["count"] == 3
    assert result["income"]["monthly_rent_per_unit"]["typical"] == 1500


def test_http_cost_routes_validate_and_serve_assets(context, monkeypatch):
    monkeypatch.setattr(web.Handler, "buildings", {1: building()})
    monkeypatch.setattr(web, "space_payload", lambda *args: deepcopy(context))
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = HTTPConnection(*server.server_address)
    try:
        for path in ("/costs.js", "/costs.css", "/api/spaces/1/cost"):
            client.request("GET", path)
            response = client.getresponse()
            assert response.status == 200
            response.read()
        for body, status in (("{}", 200), ('{"income":{"units":false}}', 400), ("[]", 400), ("bad", 400)):
            client.request("POST", "/api/spaces/1/cost", body, {"Content-Type": "application/json"})
            response = client.getresponse()
            assert response.status == status
            response.read()
        client.request("GET", "/api/spaces/1/cost?space=999")
        response = client.getresponse()
        assert response.status == 404
        response.read()
    finally:
        client.close()
        server.shutdown()
        server.server_close()
        thread.join()
