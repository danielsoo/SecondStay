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
- [x] Cost, rent, payback and sensitivity connected to the selected space (`secondstay/finances.py`)
- [x] Agent orchestration (deepagents), validated tools, private run history and replay; live demo recording needs local model keys

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

## Evidence agent and recorded replay

This is a preliminary evidence review, not a legal or code determination. Final decisions are made by LADBS and licensed professionals.

Use Python 3.11 or newer (tested with 3.12):

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,agent]'
.venv/bin/python -m pytest
.venv/bin/python -m secondstay.web 8001
```

Add these settings to the ignored `.env` locally. Choose model names supported by your provider;
there is no default model and no assumption that calls are free.

| Setting | Value |
| --- | --- |
| `SECONDSTAY_AGENT_PROVIDER` | `groq` or `openrouter` (also supports `gemini`) |
| `SECONDSTAY_AGENT_MODEL` | Your provider's tool-calling model name |
| `GROQ_API_KEY` or `OPENROUTER_API_KEY` | Key for the selected reasoning provider |
| `SECONDSTAY_VISION_PROVIDER` | `gemini` by default; `openrouter` also supported |
| `SECONDSTAY_VISION_MODEL` | Your provider's image-capable model name |
| `GOOGLE_API_KEY` | Gemini key, when Gemini is selected |

Open a building or suite and choose **Run evidence review** beside the 3D view. The deepagents
model selects validated actions through `evidence_step`: inspect missing evidence, read records,
read scan geometry, inspect panorama/plan images, read aerial measurements and streets,
cross-check, then record a checklist and next steps. The built-in planning tool is available;
arbitrary filesystem access, shell execution and delegation are excluded. The selected scope
is fixed before the model starts, so it cannot supply unrelated building or scan identifiers.

The tool observations update typed facts. Existing checklist and change-list functions determine
the displayed states; model prose cannot overwrite them. Repeated source disagreement stays
visible for professional confirmation. The progress panel describes the purpose of each selected
tool, rather than displaying private model reasoning. Each run is limited to 24 evidence actions
and 48 graph steps, with at most two attempts per source. Only one browser-started run executes
at a time.

Runs and image observations are saved under ignored `data/raw/agent_runs/`. **Replay saved run**
plays those recorded tool events without calling a model. The recorded checklist and its export
belong to that run; the existing checklist below the panel is the separate cached-data view.
Interrupted or incomplete runs retain their observations but do not receive a completed report.
Set `SECONDSTAY_OFFLINE=1` to use cached source data and recorded reviews without new model calls.
The existing 3D libraries still require internet access.

For up to five demo buildings, invoke `python -m secondstay.agent` with the numeric identifiers
from your local collection as positional arguments. Add `--space` with a local space identifier
for a single-suite review. Do not put real identifiers in checked-in scripts or documentation.
Each completed run becomes available in the screen's saved-review selector.

### Image evidence and limits

New runs do not import the old manual readings. A configured vision model reads the selected
scan's panorama sheet and, when available, its Matterport plan. All such evidence is labelled
**read from images, not measured**, with provider/model, reading date and image hash stored in
the private run. Counts are observations, not a complete inventory; accuracy is not validated.

CoStar image downloads remain excluded. CoStar floor plans are available for human browser
review; they are not sent to a vision model by this implementation. If a linked Matterport plan
is absent, that tool records the gap. Missing model settings, unavailable images and provider
errors leave evidence open. Source rechecks may use the same cached snapshot; they are not
presented as new independent measurements.

The automated tests use synthetic buildings and scripted model replies through the actual
LangChain graph. They verify orchestration and validation, not a provider's reasoning quality.
A real provider run and the five-building demo recording require local model credentials.

Implementation references: [Deep Agents customization](https://docs.langchain.com/oss/python/deepagents/customization),
[Groq integration](https://docs.langchain.com/oss/python/integrations/chat/groq),
[Gemini integration](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai).
