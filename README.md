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

- [x] Scoring engine (`secondstay/scoring.py`)
- [x] Cost and payback model (`secondstay/economics.py`)
- [ ] CoStar, Matterport and Vexcel data adapters
- [ ] Agent orchestration (deepagents)
- [ ] Web UI with the Matterport viewer

## Development

```bash
pip install -e ".[dev]"
```

```bash
pytest
```
