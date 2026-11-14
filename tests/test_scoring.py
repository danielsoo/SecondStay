from secondstay import BuildingProfile, assess, rank


def good_building(**overrides):
    fields = dict(
        building_id="good",
        year_built=1965,
        stories=10,
        typical_floor_area_sqft=12_000,
        vacancy_rate=0.5,
        window_to_core_depth_ft=30,
        floor_to_floor_height_ft=12.5,
        windowed_perimeter_share=0.85,
        neighbor_gap_ft=80,
    )
    fields.update(overrides)
    return BuildingProfile(**fields)


def test_ideal_building_is_strong_candidate():
    a = assess(good_building())
    assert a.score == 100.0
    assert a.coverage == 1.0
    assert a.verdict == "Strong candidate"
    assert a.dealbreakers == []
    assert a.estimated_units == 128


def test_deep_floor_plate_is_dealbreaker():
    a = assess(good_building(window_to_core_depth_ft=75))
    assert a.verdict == "Poor fit"
    assert any("too deep" in d for d in a.dealbreakers)


def test_missing_data_lowers_coverage_not_score():
    a = assess(good_building(neighbor_gap_ft=None, vacancy_rate=None))
    assert a.score == 100.0
    assert round(a.coverage, 2) == 0.70


def test_no_data_at_all():
    a = assess(BuildingProfile(building_id="empty"))
    assert a.score is None
    assert a.verdict == "Not enough data"


def test_rank_orders_best_first_and_unknown_last():
    ranked = rank(
        [
            BuildingProfile(building_id="empty"),
            good_building(building_id="mid", window_to_core_depth_ft=50, vacancy_rate=0.2),
            good_building(building_id="top"),
        ]
    )
    assert [a.building_id for a in ranked] == ["top", "mid", "empty"]
