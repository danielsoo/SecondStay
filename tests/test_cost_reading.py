from secondstay import cost_reading, finances
from secondstay.changes import CALLED_FOR, POSSIBLE, UNKNOWN, Change


def change(key, certainty, unit="sqft", quantity=1000.0):
    return Change(key=key, requirement=key.split(".")[0], title=key, certainty=certainty, quantity=quantity,
                  unit=unit, quantity_basis="test", scope="building", reason="On record.", source_url=None,
                  confirmed_by="Engineer")


def reading(**seen):
    base = {"sprinkler_heads": "unclear", "alarm_devices": "unclear", "exit_signs": "unclear", "water": "unclear",
            "windows": "some", "evidence": {}, "notes": ""}
    return {**base, **seen}


def test_visible_heads_turn_an_unknown_install_into_confirming_coverage():
    out, considered = cost_reading.apply([change("sprinklers.install", UNKNOWN)], reading(sprinkler_heads="seen"))
    assert [(c.key, c.certainty, c.unit) for c in out] == [("sprinklers.verify_coverage", POSSIBLE, "sqft")]
    assert "read from images" in out[0].reason
    assert {c["key"] for c in considered} == set(cost_reading.FIELDS)


def test_photos_never_remove_work_the_record_calls_for():
    out, considered = cost_reading.apply([change("sprinklers.install", CALLED_FOR)], reading(sprinkler_heads="seen"))
    assert out[0].key == "sprinklers.install" and out[0].certainty == CALLED_FOR
    assert "disagree" in out[0].reason
    assert "stays in" in next(c for c in considered if c["key"] == "sprinkler_heads")["effect"]


def test_alarm_devices_and_water_notes():
    out, considered = cost_reading.apply([change("fire_alarm.install", UNKNOWN)],
                                         reading(alarm_devices="seen", water="kitchenette", windows="few"))
    assert out[0].certainty == POSSIBLE and out[0].title.startswith("Extend")
    notes = {c["key"]: c["effect"] for c in considered}
    assert "still needs its own kitchen" in notes["water"] and "fewer homes" in notes["windows"]


def test_unclear_photos_leave_the_work_list_unchanged():
    before = [change("sprinklers.install", UNKNOWN), change("fire_alarm.install", UNKNOWN)]
    out, _ = cost_reading.apply(before, reading())
    assert out == before


def test_minimum_lists_called_for_work_and_what_still_needs_a_quote():
    line = lambda title, certainty, status, cost=None: {"key": title.lower(), "title": title, "certainty": certainty,
        "status": status, "quantity": 2, "unit": "each", "cost": cost, "quantity_basis": "test", "reason": "no price",
        "source": "https://example.org", "rate": None}
    base = {"total": {"low": 10.0, "typical": 15.0, "high": 20.0}, "lines": [
        line("Bathrooms", "called_for", "priced", {"low": 8.0, "typical": 12.0, "high": 16.0}),
        line("Kitchens", "called_for", "not priced"),
        line("Smoke control", "possible", "not priced")]}
    m = finances.minimum(base)
    assert m["low"] == 10.0 and [i["title"] for i in m["included"]] == ["Bathrooms"]
    assert [i["title"] for i in m["to_quote"]] == ["Kitchens"] and m["possible"] == 1


def test_photos_are_read_only_when_asked(monkeypatch):
    assert finances.photo_reading({"scan": {"model_id": ""}})["available"] is False
    monkeypatch.setattr(cost_reading, "cached", lambda scan: None)
    monkeypatch.setattr(finances, "photo_check_blocked", lambda: "")
    calls = []
    monkeypatch.setattr(cost_reading, "read", lambda scan: calls.append(scan) or reading(sprinkler_heads="seen"))
    assert finances.photo_reading({"scan": {"model_id": "SAMPLE0001"}})["read"] is False and not calls
    done = finances.photo_reading({"scan": {"model_id": "SAMPLE0001"}}, read_now=True)
    assert calls == ["SAMPLE0001"] and done["read"] and done["reading"]["sprinkler_heads"] == "seen"


def test_photo_check_says_up_front_when_it_cannot_run(monkeypatch):
    monkeypatch.setattr(cost_reading, "cached", lambda scan: None)
    monkeypatch.setenv("SECONDSTAY_OFFLINE", "1")
    monkeypatch.setattr(cost_reading, "read", lambda scan: (_ for _ in ()).throw(AssertionError("must not read")))
    result = finances.photo_reading({"scan": {"model_id": "SAMPLE0001"}}, read_now=True)
    assert result["can_read"] is False and result["read"] is False and "public demo" in result["reason"]


def test_wording_stays_within_the_review_rules():
    from secondstay.agent import BANNED
    import inspect
    assert not BANNED.search(cost_reading.QUESTIONS + inspect.getsource(cost_reading.apply))
