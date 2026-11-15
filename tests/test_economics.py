"""Hand-calculated financial cases, with synthetic inputs only."""

from itertools import product

import pytest

from secondstay.economics import LEVELS, NO_PAYBACK, evaluate, spread


def globals(**overrides):
    data = {"occupancy": {**spread(.9), "source": "Test"},
            "operating_cost_share": {**spread(.3), "source": "Test"},
            "months_to_convert": {**spread(6), "source": "Test"}}
    data.update(overrides)
    return data


def income(**overrides):
    data = {"units": 6, "monthly_rent_per_unit": spread(2000)}
    data.update(overrides)
    return data


def test_original_arithmetic_without_recommendation():
    result = evaluate(spread(400000), income(), globals())
    assert result["monthly_net_income"] == pytest.approx(spread(7560))
    assert result["monthly_gain"] == pytest.approx(spread(7560))
    assert result["payback_years"] == pytest.approx(spread((6 + 400000 / 7560) / 12))
    assert result["gain_over_horizon"] == pytest.approx(spread(7560 * 54 - 400000))
    assert "vacant: earns nothing today" in result["inputs"]["current_monthly_income"]["source"]
    short = evaluate(spread(400000), income(horizon_years=2), globals())
    assert short["gain_over_horizon"]["typical"] < 0
    assert short["payback_years"] == result["payback_years"]


def test_current_income_and_construction_loss():
    result = evaluate(spread(400000), income(current_monthly_income=spread(1000)), globals())
    assert result["payback_years"]["typical"] == pytest.approx((6 + 406000 / 6560) / 12)
    assert result["gain_over_horizon"]["typical"] == pytest.approx(6560 * 54 - 400000 - 6000)
    result = evaluate(spread(400000), income(current_monthly_income=spread(9000)), globals())
    assert result["payback_years"] == dict.fromkeys(LEVELS)
    assert result["reasons"]["payback_years"]["typical"] == NO_PAYBACK


def test_ranges_bound_all_input_corners():
    costs, rents, currents = spread(200000, 300000, 400000), spread(1000, 2000, 3000), spread(0, 500, 1000)
    settings = globals(occupancy={**spread(.7, .8, .9), "source": "Test"},
                       operating_cost_share={**spread(.2, .3, .4), "source": "Test"},
                       months_to_convert={**spread(3, 6, 9), "source": "Test"})
    result = evaluate(costs, income(monthly_rent_per_unit=rents, current_monthly_income=currents), settings)
    assert result["monthly_net_income"]["low"] == pytest.approx(6 * 1000 * .7 * .6)
    assert result["monthly_net_income"]["high"] == pytest.approx(6 * 3000 * .9 * .8)
    for choices in product(("low", "high"), repeat=6):
        c, r, now, occ, op, dur = choices
        point = evaluate(spread(costs[c]), income(monthly_rent_per_unit=spread(rents[r]), current_monthly_income=spread(currents[now])),
                         globals(occupancy={**spread(settings["occupancy"][occ]), "source": "Test"},
                                 operating_cost_share={**spread(settings["operating_cost_share"][op]), "source": "Test"},
                                 months_to_convert={**spread(settings["months_to_convert"][dur]), "source": "Test"}))
        for field in ("payback_years", "gain_over_horizon", "monthly_net_income", "monthly_gain"):
            assert result[field]["low"] - 1e-8 <= point[field]["typical"] <= result[field]["high"] + 1e-8


@pytest.mark.parametrize("units", [None, 0, -1, 1.5, True, float("nan")])
def test_invalid_units(units):
    result = evaluate(spread(1), income(units=units), globals())
    assert result["monthly_net_income"] is None
    assert result["reasons"]["payback_years"] == "unit count not available"


@pytest.mark.parametrize("rent", [None, spread(None), spread(5, 4, 3), spread(-1), spread(float("inf"))])
def test_invalid_rent(rent):
    result = evaluate(spread(1), income(monthly_rent_per_unit=rent), globals())
    assert result["reasons"]["payback_years"] == "rent per unit not available"


def test_missing_cost_duration_and_current_are_not_zero():
    result = evaluate(None, income(), globals())
    assert result["monthly_net_income"] is not None and result["payback_years"] is None
    assert result["reasons"]["payback_years"] == "cost total not available"
    result = evaluate(spread(1), income(), globals(months_to_convert={}))
    assert result["monthly_net_income"] is not None and result["payback_years"] is None
    assert "months_to_convert" in result["reasons"]["payback_years"]
    result = evaluate(spread(1), income(current_monthly_income=None), globals())
    assert result["monthly_gain"] is None
    assert result["reasons"]["payback_years"] == "current monthly income not available"


@pytest.mark.parametrize("horizon", [0, -1, None, float("nan"), "5", True])
def test_invalid_horizon_only_suppresses_horizon_gain(horizon):
    result = evaluate(spread(1), income(horizon_years=horizon), globals())
    assert result["payback_years"] is not None
    assert result["gain_over_horizon"] is None
    assert result["reasons"]["gain_over_horizon"] == "horizon must be a positive number of years"


def test_no_payback_at_only_adverse_endpoint_and_zero_occupancy():
    result = evaluate(spread(400000), income(current_monthly_income=spread(0, 100, 9000)), globals())
    assert result["payback_years"]["low"] < result["payback_years"]["typical"]
    assert result["payback_years"]["high"] is None
    result = evaluate(spread(400000), income(), globals(occupancy={**spread(0), "source": "Test"}))
    assert result["monthly_gain"] == spread(0)
    assert result["payback_years"] == dict.fromkeys(LEVELS)


def test_extreme_finite_values_do_not_export_infinity():
    import json
    result = evaluate(spread(1e308), income(monthly_rent_per_unit=spread(1e308)), globals())
    assert result["monthly_net_income"] is None
    json.dumps(result, allow_nan=False)
