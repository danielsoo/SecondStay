import json

import pytest

from secondstay import floor_geometry as fg
from secondstay.costar import Building, Scan


def dxf(units=6, x2="4"):
    return f"0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n{units}\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n0\nLINE\n10\n0\n20\n0\n11\n{x2}\n21\n0\n0\nENDSEC\n0\nEOF\n"


def scope(tmp_path, monkeypatch):
    monkeypatch.setattr(fg, "SCAN_CACHE", tmp_path)
    monkeypatch.setattr(fg, "PLAN_CACHE", tmp_path)
    scan = Scan("SAMPLE0001", "Sample suite", suite="300", floor=3, floor_basis="the floor of that suite in the listing")
    b = Building(property_id=1, name="Sample Plaza", address="100 Example St", stories=4, scans=[scan])
    b.spaces = [{"id":11,"floor":3,"scans":[scan.model_id]}, {"id":12,"floor":4,"scans":[]}]
    (tmp_path / "SAMPLE0001.json").write_text(json.dumps({"floors":[{"label":"Floor 1"}], "rooms":[]}))
    (tmp_path / "SAMPLE0001_0.dxf").write_text(dxf())
    return b


def test_dxf_units_and_invalid_numbers():
    assert fg.dxf_lines(dxf()) == [[0,0,4,0]]
    assert fg.dxf_lines(dxf(2))[0][2] == pytest.approx(1.2192)
    assert fg.dxf_lines(dxf(0)) == []
    assert fg.dxf_lines(dxf(x2="nan")) == []


def test_single_scan_floor_uses_building_listing_number(tmp_path, monkeypatch):
    b = scope(tmp_path, monkeypatch)
    result = fg.geometry_for(b, 3, "11")
    assert result["available"] and result["floor"] == 3
    assert result["walls"] == [[0,0,4,0]]
    assert result["source"] == "Matterport DXF linework"
    assert "unverified" in result["note"]
    assert not fg.geometry_for(b, 4, "12")["available"]
    assert not fg.geometry_for(b, 1)["available"]
    with pytest.raises(ValueError):
        fg.geometry_for(b, 4, "11")


def test_multifloor_or_inferred_assignment_does_not_guess(tmp_path, monkeypatch):
    b = scope(tmp_path, monkeypatch)
    b.scans[0].floor_basis = "read from the suite number"
    assert not fg.geometry_for(b, 3)["available"]
    b.scans[0].floor_basis = "named in the scan's caption"
    (tmp_path / "SAMPLE0001.json").write_text(json.dumps({"floors":[{"label":"Floor 1"},{"label":"Floor 2"}]}))
    assert not fg.geometry_for(b, 3)["available"]


def test_suite_without_scan_cannot_use_a_neighboring_suites_scan(tmp_path, monkeypatch):
    b = scope(tmp_path, monkeypatch)
    b.spaces.append({"id":13,"floor":3,"scans":[]})
    assert not fg.geometry_for(b, 3, "13", "SAMPLE0001")["available"]


def test_floor_endpoint_and_modules(tmp_path, monkeypatch):
    import threading
    import urllib.request
    import urllib.error
    from http.server import ThreadingHTTPServer
    from secondstay import web

    b = scope(tmp_path, monkeypatch)
    monkeypatch.setattr(web.Handler, "buildings", {1:b})
    server = ThreadingHTTPServer(("127.0.0.1",0),web.Handler)
    thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(base+"/api/spaces/1/floor-geometry?floor=3&space=11") as r:
            assert json.load(r)["available"]
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(base+"/api/spaces/1/floor-geometry?floor=4&space=11")
        assert error.value.code == 400
        for name in ["floor_explorer","floor_motion","plan_trace","opening_layout"]:
            with urllib.request.urlopen(base+f"/static/{name}.mjs") as r:
                assert "javascript" in r.headers["Content-Type"]
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_opening_dimensions_room_boundaries_and_shared_edges():
    def edge(i, a, b, openings=None):
        return {"id": i, "type": "wall", "vertices": [{"position": {"x": x, "y": y}} for x,y in (a,b)], "openings": openings or []}
    opening = {"type": "window", "relativeCenter": .25, "width": 1.5, "height": 1.8, "lowerElevation": .7}
    walls = [edge("a",(0,0),(8,0),[opening]), edge("b",(8,0),(8,4)), edge("c",(8,4),(0,4)),edge("d",(0,4),(0,0))]
    model = {"rooms": [
        {"floor":{"label":"Local"},"classifications":[{"label":"Office"}],"dimensionEstimates":{"height":10,"area":300},"boundary":{"edges":walls}},
        {"floor":{"label":"Local"},"classifications":[{"label":"Void"}],"boundary":{"edges":[edge("a",(8,0),(0,0),[{**opening,"relativeCenter":.75}])]}},
        {"floor":{"label":"Another"},"boundary":{"edges":walls}}]}
    result = fg.interior_details(model,"Local")
    assert result["counts"] == {"windows":1,"doors":0,"rooms":1}
    assert len(result["wall_segments"]) == 4
    wall = result["wall_segments"][0]
    assert wall["height_m"] == pytest.approx(3.048)
    assert wall["openings"] == [{"kind":"window","start":1.25,"end":2.75,"height_m":1.8,"sill_m":.7}]
    assert result["rooms"][0]["polygon"] == [[0,0],[8,0],[8,4],[0,4]]
    assert fg.room_ring(walls[:3]) == []


def test_catalog_includes_all_floor_sources_and_keeps_unknown_floors_separate(tmp_path, monkeypatch):
    b = scope(tmp_path, monkeypatch)
    b.spaces[0].update(suite="300", plan_url="https://example.com/third.png")
    b.spaces[1].update(suite="400", plan_url="https://example.com/fourth.png")
    b.spaces.append({"id":13,"floor":3,"suite":"310","scans":[],"plan_url":"https://example.com/other.png"})
    b.scans.append(Scan("SAMPLE0002", "Suite 200", suite="200", floor=2, floor_basis="read from the suite number"))
    b.floor_plans = [
        {"url":"https://example.com/third.png","caption":"duplicate"},
        {"url":"https://example.com/first.png","caption":"1st floor plan"},
        {"url":"https://example.com/unknown.png","caption":"Suite 900"}]
    catalog = fg.source_catalog(b)
    floors = {f["floor"]:f["assets"] for f in catalog["floors"]}
    assert len(floors[3]) == 2
    assert floors[3][0]["geometry_available"]
    assert floors[3][0]["space_id"] == "11"
    assert floors[3][1]["plan_url"].endswith("other.png")
    assert floors[4][0]["plan_url"].endswith("fourth.png")
    assert not floors[4][0]["geometry_available"]
    assert floors[1][0]["plan_url"].endswith("first.png")
    assert floors[2] == []
    assert len(catalog["unassigned"]) == 2


def test_each_scan_on_a_floor_has_its_own_source(tmp_path, monkeypatch):
    b = scope(tmp_path, monkeypatch)
    b.scans.append(Scan("SAMPLE0002","Alternate scan",suite="300",floor=3,floor_basis="the floor of that suite in the listing"))
    b.spaces[0]["scans"].append("SAMPLE0002")
    sources = fg.source_catalog(b)["floors"][2]["assets"]
    assert len(sources) == 2
    assert len({s["key"] for s in sources}) == 2
    assert sources[0]["geometry_available"]
    assert not sources[1]["geometry_available"]


def test_archived_listing_plan_floor_enum_is_decoded_instead_of_read_as_floor_number():
    b = Building(property_id=2, name="Sample Tower", stories=30)
    b.floor_plans = [{"url":"https://example.com/archived.png", "caption":"Suite 310 floor 27", "source":"space"}]
    catalog = fg.source_catalog(b)
    assert len(catalog["floors"][2]["assets"]) == 1
    assert catalog["floors"][26]["assets"] == []
