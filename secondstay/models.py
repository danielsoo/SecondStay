"""Normalized building record that the scoring engine works on.

Adapters for the CoStar dump, the Matterport API and the Vexcel API each fill
in the fields they know about. Every field is optional: the scorer skips what
is missing and reports how much of the picture it actually had.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class BuildingProfile:
    building_id: str
    name: str = ""
    address: str = ""
    city: str = ""

    # CoStar building data
    year_built: Optional[int] = None
    stories: Optional[int] = None
    typical_floor_area_sqft: Optional[float] = None
    vacancy_rate: Optional[float] = None  # 0.0 - 1.0

    # Matterport interior scan
    window_to_core_depth_ft: Optional[float] = None
    floor_to_floor_height_ft: Optional[float] = None
    windowed_perimeter_share: Optional[float] = None  # 0.0 - 1.0

    # Vexcel aerial imagery
    neighbor_gap_ft: Optional[float] = None  # distance to the closest facing building
    parking_spaces: Optional[int] = None
