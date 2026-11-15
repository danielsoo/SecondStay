from secondstay import costar, vexcel, web


def test_city_view_lists_every_building_with_its_outline_and_counts(monkeypatch):
    k = 1 / 111320
    ring = [(-118.4 + x * k, 34.0 + y * k) for x, y in [(0, 0), (40, 0), (40, 1), (39.4, 1.5), (40, 2), (40, 30), (0, 30), (0, 0)]]
    spaces = [{"id": 1, "scans": ["m"], "plan_url": ""}, {"id": 2, "scans": [], "plan_url": "p"}]
    one = costar.Building(1, name="A", address="1 Main St", latitude=34.0, longitude=-118.4, stories=10, spaces=spaces,
                          available_sqft=5000)
    two = costar.Building(2, address="2 Main St", latitude=34.05, longitude=-118.3)
    outside = {1: vexcel.Outside(footprint=[ring], height_ft=150.0), 2: vexcel.Outside()}
    monkeypatch.setattr(web, "read_outside", lambda b, fetch=True: outside[b.property_id])
    monkeypatch.setitem(web._city_cache, "data", None)
    city = web.city_payload([one, two])
    a, b = city["buildings"]
    assert city["bbox"] == [round(-118.4 - web.REGION_PAD, 6), round(34.0 - web.REGION_PAD, 6),
                            round(-118.3 + web.REGION_PAD, 6), round(34.05 + web.REGION_PAD, 6)]
    assert (a["tours"], a["plans"], a["spaces"], a["height_ft"]) == (1, 1, 2, 150.0)
    assert len(a["footprint"][0]) < len(ring)  # drawn without tracing jitter
    assert b["footprint"] == [] and b["height_ft"] is None  # no imagery read: drawn as a plain block


def test_city_costs_are_computed_once_per_building(monkeypatch):
    calls = []
    monkeypatch.setattr(web, "market_minimum", lambda b, book: calls.append(b.property_id) or {"per_home": 45000.0})
    monkeypatch.setitem(web._city_costs, "data", None)
    buildings = [costar.Building(7), costar.Building(8)]
    first = web.city_costs(buildings)
    again = web.city_costs(buildings)
    assert first == {"7": {"per_home": 45000.0}, "8": {"per_home": 45000.0}} and again is first and calls == [7, 8]
