"""Locate a caller inside a building by narrowing down candidate rooms.

This is not precise positioning. The agent keeps a probability for every room,
updates it with each piece of evidence from the caller's camera, and picks the
next thing to ask for that would split the remaining candidates best.

Evidence comes in two forms:
  * image similarity: how closely the camera frame resembles each room's
    scan imagery (scores supplied by an image embedder)
  * attribute observations: "there is a window", "the door sign says 301"
"""

import math
from dataclasses import dataclass
from typing import Optional

from .models import Building

LOCATED_THRESHOLD = 0.85

# What the agent says to the caller to get each kind of evidence.
PROMPTS = {
    "has_window": "Is there a window in the room? If so, point your camera at it.",
    "window_facing": "Point your camera out of the window so I can see what is outside.",
    "label": "Show me the sign or number next to the door.",
    "room_type": "Slowly turn around so I can see the whole room.",
    "floor": "Is there a floor number on the wall, by the stairs or the elevator? Show it to me.",
}


@dataclass
class Estimate:
    room_id: Optional[str]
    confidence: float
    located: bool
    candidates: list  # [(room_id, probability)], best first


class Localizer:
    def __init__(self, building: Building):
        if not building.rooms:
            raise ValueError("Building has no rooms")
        self.building = building
        n = len(building.rooms)
        self.belief = {room_id: 1.0 / n for room_id in building.rooms}
        self.asked: set = set()

    # --- evidence -----------------------------------------------------

    def observe_attribute(self, attribute: str, value, reliability: float = 0.9) -> None:
        """The camera showed that `attribute` is `value`.

        `reliability` is how much we trust the reading. A room where the
        attribute is not known could hold any of the values seen elsewhere
        in the building, so it is weighted as one chance among those.
        """
        self.asked.add(attribute)
        known = {
            room.attributes().get(attribute) for room in self.building.rooms.values()
        } - {None}
        unknown_factor = 1.0 / max(2, len(known))
        for room_id, room in self.building.rooms.items():
            actual = room.attributes().get(attribute)
            if actual is None:
                factor = unknown_factor
            elif actual == value:
                factor = reliability
            else:
                factor = 1.0 - reliability
            self.belief[room_id] *= factor
        self._normalize()

    def observe_similarity(self, scores: dict, temperature: float = 0.1) -> None:
        """`scores` maps room_id -> image similarity (higher is closer).

        Rooms with no score keep a neutral weight so that missing scan
        imagery does not rule a room out.
        """
        if not scores:
            return
        best = max(scores.values())
        for room_id in self.belief:
            if room_id in scores:
                self.belief[room_id] *= math.exp((scores[room_id] - best) / temperature)
            else:
                self.belief[room_id] *= math.exp(-1.0)
        self._normalize()

    def _normalize(self) -> None:
        total = sum(self.belief.values())
        if total <= 0:
            # Contradictory evidence: start over rather than divide by zero.
            n = len(self.belief)
            self.belief = {room_id: 1.0 / n for room_id in self.belief}
            return
        for room_id in self.belief:
            self.belief[room_id] /= total

    # --- reading the result -------------------------------------------

    def estimate(self, top: int = 5) -> Estimate:
        ranked = sorted(self.belief.items(), key=lambda kv: -kv[1])
        room_id, confidence = ranked[0]
        return Estimate(
            room_id=room_id,
            confidence=confidence,
            located=confidence >= LOCATED_THRESHOLD,
            candidates=ranked[:top],
        )

    # --- deciding what to ask next ------------------------------------

    def _entropy(self, weights) -> float:
        total = sum(weights)
        if total <= 0:
            return 0.0
        return -sum((w / total) * math.log(w / total) for w in weights if w > 0)

    def _expected_entropy(self, attribute: str) -> float:
        """Uncertainty left, on average, after learning this attribute."""
        groups: dict = {}
        for room_id, p in self.belief.items():
            value = self.building.rooms[room_id].attributes().get(attribute)
            groups.setdefault(value, []).append(p)
        return sum(sum(ps) * self._entropy(ps) for ps in groups.values())

    def next_question(self) -> Optional[tuple]:
        """Returns (attribute, prompt) for the most useful thing to ask,
        or None when located or nothing left would help."""
        if self.estimate().located:
            return None
        current = self._entropy(self.belief.values())
        best_attribute, best_remaining = None, current
        for attribute in PROMPTS:
            if attribute in self.asked:
                continue
            remaining = self._expected_entropy(attribute)
            if remaining < best_remaining - 1e-9:
                best_attribute, best_remaining = attribute, remaining
        if best_attribute is None:
            return None
        return best_attribute, PROMPTS[best_attribute]
