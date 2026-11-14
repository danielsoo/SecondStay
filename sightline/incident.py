"""One emergency: a caller being located, and the responders coming for them.

The commander decides whether the caller stays or moves. The agent only
relays that decision; it never issues one on its own.
"""

from dataclasses import dataclass, field
from typing import Optional

from .localize import Localizer
from .models import Building
from .routing import Route, fastest_route


@dataclass
class Incident:
    building: Building
    localizer: Localizer = None
    blocked: set = field(default_factory=set)
    instruction: Optional[str] = None  # "stay" or "move"
    move_target: Optional[str] = None

    def __post_init__(self):
        if self.localizer is None:
            self.localizer = Localizer(self.building)

    # --- commander side -----------------------------------------------

    def mark_blocked(self, room_id: str) -> None:
        self.blocked.add(room_id)

    def instruct_stay(self) -> None:
        self.instruction, self.move_target = "stay", None

    def instruct_move(self, room_id: str) -> None:
        if room_id not in self.building.rooms:
            raise KeyError(f"Unknown room {room_id}")
        self.instruction, self.move_target = "move", room_id

    def responder_route(self) -> Optional[Route]:
        """Route to the caller, once they are located."""
        estimate = self.localizer.estimate()
        if not estimate.located:
            return None
        return fastest_route(self.building, estimate.room_id, blocked=self.blocked)

    # --- caller side --------------------------------------------------

    def caller_message(self) -> str:
        """What the caller's phone shows right now."""
        estimate = self.localizer.estimate()
        if not estimate.located:
            question = self.localizer.next_question()
            if question:
                return question[1]
            return "Keep your camera steady and slowly look around the room."
        if self.instruction == "stay":
            return "Responders know where you are. Stay where you are. Help is coming to you."
        if self.instruction == "move":
            room = self.building.rooms[self.move_target]
            name = f"room {room.label}" if room.label else f"the {room.room_type}"
            return f"Responders are asking you to move to {name} on floor {room.floor}."
        return "I have found your location and sent it to responders. Wait for their instructions."

    def commander_view(self) -> dict:
        estimate = self.localizer.estimate()
        route = self.responder_route()
        return {
            "located": estimate.located,
            "room_id": estimate.room_id if estimate.located else None,
            "confidence": round(estimate.confidence, 3),
            "candidates": [(r, round(p, 3)) for r, p in estimate.candidates],
            "route": route.rooms if route else None,
            "route_distance_ft": route.distance_ft if route else None,
            "instruction": self.instruction,
            "blocked": sorted(self.blocked),
        }
