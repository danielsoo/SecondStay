"""The prices here are round numbers chosen to make the arithmetic easy to
check by hand. They are not real cost data."""

import pytest

from secondstay.economics import Assumptions, ConversionPlan, evaluate


def plan(**overrides):
    fields = dict(area_sqft=4_000, units=6, bathrooms_to_add=6, plumbing_run_ft=100, kitchens_to_add=6)
    fields.update(overrides)
    return ConversionPlan(**fields)


def assumptions(**overrides):
    fields = dict(
        fitout_cost_per_sqft=50,
        cost_per_bathroom=20_000,
        plumbing_cost_per_ft=200,
        cost_per_kitchen=10_000,
        months_to_convert=6,
        monthly_rent_per_unit=2_000,
        occupancy=0.9,
        operating_cost_share=0.3,
    )
    fields.update(overrides)
    return Assumptions(**fields)


def test_cost_and_payback():
    e = evaluate(plan(), assumptions(), horizon_years=5)
    assert e.conversion_cost == 200_000 + 120_000 + 20_000 + 60_000
    assert e.monthly_net_income == pytest.approx(6 * 2_000 * 0.9 * 0.7)
    # 6 months of construction, then 400,000 / 7,560 per month
    assert e.payback_years == pytest.approx((6 + 400_000 / 7_560) / 12)
    assert e.gain_over_horizon == pytest.approx(7_560 * 54 - 400_000)
    assert e.verdict.startswith("Convert")


def test_short_availability_kills_the_conversion():
    e = evaluate(plan(), assumptions(), horizon_years=2)
    assert e.gain_over_horizon < 0
    assert e.verdict.startswith("Do not convert")


def test_long_plumbing_runs_raise_cost():
    near = evaluate(plan(plumbing_run_ft=20), assumptions())
    far = evaluate(plan(plumbing_run_ft=400), assumptions())
    assert far.conversion_cost - near.conversion_cost == 380 * 200
    assert far.payback_years > near.payback_years


def test_space_already_earning_more_is_rejected():
    e = evaluate(plan(), assumptions(current_monthly_income=9_000))
    assert e.payback_years is None
    assert "no more than the space does today" in e.verdict
