"""Physical feasibility score for converting an office building to housing.

Scope: physical fit only. Zoning, financing and structural condition are out
of scope and must be said so wherever the score is shown.

The thresholds below are rule-of-thumb defaults for office-to-residential
conversion (shallow floor plates, generous floor heights and plenty of windows
convert well). They are tunable and should be checked with a practitioner
before being presented as fact.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

from .models import BuildingProfile


@dataclass
class Finding:
    criterion: str
    layer: str  # which data layer the evidence came from
    weight: float
    score: Optional[float]  # 0.0 - 1.0, None when the data is missing
    reason: str


@dataclass
class Assessment:
    building_id: str
    score: Optional[float]  # 0 - 100, None when nothing could be scored
    coverage: float  # share of total weight that had data, 0.0 - 1.0
    verdict: str
    dealbreakers: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    estimated_units: Optional[int] = None


def _ramp(value: float, bad: float, good: float) -> float:
    """Linear 0..1 between `bad` and `good`; works in either direction."""
    if bad == good:
        return 1.0 if value == good else 0.0
    t = (value - bad) / (good - bad)
    return max(0.0, min(1.0, t))


# Deeper than this from window to core and the middle of the floor has no
# daylight, which is the classic reason conversions fail.
DEPTH_GOOD_FT = 35.0
DEPTH_BAD_FT = 60.0

HEIGHT_BAD_FT = 9.5
HEIGHT_GOOD_FT = 12.0

FLOOR_AREA_GOOD_SQFT = 12_000.0
FLOOR_AREA_BAD_SQFT = 35_000.0

GAP_BAD_FT = 15.0
GAP_GOOD_FT = 60.0

# Unit count estimate assumptions.
RESIDENTIAL_EFFICIENCY = 0.80  # share of floor area that becomes apartments
AVERAGE_UNIT_SQFT = 750.0


def _depth(b: BuildingProfile):
    d = b.window_to_core_depth_ft
    if d is None:
        return None, "No interior depth measurement."
    return _ramp(d, DEPTH_BAD_FT, DEPTH_GOOD_FT), f"Window-to-core depth is {d:.0f} ft."


def _height(b: BuildingProfile):
    h = b.floor_to_floor_height_ft
    if h is None:
        return None, "No floor height measurement."
    return _ramp(h, HEIGHT_BAD_FT, HEIGHT_GOOD_FT), f"Floor-to-floor height is {h:.1f} ft."


def _windows(b: BuildingProfile):
    w = b.windowed_perimeter_share
    if w is None:
        return None, "No window coverage measurement."
    return _ramp(w, 0.3, 0.8), f"{w:.0%} of the perimeter has windows."


def _floor_area(b: BuildingProfile):
    a = b.typical_floor_area_sqft
    if a is None:
        return None, "No typical floor area."
    return (
        _ramp(a, FLOOR_AREA_BAD_SQFT, FLOOR_AREA_GOOD_SQFT),
        f"Typical floor is {a:,.0f} sq ft.",
    )


def _vacancy(b: BuildingProfile):
    v = b.vacancy_rate
    if v is None:
        return None, "No vacancy data."
    return _ramp(v, 0.1, 0.5), f"Vacancy is {v:.0%}."


def _daylight_gap(b: BuildingProfile):
    g = b.neighbor_gap_ft
    if g is None:
        return None, "No neighbor distance measurement."
    return _ramp(g, GAP_BAD_FT, GAP_GOOD_FT), f"Closest facing building is {g:.0f} ft away."


# (criterion, data layer, weight, scorer)
CRITERIA: list[tuple[str, str, float, Callable]] = [
    ("Floor plate depth", "Matterport", 0.30, _depth),
    ("Floor height", "Matterport", 0.15, _height),
    ("Window coverage", "Matterport", 0.15, _windows),
    ("Floor plate size", "CoStar", 0.10, _floor_area),
    ("Vacancy", "CoStar", 0.15, _vacancy),
    ("Daylight clearance", "Vexcel", 0.15, _daylight_gap),
]


def assess(b: BuildingProfile) -> Assessment:
    findings = []
    for criterion, layer, weight, scorer in CRITERIA:
        score, reason = scorer(b)
        findings.append(Finding(criterion, layer, weight, score, reason))

    known = [f for f in findings if f.score is not None]
    coverage = sum(f.weight for f in known)
    score = None
    if known:
        score = 100.0 * sum(f.weight * f.score for f in known) / coverage

    dealbreakers = []
    if b.window_to_core_depth_ft is not None and b.window_to_core_depth_ft > DEPTH_BAD_FT:
        dealbreakers.append(
            f"Floor plate is too deep ({b.window_to_core_depth_ft:.0f} ft from window to core)."
        )
    if b.floor_to_floor_height_ft is not None and b.floor_to_floor_height_ft < HEIGHT_BAD_FT:
        dealbreakers.append(
            f"Floor height is too low ({b.floor_to_floor_height_ft:.1f} ft)."
        )

    if score is None:
        verdict = "Not enough data"
    elif dealbreakers:
        verdict = "Poor fit"
    elif score >= 70:
        verdict = "Strong candidate"
    elif score >= 50:
        verdict = "Possible with redesign"
    else:
        verdict = "Poor fit"

    units = None
    if b.typical_floor_area_sqft and b.stories:
        units = int(
            b.typical_floor_area_sqft * b.stories * RESIDENTIAL_EFFICIENCY / AVERAGE_UNIT_SQFT
        )

    return Assessment(
        building_id=b.building_id,
        score=score,
        coverage=coverage,
        verdict=verdict,
        dealbreakers=dealbreakers,
        findings=findings,
        estimated_units=units,
    )


def rank(buildings: list[BuildingProfile]) -> list[Assessment]:
    """Best candidates first; buildings with no data go last."""
    results = [assess(b) for b in buildings]
    return sorted(results, key=lambda a: (a.score is None, -(a.score or 0.0)))
