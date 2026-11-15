# SecondStay

An evidence pre-check for owners of vacant commercial space in Los Angeles. For each published
requirement on converting offices to housing, it shows the rule, the evidence found in the data, how
strong that evidence is, and who confirms it. It then lists the work the rules call for.

> This is a preliminary evidence review, not a legal or code determination. Final decisions are made
> by LADBS and licensed professionals.

There is no score and no overall result. See `PRD.md` for the product and its wording rules.

Built at HackPrinceton on three data layers for the same address:

| Layer | What it supplies |
|---|---|
| CoStar building data | Year built, zone, stories, sprinklers, elevators, space on the market, tenancies |
| Matterport 3D scans | Floor area, room types and stairs where the scan has them |
| Vexcel aerial imagery | Footprint, roof height, distance to neighbouring structures, the top-down image |

## How it works

1. **Find** existing Los Angeles office buildings with a scan in the CoStar data.
2. **Link the layers**: each building to its Matterport scans and its Vexcel location.
3. **Gather evidence** per requirement and give it one of four states: Evidence found, Possible issue,
   Not enough data, Needs professional review.
4. **List the work** the published rules call for, each item with a quantity, a source and how certain
   it is (`docs/requirements-research.md`).
5. **Show it**: a 3D view of the building in its surroundings, the requirement list, the evidence for
   each row, and a next-steps list to hand to an architect.

6. **Explore cost and income** below the work list: compare called-for, possible, all and custom
   scenarios; edit quantities, prices, rent and project assumptions; see ranges, omissions and sources.
   Payback is withheld until rent and current income are supplied. Explicitly assume vacancy to use $0.
Who works on what is in `docs/work-split.md`.

## Status

- [x] Evidence checklist (`secondstay/checklist.py`)
- [x] CoStar adapter for Los Angeles offices (`secondstay/costar.py`, notes in `docs/costar-data-notes.md`)
- [x] Matterport Model API adapter (`secondstay/matterport.py`)
- [x] Work the rules call for (`secondstay/changes.py`, sources in `docs/requirements-research.md`)
- [x] Checklist screen with a 3D view of each building (`secondstay/web.py`, three.js)
- [x] Suites on the market by floor, each with its own floor plan and scan; the chosen floor opens in 3D
- [x] Vexcel adapter: height and distance to neighbours (`secondstay/vexcel.py`); street frontage not yet
- [x] Inside the scan: room types, windows and stairs from scan data; panoramas read by a vision model where there is none (`secondstay/panoramas.py`)
- [x] Street frontage from OpenStreetMap (`secondstay/streets.py`)
- [ ] Agent orchestration (deepagents)
- [x] Cost, rent, payback and sensitivity connected to the selected space (`secondstay/finances.py`)

The price book has two provisional sourced rates and 18 unpriced keys. Partial totals omit unpriced
work and must not be treated as full project budgets. See `docs/cost-sources.md`. Residential quantities
use the scan, then the selected suite, then the building when no suite is selected. Building-wide work
retains building quantities; it is not prorated to a suite. Edits are session-only Team assumptions.
Default rent uses studio asking-rent comparables within 3 miles from `data/apartment-listing.jsonl`
in the kit; missing data leaves rent blank. Restart after changing the kit location.

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
