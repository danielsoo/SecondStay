# SecondStay work split: required changes and cost model

As of 2026-11-14

## Summary

Teammate A works out which physical changes the published rules call for in a building. Teammate B prices those changes and models how cost and payback move when the list changes. They meet at one data format, the **change list**, which this report fixes. Neither edits the other's files.

- **Teammate A, required changes.** Input: the evidence checklist that already runs on 89 Los Angeles office buildings. Output: a list of changes per building, each with a quantity, a source and a certainty.
- **Teammate B, cost model.** Input: a change list. Output: a cost range per change, a total, and payback against what the space earns today.
- **Until A's list exists, B works from the sample list in "The shared contract".** A works from made-up building facts. Neither needs the CoStar kit or API keys to write and test their half.

Read the first four sections, then only your own workstream. The last three sections apply to both.

One wording point before starting. The product never says a conversion is legal, allowed or feasible. A's output is "changes the published rules call for, to be confirmed by a professional", and B's output is numbers with no recommendation.

## Where the project stands

The evidence checklist works end to end on real data, but nothing yet turns a requirement into a change, and the cost model is not connected to anything.

| Piece | State | What it means for you |
| --- | --- | --- |
| Evidence checklist (`secondstay/checklist.py`) | Works. 14 requirement rows, each with one of four evidence states | A starts here. Rows say what the data shows, not what must be built |
| CoStar records | Loaded for 89 existing LA office buildings with a scan. Year built, zone and stories are on all of them | Sprinkler presence is recorded on about two thirds. Asking office rent is on 45 |
| Vexcel imagery | Height and distance to the nearest structure measured on 87 of 89 | Height is the highest roof point, so it includes rooftop equipment |
| Matterport scans | 254 scans read. 86 have floor area, 24 have room labels, 7 have stairs labelled | Interior changes (stairs, bathrooms) will be "unknown" for most buildings |
| Cost model (`secondstay/economics.py`) | Works on five hand-typed inputs. Not connected to the checklist | B replaces the hand-typed inputs with the change list |
| Price inputs (`assumptions.json`) | Every value is empty | B fills it. The code refuses to calculate with blanks |
| Screen (`secondstay/web.py`) | Shows the checklist and evidence. No changes or cost yet | Neither teammate edits it. See "Working in parallel" |

Two things in the current code conflict with the product's wording rules and are assigned below. The cost model returns the strings "Convert" and "Do not convert". The README still describes a 0 to 100 feasibility score.

## The split at a glance

A owns everything up to and including the change list. B owns everything after it. The files below do not overlap, so the two branches cannot conflict.

```
                 Teammate A                              Teammate B
Evidence   -->  changes_for   -->  CHANGE LIST  -->  estimate          -->  Cost ranges
(facts, rows)   (what the rules    (the shared       (price x quantity,     (total, payback,
already built    call for)          contract)         by scenario)           no conclusion)
                     ^                                     ^
                Rule sources                          Prices, rents
                (ordinance, LADBS bulletin)           (sourced ranges, CoStar rents)
```

The change list in the middle is the only thing that passes between the two teammates. Each brings their own research in from below.

| | Teammate A: required changes | Teammate B: cost model |
| --- | --- | --- |
| Question answered | Given the evidence, what do the published rules call for in this building? | Given that list, what does it cost, and how does the total move when the list changes? |
| Takes in | Building facts (`SpaceFacts`) and checklist rows | A change list, a price book, rent figures |
| Hands over | `changes_for(facts, rows, current_year)` returning a list of `Change` | `estimate(changes, prices, income)` returning cost lines, totals and payback |
| Files owned | `secondstay/changes.py`, `secondstay/checklist.py`, `tests/test_changes.py`, `tests/test_checklist.py`, `docs/requirements-research.md` | `secondstay/costing.py`, `secondstay/economics.py`, `secondstay/rents.py`, `assumptions.json`, `tests/test_costing.py`, `tests/test_economics.py`, `tests/fixtures/sample_changes.json`, `docs/cost-sources.md` |
| Research | The adaptive reuse ordinance, LADBS bulletin IB-BC-2026-164, the building code sections they cite | Los Angeles construction costs per change, soft costs, apartment rents, operating costs |
| Never decides | What anything costs | Whether a change is called for |
| Done when | Every checklist row maps to zero or more changes with a source, and the function runs on all 89 buildings | Every change key in the catalog has a sourced price or is shown as "not priced", and the total responds to adding or removing a change |

**Files neither teammate edits:** `secondstay/web.py`, `secondstay/static/`, `secondstay/costar.py`, `secondstay/matterport.py`, `secondstay/vexcel.py`, `secondstay/prefetch.py`, `PRD.md`, `README.md`. These belong to integration. If you need something from them, write the request in "Open questions" instead of editing.

## The shared contract

A change is one piece of physical or professional work, with a quantity B can multiply by a unit price. This is the only thing the two halves share. Agree on it in the first 30 minutes; after that it only grows, it never changes shape.

This type already exists, with the catalog and a loader, in `secondstay/changes.py`. A adds the function below it. B imports it and never edits it.

```python
@dataclass
class Change:
    key: str                  # from the catalog below, e.g. "sprinklers.install"
    requirement: str          # checklist row key it comes from, e.g. "sprinklers"
    title: str                # shown to the owner: "Install sprinkler coverage"
    certainty: str            # "called_for" | "possible" | "unknown"
    quantity: Optional[float] # None when the data cannot size it
    unit: str                 # "sqft" | "each" | "linear_ft" | "story" | "lump"
    quantity_basis: str       # where the quantity came from, in words
    scope: str                # "building" | "space" (the scanned suite)
    reason: str               # the evidence that triggered it
    source_url: Optional[str] # the published rule
    confirmed_by: str         # who confirms it
```

### What each certainty means

| Certainty | A sets it when | B treats it as |
| --- | --- | --- |
| `called_for` | The published rule calls for the work and the evidence shows it is missing or applies. Example: the record shows no sprinkler system | Part of the base estimate |
| `possible` | The evidence points to the work but could be wrong. Example: 12 stories on record, height not yet confirmed as 75 ft or above | Outside the base. Added in the "with possible changes" scenario |
| `unknown` | The data cannot say either way. Example: seismic strengthening | Outside the base. Added only in the "everything" scenario, and listed by name |

A requirement with "Evidence found" produces no change. The mapping from evidence state to certainty is A's decision, row by row.

### Starting catalog of change keys

A owns this list and may add to it. B prices every key in it. Revised on 2026-11-14 after reading the sources; see `docs/requirements-research.md` for the reasons and the decision table.

| Key | Unit | Quantity comes from | From requirement | When |
| --- | --- | --- | --- | --- |
| `planning.conditional_use_permit` | lump | 1 | Building age, Zone | 5 to under 15 years old, or a manufacturing zone |
| `historic.review` | lump | 1 | Historic status | Always, unknown until checked |
| `sprinklers.install` | sqft | Building rentable area | Sprinklers | Record shows no system, or nothing on record |
| `sprinklers.verify_coverage` | lump | 1 | Sprinklers | System on record, coverage not recorded |
| `fire_alarm.install` | sqft | Building rentable area | Fire alarm | Always, until evidence exists |
| `highrise.smokeproof_stairs` | each | Number of exit stairs (not known yet) | Height | Highest occupied level near or above 75 ft |
| `highrise.fire_pump_water_supply` | lump | 1 | Height | Same |
| `highrise.emergency_power` | lump | 1 | Height | Same |
| `highrise.fire_command_center` | lump | 1 | Height | Same |
| `highrise.smoke_control` | lump | 1 | Height | Same |
| `elevator.gurney_car` | each | 1 | Elevator | More than four stories |
| `elevator.fire_service_access` | each | 1 | Elevator | Highest occupied level above 120 ft |
| `seismic.evaluate` | lump | 1 | Seismic | Always |
| `seismic.strengthen` | sqft | Building rentable area | Seismic | Unknown until evaluated |
| `egress.add_stair` | story | Stories lacking a second stair | Exits per story | Scan shows fewer than two stairs on a story |
| `escape.add_openings` | each | Sleeping rooms without an exterior opening | Escape openings | Not derivable yet |
| `units.fitout` | sqft | Scan floor area, or rentable area | Unit count | Always, for the space converted |
| `units.bathroom` | each | Units minus existing bathrooms | Unit count | Always |
| `units.kitchen` | each | Units | Unit count | Always |
| `units.plumbing_run` | linear_ft | Distance from new wet rooms to existing ones | Unit count | Not produced yet |

### Sample change list for B to build against

A made-up four-story building, saved as `tests/fixtures/sample_changes.json`. It has five changes covering all three certainties, including one with no quantity. Load it with `load_changes(path)` from `secondstay/changes.py`.

### Rules for changing the contract

- **New key:** A adds a row to the catalog and tells B. Until B prices it, B's code shows the line as "not priced" and leaves it out of the total. It must never crash on an unknown key.
- **Missing quantity:** when `quantity` is `None`, B lists the change as "quantity unknown" and leaves it out of the total.
- **New field:** allowed if it has a default, so old lists still load. Removing or renaming a field is not allowed.
- **Units:** only the five above. If a change needs another unit, pick the closest and explain in `quantity_basis`.

## Workstream A: required changes

Your job is to turn each requirement row into the work it calls for, with a quantity and a source. You do the rule research and write one function. You never put a price on anything.

### What you start with

`build_checklist(facts, year)` returns 14 rows. Each row has a requirement, a rule summary, a source link, an evidence state, the evidence in words and who confirms it. `SpaceFacts` holds the building facts behind them: year built, zone, stories, sprinkler presence, passenger elevators, height from imagery, distance to the nearest structure, scan floor areas and room types.

The rule summaries came from the City Planning adaptive reuse page and the LADBS bulletin. Nobody has read the full ordinance text yet. Treat every threshold in the code as unverified until you have checked it.

### Tasks, in order

- [ ] **Agree the contract with B.** Read "The shared contract" and raise objections in the first 30 minutes.
- [ ] **Verify each rule.** For all 14 rows, find the sentence in the ordinance or bulletin that supports the rule summary. Record the section, the quote location and the date accessed in `docs/requirements-research.md`. Correct `checklist.py` where the summary is wrong.
- [ ] **Write the decision table.** For each requirement: which evidence leads to which change key, with which certainty. Start from the draft "when" column in the catalog. Put the finished table in `docs/requirements-research.md`.
- [ ] **Implement `changes_for(facts, rows)`.** A pure function in `secondstay/changes.py`. No file reads, no network calls, no prices.
- [ ] **Size each change.** Fill `quantity` and `quantity_basis` from the facts. Leave `quantity` as `None` when the data cannot size it. Do not guess.
- [ ] **Test with made-up buildings.** Cover at least: a low-rise with everything on record, a tall building, a building with no sprinkler record, a scan with no room types. Reuse the banned-word check in `tests/test_changes.py` on every `title` and `reason`.
- [ ] **Run it on all 89 buildings** once integration has merged your branch, and report how many changes of each certainty come out.

### Questions the research has to settle

These decide what the change list contains, so answer them before coding the affected rows.

1. **How is the 75 ft threshold measured?** Our imagery height is the highest roof point including equipment. If the rule measures to the highest occupied floor, the row needs a different comparison.
2. **Does the ordinance apply to a whole building or to part of one?** A scan covers a suite or a floor. This decides whether `scope` is "building" or "space" for each change.
3. **What exactly triggers the high-rise systems, and which systems?** The spec lists smokeproof stairs, fire pumps and emergency power. If they are priced very differently, split `highrise.systems` into separate keys.
4. **What does the elevator rule call for above four stories?** The spec only says four stories or fewer may not need a gurney-sized elevator.
5. **Which zones qualify?** The code holds a list of 23 zone classes taken from the City Planning page. 16 of 89 buildings fall outside it, mostly industrial zones.
6. **Is there a rule for existing sprinklers that cover only part of a building?** The record says a system exists, never how much it covers.

### Limits in the data you should design around

- **Stairs are labelled in 7 of 254 scans.** For most buildings `egress.add_stair` will be `unknown` with no quantity. That is the correct output, not a gap in your work.
- **Sprinkler presence is recorded on about two thirds of buildings.** Where it is blank, use `unknown`.
- **Rentable area is not in `SpaceFacts` yet.** Several quantities need it. Add `building_sqft` and `typical_floor_sqft` to `SpaceFacts` (you own that file) and ask integration to fill them from the CoStar record. Until then, use made-up values in tests.
- **Unit count is a planning assumption.** The code uses 80% usable area and 500 sq ft per unit. Keep it labelled as an assumption in `quantity_basis`.

### What you hand over

- `secondstay/changes.py` with `changes_for`, tests passing.
- `docs/requirements-research.md` with a source for every rule and the decision table.
- A short list of rule summaries you corrected, so the screen and the pitch can be updated.

## Workstream B: cost model

Your job is to price a change list and show how the total and the payback move when the list changes. You do the cost research and write one function. You never decide whether a change is called for.

### What you start with

`secondstay/economics.py` already computes a cost breakdown, monthly net income and payback. It takes a `ConversionPlan` of five hand-typed numbers (area, units, bathrooms, plumbing run, kitchens) and an `Assumptions` object. `assumptions.json` lists eleven price inputs with low, typical and high slots, a source and a confidence. All of them are empty.

Three things need to change. The inputs must come from the change list, not from hand-typed numbers. Prices must be keyed by change key. The result must stop returning "Convert" and "Do not convert", because the product gives no overall result.

### The model

Each change becomes one cost line with a low, typical and high value. A price can have a fixed part and a per-unit part, so a lump-sum study and a per-square-foot installation use the same formula.

```
line(c) = fixed(c) + rate(c) x quantity(c)

total = (sum of line(c) for c in scenario) x (1 + soft cost share) x (1 + contingency)
```

The scenario is what makes cost respond to changes. It is the set of changes included:

| Scenario | Includes | Answers |
| --- | --- | --- |
| Base | `called_for` changes | What the evidence already points to |
| With possible changes | Base plus `possible` | What it costs if the open evidence goes against the owner |
| Everything | All changes with a quantity | The upper bound we can put a number on |
| Custom | Any set the owner ticks | "What if the building already has sprinklers?" |

Report each scenario as a low to high range, never a single figure. List changes that are "not priced" or "quantity unknown" by name next to the total, so the owner sees what the number leaves out.

### Tasks, in order

- [ ] **Agree the contract with A.** Read "The shared contract" and raise objections in the first 30 minutes.
- [ ] **Restructure the price book.** Rewrite `assumptions.json` so each entry is keyed by a change key from the catalog, with `unit`, `fixed` and `rate` at low, typical and high, plus `source`, `published`, `accessed`, `confidence` and `notes`. Keep soft cost share, contingency, months to convert, occupancy and operating cost share as their own entries.
- [ ] **Write `estimate(changes, prices, income, scenario)`** in `secondstay/costing.py`. It returns one line per change (quantity, unit, unit price range, line range, status), the scenario total range, and the list of changes left out with the reason.
- [ ] **Handle the three statuses.** `priced`, `not priced` (key missing from the price book or its values empty) and `quantity unknown`. No status may raise an error.
- [ ] **Research and fill prices.** One sourced range per change key for Los Angeles. Record every source in `docs/cost-sources.md` with the publication date, the date accessed and what the figure excludes. A value without a source stays empty.
- [ ] **Build the income side.** In `secondstay/rents.py`, work out monthly rent per unit and what the space earns today. See "Where the rent figures come from" below.
- [ ] **Keep the payback arithmetic, remove the conclusion.** Move the payback calculation from `evaluate` into the new function. Delete the `verdict` field and its three strings. Return cost range, monthly net income, payback range in years and gain over the horizon.
- [ ] **Add sensitivity.** For one building, show which three inputs move payback the most when each is set to its low and high value.
- [ ] **Test with the sample list.** Cover: base total excludes `possible` and `unknown`; removing a change lowers the total by exactly its line; an unknown key shows as "not priced"; a `None` quantity shows as "quantity unknown"; empty prices never produce a number.

### Where the rent figures come from

The CoStar kit holds both sides. You need the kit on your machine for this part only; everything else runs on made-up data.

| Figure | Source in the kit | Caution |
| --- | --- | --- |
| Housing rent per unit | `data/apartment-listing.jsonl`: asking rents by floor plan for 767 Los Angeles apartment communities. Each joins to a property with a latitude and longitude | Asking rent, not achieved rent. Pick comparables by distance or submarket and say which |
| What the space earns today | Office asking rent per sq ft per year, on 45 of the 89 buildings, times the area | A vacant space earns nothing. Asking rents mix service types |
| How empty the building is | Marketed area, and share of rentable area with no tenancy on record | Marketed is not vacant. Some tenancies have no area recorded |

Read the kit's `concepts/metrics-and-formulas.md` and `concepts/apartments.md` before averaging rents. Rents must be on the same basis before they are compared. See also `docs/costar-data-notes.md` in this repo.

### Questions the research has to settle

1. **Which changes scale with area and which are mostly fixed?** This sets `fixed` against `rate` for each key and is the main reason one building is cheap and another is not.
2. **What do published Los Angeles figures exclude?** Many per-square-foot conversion costs already include sprinklers or soft costs. Adding them again double-counts.
3. **What soft cost share and contingency are defensible?** Give a range with a source for each.
4. **How long is the build?** No rent is earned during it, so months to convert moves payback directly.
5. **What horizon should payback be judged against?** The current default is five years. Agree it with the team.

### What you hand over

- `secondstay/costing.py` with `estimate`, and `secondstay/rents.py`, tests passing.
- `assumptions.json` filled where a source exists, empty where it does not.
- `docs/cost-sources.md` with every figure's source.
- A list of catalog keys you could not price, so the screen can say so.

## Working in parallel

Neither teammate waits for the other at any point. B builds against the sample list; A builds against made-up buildings. The two halves are joined by integration at the end.

1. **First 30 minutes: fix the contract.** Both read "The shared contract" and agree or amend it together. After that it only grows.
2. **Branch.** A works on a branch named `changes`, B on `cost`, both cut from the latest commit on `claude/dreamy-franklin-8rv2am`. Each touches only the files in their column of the ownership table.
3. **Checkpoint 1: one real list.** A sends B the change list for one made-up building produced by real code, even if it covers only three requirements. B runs it through `estimate` and reports anything that does not fit.
4. **Checkpoint 2: catalog closed.** A confirms the catalog keys are final for the hackathon. B confirms every key is priced or deliberately shown as "not priced".
5. **Checkpoint 3: join.** Integration merges both branches and adds a cost panel to the screen that calls `changes_for` then `estimate`. Because the files do not overlap, the merge order does not matter.
6. **After the join: run on all 89 buildings.** A checks the change counts look right. B checks no total is built on an empty price.

### If you are blocked

| Situation | What to do |
| --- | --- |
| A's catalog is not final | B prices the starting catalog. Extra keys show as "not priced" until added |
| A cannot size a change | Set `quantity` to `None`. B's code already handles it |
| B needs a fact that is not in a change | Ask A to add it to `quantity_basis` or as a new field with a default. Do not read `SpaceFacts` directly |
| Either needs a change in a shared file | Write the request under "Open questions". Do not edit the file |
| A finds a rule summary on the screen is wrong | Fix it in `checklist.py` (A owns it) and note it in the hand-over list |

## Rules both follow

These come from the product spec (`PRD.md`) and from CoStar's data terms. They apply to code, tests, documents and the pitch.

**Wording**

- Do not use: legal, illegal, compliant, approved, eligible, pass, fail, verdict, "can be converted", "cannot be converted".
- Use instead: pre-check, evidence, indication, "appears consistent with", "may not meet", "the published rule calls for", "to be confirmed by".
- No score and no overall result. A's output is a list. B's output is ranges. Neither says whether to convert.
- Every screen and exported document carries the fixed notice: "This is a preliminary evidence review, not a legal or code determination. Final decisions are made by LADBS and licensed professionals."
- A test already enforces the banned words on checklist text. Each of you adds the same check to your own output.

**Sources**

- Every rule has a link to the published text and the date it was read.
- Every price has a source, a publication date and a note on what it excludes. A value without a source stays empty, and the code refuses to total it.
- Anything that is our own assumption is labelled as one where the owner can see it.

**Data**

- No real CoStar record, address, property id, floor plan or Matterport model id goes into the repository, tests, documents or the README. Tests use made-up buildings.
- `.env` and everything under `data/raw/` are ignored by git. Keep it that way.
- Real data may appear in the demo video and a temporary deployment only.

**Git**

- One branch each, own files only. Tests pass before you ask for a merge.
- Do not commit generated files or caches.

## Open questions

Add to this table as you work. Requests for changes to shared files go here too.

| Question | Who answers |
| --- | --- |
| Who owns integration: the screen, the data adapters and the merges? This report assumes the person holding the CoStar kit and API keys | Team |
| Which building is the demo building? Two candidates with labelled stairs in their scans have been identified | Team |
| Is the 75 ft threshold measured to the roof or to the highest occupied floor? | A |
| Does the ordinance cover converting part of a building? | A |
| Should `highrise.systems` be one key or one per system? | A, then B prices the result |
| Which Los Angeles cost sources will judges accept as credible? | B |
| Are apartment rent comparables chosen by distance or by submarket? | B |
| What horizon is payback judged against? Currently five years | B proposes, team agrees |
| Request to integration: fill `building_sqft` and `typical_floor_sqft` in `SpaceFacts` from the CoStar record | A raises, integration does |
| Request to integration: add a cost panel to the screen once both branches merge | Integration |
| Request to integration: update the README, which still describes a 0 to 100 score | Integration |
