# SecondStay

**Could this office become homes? A first check for Los Angeles.**

SecondStay is an evidence pre-check for owners of vacant office space in Los Angeles. For each of the
14 published requirements for converting offices to housing, it shows the rule, the evidence found in
the data, how strong that evidence is, and who confirms it. It then lists the least work the rules
call for, prices it from real Los Angeles permits, and estimates what the homes could rent for.

> This is a preliminary evidence review, not a legal or code determination. Final decisions are made
> by LADBS and licensed professionals.

There is no score and no overall result. Before an owner pays an architect, SecondStay shows what the
data already says about each requirement, and exactly what is left to verify.

Built at HackPrinceton Fall 2026.

## Contents

- [What you see](#what-you-see)
- [Data sources](#data-sources)
- [The 14 requirements](#the-14-requirements)
- [How a building is checked](#how-a-building-is-checked)
- [Cost and income](#cost-and-income)
- [Evidence agent (deepagents)](#evidence-agent-deepagents)
- [Floors, suites and interior models](#floors-suites-and-interior-models)
- [Tiger Data store](#tiger-data-store)
- [Running it](#running-it)
- [Tests](#tests)
- [Code map](#code-map)
- [Data handling and wording rules](#data-handling-and-wording-rules)
- [Hackathon tracks](#hackathon-tracks)
- [Further documents](#further-documents)

## What you see

| Screen | What it shows |
| --- | --- |
| Landing | A map of every listed Los Angeles office building in the collection, the evidence behind the tool, and how it reasons |
| Building list | Each building with its photo, space on the market, stories and floors drawn in 3D; filters for buildings and suites with a Matterport tour |
| Building page | Headline figures (least cost the published rules call for, possible rent, least cost to open one home, requirements with evidence) and a 3D view of the building in its surroundings |
| Requirement list | The 14 rows, each with its evidence state; selecting a row opens its evidence |
| Evidence views | Per requirement: 3D height view with level planes, separation and access views with dimension bars, permit floors in 3D, permit timelines, permits per year, age, units and stay graphics, seismic and historic cards, real CoStar photos |
| Floor view | Floors pulled apart in 3D; a floor opens on its scan or traced plan, with a ledger of what each part of the floor is and why it is or is not drawn |
| Walk-through | The Matterport tour of the selected suite |
| Evidence agent panel | The latest stored evidence check, step by step, marking steps a sub-agent ran; **Run again** starts a new one |
| Next steps | A Markdown export of open items grouped by the professional who confirms them |

## Data sources

| Kind | Source | What it supplies |
| --- | --- | --- |
| Industry | CoStar | Building records, space on the market, tenancies, floor plans, asking rents, nearby apartment communities |
| Industry | Matterport | 3D scans of suites on the market: floor area, rooms, stairs, windows, 360° photos |
| Industry | Vexcel | Aerial imagery, roof and ground elevation (DSM), footprint, distance to neighbouring buildings |
| Government | LA Department of Building and Safety | Building, mechanical and electrical permits since the 1990s, certificates of occupancy, the non-ductile concrete list |
| Government | LA City Planning | Zoning map, Historic-Cultural Monuments, HPOZ districts, national and state registers |
| Government | LA County (LARIAC) | Surveyed building outlines and measured roof heights |
| Government | California Geological Survey | Liquefaction zones and Alquist-Priolo fault zones |
| Open data | OpenStreetMap | Street frontage for fire access; transit, schools, parks and groceries near each building |

The three sponsor layers (CoStar, Matterport, Vexcel) describe the same address from inside, from the
market and from above. Public records are joined by parcel number or location, never by name.

## The 14 requirements

| Requirement | Confirmed by |
| --- | --- |
| Building age | LADBS building records |
| Zone | City zoning lookup (ZIMAS) |
| Unit count | Architect's layout |
| Height | Survey or building records |
| Exits per story | Architect and LADBS plan check |
| Escape openings for sleeping rooms | Architect on site |
| Fire separation distance | Survey |
| Fire access and exit discharge | Fire Department review |
| Elevator | LADBS plan check |
| Stay length | City Planning guidance |
| Sprinklers | Fire protection engineer |
| Fire alarm | Fire protection engineer |
| Seismic | Structural engineer |
| Historic status | Office of Historic Resources |

Each row gets one of four states, and only these four:

| State | Meaning |
| --- | --- |
| Evidence found | The data is consistent with the requirement |
| Possible issue | The data suggests the requirement may not be met, or two sources disagree |
| Not enough data | The data we have cannot answer it |
| Needs professional review | Data cannot answer this kind of requirement |

Sources for every rule are in `docs/requirements-research.md`.

## How a building is checked

1. **Find the building.** A CoStar record gives the address, parcel number, age, zone, stories and the
   space on the market.
2. **Link the layers.** Each building is linked to its Matterport scans and its Vexcel location.
3. **Gather the records.** Code pulls permits, zoning, seismic zones, measured height, scans, aerial
   imagery and streets. No model is involved in this step.
4. **Read what records miss.** A vision model reads twelve 360° photos per scan, and the Matterport
   plan, for sprinkler heads, alarms, exits and windows. Those answers are labelled **read from images,
   not measured**.
5. **Check every rule.** `checklist.py` gives each requirement its state from CoStar, Matterport and
   Vexcel; `evidence.py` then lays the public records onto the rows they speak to (zoning map over
   CoStar zoning text, county height against Vexcel, permits for sprinklers, alarms, elevators, stairs
   and seismic work, historic designations).
6. **List the work.** `changes.py` turns the rows into the change list: each item with a quantity, a
   source and how certain it is.
7. **Hand it to a professional.** The screen shows the evidence behind each row and exports the open
   items as next steps.

## Cost and income

**Least the published rules call for.** `la_costs.py` builds a Los Angeles price book from LADBS
permits. Code fetches candidate permits for each kind of work, a language model reads each
description and says what the job was and how many units it covers, and code takes the 25th, 50th and
75th percentile of the declared values as low, typical and high (`la_permit_prices.json`). Declared
values are what applicants state for permit fees and run below final cost, so the figures suit a
minimum. `cost_reading.py` adjusts the change list from the scan photos with fixed, visible rules
(visible sprinkler heads turn "install sprinklers" into "confirm and adapt coverage"); photos never
remove work the record calls for. `costing.py` prices the change list, and `finances.py` connects it
to the screen, where quantities, prices, rent and project assumptions can be edited for one
calculation.

**Could rent for.** `income_research.py` gathers CoStar apartment communities within 3 miles,
nearby rental listings and public facilities from OpenStreetMap. A model chooses which communities are
close or partial comparables and never names a figure; code scales each chosen floor plan's asking
rent to a planned 500 sq ft home and takes the 25th, 50th and 75th percentiles. Asking rents are not
achieved rents.

**Least to open one home.** Building-wide work plus the work for a single home, so an owner can see
the smallest first step.

`economics.py` keeps every figure a range and gives simple payback only when rent and today's income
are both known. Sources and assumptions are in `docs/cost-sources.md` and `assumptions.json`.

## Evidence agent (deepagents)

`secondstay/agent.py` builds the evidence review with LangChain **deepagents** (`create_deep_agent`).

| Agent | Tools | Job |
| --- | --- | --- |
| Lead | `evidence_step`, `write_todos`, `task` | Plans, reads CoStar, the scan, Vexcel and streets, cross-checks sources and records the review |
| `city-records-reader` | `city_step` | Reads LADBS permits, zoning, county height, seismic and historic records, then checks which rows they filled |
| `image-reader` | `image_step` | Reads the scan's plan and panoramas for windows, stairs, elevators and EXIT signs, read from images, not measured |

- Every evidence tool takes one validated action for a scope fixed before the model starts, so the
  model cannot pick another building or scan.
- When sources disagree (for example CoStar's recorded height against Vexcel's roof height), the lead
  must re-read both and cross-check again; a disagreement that remains stays visible as a Possible
  issue.
- `write_review` refuses to record until the required evidence is gathered and cross-checked. Street
  evidence read before the Vexcel footprint does not count.
- The checklist and change-list functions decide the states; model prose cannot overwrite them.
- Guardrails: a tool allowlist hides filesystem and shell tools from the lead and both sub-agents,
  no general-purpose sub-agent is created, a run is limited to 24 evidence actions shared by all
  three agents and two reads per source, and banned words are rejected.
- Every building is checked once ahead of time. Finished runs are saved under the ignored
  `data/raw/agent_runs/` and in Tiger Data, and the panel opens on the latest check straight away;
  **Run again** starts a new one when the records change. Set `SECONDSTAY_OFFLINE=1` to use cached
  data and stored checks only.

Run up to five buildings from the command line with `python -m secondstay.agent <building ids>`, or
one suite with `--space <space id>`. Do not put real identifiers in checked-in files.

## Floors, suites and interior models

- Suites on the market are listed by floor, each with its own CoStar plan and Matterport tour.
  Leased space is not shown; a suite without a tour is never read as the owner not intending to
  convert.
- The floor view separates floors in 3D. Measured Matterport scans keep metre dimensions and their
  recorded openings cut real holes in the walls.
- Plans without printed lengths can be hand-traced into `plan_relative` models: drawing proportions
  only, no physical scale, labelled as drafts and kept apart from the measured building stack. Their
  area in the floor ledger is CoStar's listed size for the suite, never a figure read off the drawing.
- Three control points place a model in its floor frame; a discrepancy above 0.5 m withholds the
  placement. Areas with no layout on record show a 10 ft reference grid, never invented rooms.
- Vexcel DSM surface heights are drawn as colourless see-through shells over the flat aerial photo;
  trees and neighbours never carry photo texture.

Details: `docs/floor-explorer.md`.

## Tiger Data store

`data/raw/` holds licensed and private material and is never committed. A Tiger Data service
(TimescaleDB on PostgreSQL) keeps it, so a fresh checkout can be restored, and serves permit history as
time series.

| Command | What it does |
| --- | --- |
| `python -m secondstay.tiger push` | Uploads new or changed files under `data/raw/` (one row per file: path, sha256, bytes) |
| `python -m secondstay.tiger restore` | Writes stored files missing locally; a local file that differs is kept unless `--force` is given |
| `python -m secondstay.tiger permits` | Loads the permit hypertables, compresses them and refreshes the yearly continuous aggregates |
| `python -m secondstay.tiger runs` | Stores the finished evidence-agent runs saved under `data/raw/agent_runs/` |
| `python -m secondstay.tiger status` | Local against stored files, row counts and compression per hypertable |

- `building_permits` (about 30,000 LADBS permits matched by parcel) and `city_cost_permits` (about
  9,000 city-wide cost permits) are hypertables in compressed columnar form, about 70 to 75% smaller.
- `building_permits_yearly` and `city_cost_permits_yearly` are continuous aggregates. The permit
  evidence views draw all permits on the parcel by year from the first one
  (`/api/spaces/<id>/permit-years.json`).
- `agent_runs` keeps every finished evidence-agent run (events, checklist and report as JSON), so
  each building page opens on its latest check without running the model again.
- Without `TIGER_DATABASE_URL` the chart is left out, checks are read from `data/raw/agent_runs/`, and
  every other view reads `data/raw/` as before.

Details: `docs/tiger-data.md`.

## Running it

Requirements: Python 3.11 or newer, the CoStar hackathon kit, and keys in an ignored `.env`.

```bash
python3 -m venv .venv
```

```bash
.venv/bin/python -m pip install -e '.[dev,agent,db]'
```

Keep `costar-hackathon-kit` next to this folder or set `COSTAR_KIT_DIR`. Settings in `.env`:

| Setting | Used for |
| --- | --- |
| `MATTERPORT_TOKEN_ID`, `MATTERPORT_TOKEN_SECRET`, `MATTERPORT_SDK_KEY` | Matterport scans and tours |
| `VEXCEL_API_KEY` | Aerial imagery and elevation |
| `SECONDSTAY_AGENT_PROVIDER`, `SECONDSTAY_AGENT_MODEL` | Agent model: `openai`, `groq`, `openrouter` or `gemini` |
| `SECONDSTAY_VISION_PROVIDER`, `SECONDSTAY_VISION_MODEL` | Image-reading model |
| `OPENAI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY` or `GOOGLE_API_KEY` | Key for the chosen provider |
| `TIGER_DATABASE_URL` | Tiger Data service URL (optional) |

Read every building's imagery and scans once, so the screen opens from cache:

```bash
.venv/bin/python -m secondstay.prefetch
```

Start the screen and open http://127.0.0.1:8000:

```bash
.venv/bin/python -m secondstay.web
```

Restore `data/raw/` on a new machine from Tiger Data:

```bash
.venv/bin/python -m secondstay.tiger restore
```

## Tests

```bash
.venv/bin/python -m pytest -q
```

```bash
node --test tests/*.mjs tests/*.cjs
```

Tests use synthetic buildings. The agent tests drive the real deepagents graph with scripted model
replies, including delegation to both sub-agents; they check orchestration and validation, not a
provider's reasoning quality. One Tiger Data test runs against the real service when
`TIGER_TEST_DATABASE=1` is set.

## Code map

| Module | Role |
| --- | --- |
| `costar.py` | Reads the CoStar kit and turns Los Angeles buildings into facts |
| `matterport.py`, `panoramas.py` | Scan geometry from the Matterport Model API; panorama contact sheets and their readings |
| `vexcel.py` | Footprint, roof height, neighbour distance and surface heights from Vexcel |
| `streets.py` | Public streets around a building from OpenStreetMap |
| `permits.py`, `public_records.py` | LADBS permits by parcel; zoning, height, seismic, historic and occupancy records |
| `checklist.py`, `evidence.py` | The 14 rows and their states; public records laid onto the rows |
| `changes.py` | The change list shared by the rules work and the cost model |
| `cost_reading.py`, `la_costs.py`, `costing.py`, `economics.py`, `finances.py` | Photo-read cost items, the LA price book, pricing, range arithmetic and the screen connection |
| `income_research.py`, `rents.py` | Rent comparables and CoStar rent calculations |
| `floor_geometry.py`, `interior_models.py` | Cached floor vectors and traced plan models in a shared floor frame |
| `agent.py` | The deepagents evidence review with its two sub-agents |
| `tiger.py` | Tiger Data backup, restore and permit time series |
| `prefetch.py` | Fills the cache for every building |
| `web.py`, `static/` | The local server and the three.js screen |

## Data handling and wording rules

- Nothing under `data/raw/` is committed: CoStar records, scans, imagery, traced models and model
  readings stay local or in the private Tiger Data service. `.env` is never committed.
- CoStar images are shown in the browser only; they are not downloaded by the server or sent to a
  vision model.
- Anything read from an image is labelled **read from images, not measured**.
- Permits record work that was filed, not what is installed today. Declared valuation is what the
  applicant wrote, not what the work cost.
- Only spaces on the market are reviewed. Leased space is not shown.
- Words not used anywhere: legal, illegal, compliant, approved, eligible, pass, fail, verdict, "can be
  converted", "cannot be converted". Used instead: pre-check, evidence, "appears consistent with",
  "may not meet", "to be confirmed by".

## Hackathon tracks

| Track | Why it fits |
| --- | --- |
| Business and Enterprise (main) | A due-diligence tool for building owners |
| CoStar: Inside and Out | All three layers (CoStar, Matterport, Vexcel) combined per requirement, with an agent and 3D views |
| Amazon: Best Practical AI Innovation | An agent that gathers, cross-checks and explains evidence for a real decision |
| LangChain: Best use of deepagents | A deepagents lead with planning and two declared sub-agents |
| MLH: Best Use of Tiger Data | Private data store with restore, compressed hypertables and continuous aggregates on screen |

## Further documents

| Document | Contents |
| --- | --- |
| `PRD.md` | Product, users, wording rules and demo script |
| `docs/requirements-research.md` | Each requirement and its published source |
| `docs/cost-sources.md` | Cost sources and assumptions |
| `docs/costar-data-notes.md` | What the CoStar kit contains |
| `docs/floor-explorer.md` | Floor exploration, interior models and the floor ledger |
| `docs/tiger-data.md` | The Tiger Data store |
| `docs/work-split.md` | Who worked on what |
