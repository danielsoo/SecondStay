"""Fastest route for responders from an entrance to the caller."""

import heapq
from dataclasses import dataclass
from typing import Optional

from .models import Building


@dataclass
class Route:
    rooms: list  # room ids from entrance to target
    distance_ft: float
    entrance: str


def fastest_route(
    building: Building,
    target: str,
    blocked: Optional[set] = None,
    avoid_elevators: bool = True,
) -> Optional[Route]:
    """Shortest path from any entrance to `target`.

    `blocked` holds rooms responders cannot pass through (fire, collapse).
    Elevators are avoided by default because they are not used in a fire.
    Returns None when no route exists.
    """
    if target not in building.rooms:
        raise KeyError(f"Unknown room {target}")
    blocked = blocked or set()
    if target in blocked:
        return None

    graph: dict = {room_id: [] for room_id in building.rooms}
    for c in building.connections:
        if avoid_elevators and c.kind == "elevator":
            continue
        graph[c.a].append((c.b, c.distance_ft))
        graph[c.b].append((c.a, c.distance_ft))

    # Search outward from the target so one pass covers every entrance.
    distance = {target: 0.0}
    previous: dict = {}
    queue = [(0.0, target)]
    while queue:
        d, room = heapq.heappop(queue)
        if d > distance.get(room, float("inf")):
            continue
        for neighbor, length in graph[room]:
            if neighbor in blocked:
                continue
            nd = d + length
            if nd < distance.get(neighbor, float("inf")):
                distance[neighbor] = nd
                previous[neighbor] = room
                heapq.heappush(queue, (nd, neighbor))

    reachable = [e for e in building.entrances() if e in distance and e not in blocked]
    if not reachable:
        return None
    entrance = min(reachable, key=lambda e: distance[e])

    path = [entrance]
    while path[-1] != target:
        path.append(previous[path[-1]])
    return Route(rooms=path, distance_ft=distance[entrance], entrance=entrance)
