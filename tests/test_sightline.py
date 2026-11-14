import pytest

from sightline import Building, Incident, Localizer, Room, fastest_route


def sample_building() -> Building:
    """Two floors. Each has a corridor and three offices; one stairwell and
    one elevator join the floors. The lobby is the only way in."""
    b = Building("demo")
    b.add_room(Room("lobby", 1, "lobby", "", is_entrance=True, has_window=True, window_facing="S"))
    b.add_room(Room("stairs1", 1, "stairwell", "", has_window=False))
    b.add_room(Room("stairs2", 2, "stairwell", "", has_window=False))
    b.add_room(Room("elev1", 1, "elevator", "", has_window=False))
    b.add_room(Room("elev2", 2, "elevator", "", has_window=False))
    for floor in (1, 2):
        b.add_room(Room(f"hall{floor}", floor, "corridor", "", has_window=False))
        b.add_room(Room(f"{floor}01", floor, "office", f"{floor}01", True, "N"))
        b.add_room(Room(f"{floor}02", floor, "office", f"{floor}02", True, "S"))
        b.add_room(Room(f"{floor}03", floor, "office", f"{floor}03", False))
        for n in ("01", "02", "03"):
            b.connect(f"hall{floor}", f"{floor}{n}", 20)
        b.connect(f"hall{floor}", f"stairs{floor}", 30, "corridor")
        b.connect(f"hall{floor}", f"elev{floor}", 10, "corridor")
    b.connect("lobby", "hall1", 15, "corridor")
    b.connect("stairs1", "stairs2", 25, "stairs")
    b.connect("elev1", "elev2", 5, "elevator")
    return b


# --- locating the caller --------------------------------------------------


def test_starts_with_no_idea():
    est = Localizer(sample_building()).estimate()
    assert not est.located
    assert est.confidence == pytest.approx(1 / 13)


def test_evidence_narrows_to_one_room():
    loc = Localizer(sample_building())
    loc.observe_attribute("room_type", "office")
    loc.observe_attribute("has_window", True)
    assert not loc.estimate().located
    loc.observe_attribute("window_facing", "N", reliability=0.97)
    loc.observe_attribute("floor", 2, reliability=0.97)
    est = loc.estimate()
    assert est.room_id == "201"
    assert est.located


def test_room_with_unknown_sign_is_not_ruled_out():
    b = sample_building()
    b.rooms["203"].label = None  # sign not captured in the scan
    loc = Localizer(b)
    loc.observe_attribute("label", "999", reliability=0.99)
    assert loc.estimate().room_id == "203"


def test_door_sign_alone_is_decisive():
    loc = Localizer(sample_building())
    loc.observe_attribute("label", "103", reliability=0.99)
    assert loc.estimate().room_id == "103"


def test_image_similarity_shifts_belief():
    loc = Localizer(sample_building())
    loc.observe_similarity({"202": 0.9, "102": 0.85, "201": 0.3})
    ranked = [room for room, _ in loc.estimate().candidates]
    assert ranked[:2] == ["202", "102"]


def test_next_question_is_one_that_splits_candidates():
    loc = Localizer(sample_building())
    # Only the two south-facing offices remain; they differ by floor and sign.
    loc.observe_attribute("room_type", "office", reliability=0.99)
    loc.observe_attribute("window_facing", "S", reliability=0.99)
    attribute, prompt = loc.next_question()
    assert attribute in ("floor", "label")
    assert prompt


def test_no_question_once_located():
    loc = Localizer(sample_building())
    loc.observe_attribute("label", "103", reliability=0.999)
    assert loc.next_question() is None


# --- routing responders ---------------------------------------------------


def test_route_uses_stairs_not_elevator():
    route = fastest_route(sample_building(), "201")
    assert route.rooms == ["lobby", "hall1", "stairs1", "stairs2", "hall2", "201"]
    assert route.distance_ft == 15 + 30 + 25 + 30 + 20


def test_blocked_stairs_means_no_route():
    assert fastest_route(sample_building(), "201", blocked={"stairs1"}) is None


def test_elevator_allowed_when_asked():
    route = fastest_route(sample_building(), "201", avoid_elevators=False)
    assert "elev1" in route.rooms


# --- the incident as a whole ----------------------------------------------


def test_incident_flow():
    incident = Incident(sample_building())

    # Before locating: the caller is asked for evidence, commander has no route.
    assert incident.commander_view()["route"] is None
    assert incident.caller_message() in set(
        __import__("sightline.localize", fromlist=["PROMPTS"]).PROMPTS.values()
    )

    incident.localizer.observe_attribute("label", "202", reliability=0.999)
    view = incident.commander_view()
    assert view["located"] and view["room_id"] == "202"
    assert view["route"][0] == "lobby" and view["route"][-1] == "202"
    assert "Wait for their instructions" in incident.caller_message()

    incident.instruct_stay()
    assert "Stay where you are" in incident.caller_message()

    incident.instruct_move("stairs2")
    assert "floor 2" in incident.caller_message()
