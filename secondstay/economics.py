"""What a conversion costs and whether it pays back.

Every number that drives the result is an input in `Assumptions`. There are no
built-in prices: unit costs and rents must come from a source (the CoStar data
for rents, a contractor or published cost guide for construction) and the UI
shows them as editable assumptions next to the result.

The output is a preliminary screen, not a quote. Zoning, permits, structural
work and hidden plumbing capacity are not covered.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ConversionPlan:
    """What would physically change, derived from the interior scan."""

    area_sqft: float
    units: int
    bathrooms_to_add: int
    # Total pipe run from the new bathrooms to the nearest existing wet wall
    # (restroom or kitchen). The main reason one space is cheap and another is not.
    plumbing_run_ft: float
    kitchens_to_add: int = 0


@dataclass
class Assumptions:
    # Construction
    fitout_cost_per_sqft: float
    cost_per_bathroom: float
    plumbing_cost_per_ft: float
    cost_per_kitchen: float
    months_to_convert: float
    # Income as housing
    monthly_rent_per_unit: float
    occupancy: float  # 0.0 - 1.0
    operating_cost_share: float  # share of rent spent on running the units
    # What the owner earns if they leave it as is (0 when it sits empty)
    current_monthly_income: float = 0.0
    # Work the LADBS bulletin calls for. Zero means "not included", for example
    # when the building already has sprinklers.
    sprinkler_cost_per_sqft: float = 0.0
    fire_alarm_cost_per_sqft: float = 0.0
    seismic_cost_per_sqft: float = 0.0
    permit_design_share: float = 0.0  # share of construction cost


@dataclass
class Economics:
    conversion_cost: float
    cost_breakdown: dict
    monthly_net_income: float
    monthly_gain_vs_today: float
    payback_years: Optional[float]  # None when it never pays back
    gain_over_horizon: float
    horizon_years: float


def load_assumptions(
    path: str,
    monthly_rent_per_unit: float,
    current_monthly_income: float = 0.0,
    level: str = "typical",
) -> Assumptions:
    """Read assumptions.json. `level` is "low", "typical" or "high".

    Rent and current income are not in the file: they come from the CoStar data.
    Raises if any value is still empty, so a result is never built on a blank.
    """
    import json

    with open(path) as f:
        data = json.load(f)
    fields = {}
    missing = []
    for key, entry in data.items():
        if key.startswith("_"):
            continue
        value = entry.get(level)
        if value is None:
            missing.append(key)
        fields[key] = value
    if missing:
        raise ValueError(f"assumptions.json has no {level} value for: {', '.join(missing)}")
    return Assumptions(
        monthly_rent_per_unit=monthly_rent_per_unit,
        current_monthly_income=current_monthly_income,
        **fields,
    )


def evaluate(plan: ConversionPlan, a: Assumptions, horizon_years: float = 5.0) -> Economics:
    """`horizon_years` is how long the owner expects the space to stay
    available for housing. A short horizon is what kills most conversions."""
    breakdown = {
        "fit-out": plan.area_sqft * a.fitout_cost_per_sqft,
        "bathrooms": plan.bathrooms_to_add * a.cost_per_bathroom,
        "plumbing runs": plan.plumbing_run_ft * a.plumbing_cost_per_ft,
        "kitchens": plan.kitchens_to_add * a.cost_per_kitchen,
        "sprinklers": plan.area_sqft * a.sprinkler_cost_per_sqft,
        "fire alarm": plan.area_sqft * a.fire_alarm_cost_per_sqft,
        "seismic": plan.area_sqft * a.seismic_cost_per_sqft,
    }
    breakdown["design and permits"] = sum(breakdown.values()) * a.permit_design_share
    cost = sum(breakdown.values())

    monthly_net = (
        plan.units * a.monthly_rent_per_unit * a.occupancy * (1.0 - a.operating_cost_share)
    )
    monthly_gain = monthly_net - a.current_monthly_income

    # Nothing is earned while construction is under way.
    lost_during_build = a.current_monthly_income * a.months_to_convert

    payback_years = None
    if monthly_gain > 0:
        months = a.months_to_convert + (cost + lost_during_build) / monthly_gain
        payback_years = months / 12.0

    earning_months = max(0.0, horizon_years * 12.0 - a.months_to_convert)
    gain = monthly_gain * earning_months - cost - lost_during_build

    return Economics(
        conversion_cost=cost,
        cost_breakdown=breakdown,
        monthly_net_income=monthly_net,
        monthly_gain_vs_today=monthly_gain,
        payback_years=payback_years,
        gain_over_horizon=gain,
        horizon_years=horizon_years,
    )
