# Sightline

In an emergency, people inside a building often cannot say which floor or room
they are in. Sightline lets them open their phone camera, and an agent works
out where they are, tells responders, and routes responders to them.

Built at HackPrinceton on three data layers for the same address:

| Layer | What the agent uses it for |
|---|---|
| Matterport 3D scans | Rooms, floor plans, windows and scan imagery to match the caller's camera against |
| Vexcel aerial imagery | Entrances and exterior access; matching the view out of a window to a side of the building |
| CoStar building data | Floors, use and size of the building |

## How it works

1. **Caller opens the camera.** Frames are compared with the building's scan
   imagery to get a first set of candidate rooms.
2. **The agent asks for what would narrow it down most.** "Point your camera
   at the window." "Show me the sign next to the door."
3. **Location confirmed.** Floor and room appear on the commander's map.
4. **Responders get the fastest route** from an entrance, avoiding elevators
   and any areas marked as blocked.
5. **The commander decides** whether the caller stays or moves. The agent
   relays that instruction to the caller's phone. It never decides this itself.

## Status

- [x] Candidate-narrowing localizer (`sightline/localize.py`)
- [x] Responder routing (`sightline/routing.py`)
- [x] Incident state for caller and commander (`sightline/incident.py`)
- [ ] Matterport, Vexcel and CoStar data adapters
- [ ] Image similarity between camera frames and scan imagery
- [ ] Agent orchestration (deepagents)
- [ ] Caller web app and commander dashboard

## Development

```bash
pip install -e ".[dev]"
```

```bash
pytest
```
