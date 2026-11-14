# SecondStay

An agent that tells commercial property owners which of their vacant spaces can
become housing, what the conversion would cost, and whether it pays back.

Built at HackPrinceton on three data layers for the same address:

| Layer | What the agent reads from it |
|---|---|
| CoStar building data | Vacancy, floor size, stories, age |
| Matterport 3D scans | Window-to-core depth, floor height, window coverage |
| Vexcel aerial imagery | Distance to neighboring buildings, parking |

## How it works

1. **Find** high-vacancy office buildings in the CoStar data.
2. **Inspect the inside** using the Matterport scan.
3. **Inspect the outside** using Vexcel aerial imagery.
4. **Score and explain**: a 0-100 feasibility score, the evidence behind each
   criterion, dealbreakers, and an estimated unit count.
5. **Cost and payback**: what has to be added (bathrooms, plumbing runs,
   kitchens), what that costs, the expected rental income, and whether it pays
   back within the time the space is available.

This is a preliminary screen. Zoning, permits, financing and structural
condition are out of scope, and all prices are editable assumptions.

## Status

- [x] Evidence checklist (`secondstay/checklist.py`)
- [x] CoStar adapter for Los Angeles offices (`secondstay/costar.py`, notes in `docs/costar-data-notes.md`)
- [x] Matterport Model API adapter (`secondstay/matterport.py`)
- [x] Checklist screen (`secondstay/web.py`)
- [x] Vexcel adapter: height and distance to neighbours (`secondstay/vexcel.py`); street frontage not yet
- [ ] Agent orchestration (deepagents), panorama inspection
- [x] Cost and payback model, phase 2 (`secondstay/economics.py`)

## Running the screen

Keep `costar-hackathon-kit` next to this folder (or set `COSTAR_KIT_DIR`), and put the keys in `.env`
(`MATTERPORT_TOKEN_ID`, `MATTERPORT_TOKEN_SECRET`, `MATTERPORT_SDK_KEY`, `VEXCEL_API_KEY`). Neither is committed.

```bash
python -m secondstay.web
```

To read every building's imagery and scans once, so the screen opens from cache and you can see which
buildings have the most evidence:

```bash
python -m secondstay.prefetch
```

## Development

```bash
pip install -e ".[dev]"
```

```bash
pytest
```
