"""Normalized building model.

The Matterport adapter fills this in from a scan (rooms, their type, windows,
how they connect). Vexcel and CoStar adapters add exterior entrances and
building facts. Everything downstream works on this shape only.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Room:
    room_id: str
    floor: int
    room_type: str = "unknown"  # office, corridor, stairwell, restroom, lobby...
    label: Optional[str] = None  # door sign text, e.g. "301"; "" = no sign; None = not known
    has_window: Optional[bool] = None
    window_facing: Optional[str] = None  # N, E, S, W
    is_entrance: bool = False  # reachable from outside (from aerial imagery)

    def attributes(self) -> dict:
        """What a caller's camera could reveal about this room."""
        facing = self.window_facing
        if self.has_window is False:
            facing = "none"  # known to have no window, so no facing either
        return {
            "floor": self.floor,
            "room_type": self.room_type,
            "label": self.label,
            "has_window": self.has_window,
            "window_facing": facing,
        }


@dataclass
class Connection:
    a: str
    b: str
    distance_ft: float
    kind: str = "door"  # door, corridor, stairs, elevator


@dataclass
class Building:
    building_id: str
    name: str = ""
    address: str = ""
    rooms: dict = field(default_factory=dict)  # room_id -> Room
    connections: list = field(default_factory=list)

    def add_room(self, room: Room) -> None:
        self.rooms[room.room_id] = room

    def connect(self, a: str, b: str, distance_ft: float, kind: str = "door") -> None:
        if a not in self.rooms or b not in self.rooms:
            raise KeyError(f"Unknown room in connection {a} - {b}")
        self.connections.append(Connection(a, b, distance_ft, kind))

    def entrances(self) -> list:
        return [r.room_id for r in self.rooms.values() if r.is_entrance]
