# SecondStay PRD

As of 2026-11-14 (revision 2: evidence pre-check first, cost second)

> SecondStay is a preliminary evidence review, not a legal or code determination.
> Final decisions are made by the Los Angeles Department of Building and Safety
> (LADBS) and licensed professionals.

## Summary

SecondStay helps owners of vacant commercial space check, requirement by requirement, what evidence exists that the space could be converted to housing under Los Angeles rules, and what still has to be confirmed by a professional.

It does not say a conversion is allowed or not allowed. For each published requirement it shows the rule, the evidence found in the data, how strong that evidence is, and who can confirm it.

Pitch: "Before an owner pays an architect, SecondStay shows what the data already says about each conversion requirement, and exactly what is left to verify."

Scope for HackPrinceton: Los Angeles only, office and commercial space only, pre-check only.

## Problem

An owner with vacant space cannot easily tell whether a conversion to housing is worth pursuing.

- **The rules are spread across documents.** The Citywide Adaptive Reuse Ordinance, the LADBS bulletin and the building codes each add requirements.
- **Checking them takes paid professional time.** Today the first answer comes after hiring an architect to visit and measure.
- **Most of the first-pass facts already exist as data.** Building age, size, floors, room dimensions, stair locations and the surroundings are in records, 3D scans and aerial imagery.
- **Nobody connects that data to the requirements.** So owners either skip the question or pay to learn something a screen could have shown.

## Users and goals

| Who | What they want | What SecondStay gives them |
| --- | --- | --- |
| Building owner or operator (customer) | To know whether a conversion is worth a professional's time | A requirement-by-requirement evidence checklist and a list of what to verify |
| Architect or consultant hired next | A head start | The evidence and open items in one document |
| Future resident (not a user) | A home in a converted space | Nothing directly. They come after a conversion is approved and built |

**Success at the hackathon**

- The checklist runs on real LA spaces using all three data layers.
- Every requirement row shows its source, the evidence, and how to confirm it.
- Clicking a row shows the evidence itself: the scan view, the aerial image, or the record value.
- No screen states a legal conclusion.
- Every requirement row is checked against its published source before the demo.

## Wording rules

These apply to the UI, the report, the pitch and the README.

**Evidence states (the only four)**

| State | Meaning | When it is used |
| --- | --- | --- |
| Evidence found | The data is consistent with the requirement | A record or measurement matches |
| Possible issue | The data suggests the requirement may not be met | A record or measurement conflicts |
| Not enough data | The data we have cannot answer it | Field is empty or not visible in the scan |
| Needs professional review | Data cannot answer this kind of requirement | Sprinklers, seismic performance, historic status |

**Words we do not use:** legal, illegal, compliant, approved, eligible, pass, fail, verdict, "can be converted", "cannot be converted".

**Words we use instead:** pre-check, evidence, indication, "appears consistent with", "may not meet", "to be confirmed by".

**Fixed notice** on every screen and report: "This is a preliminary evidence review, not a legal or code determination. Final decisions are made by LADBS and licensed professionals."

There is no score and no overall result. The summary is a count per state, for example "Evidence found 6 · Possible issue 1 · Needs professional review 4".

## Requirements checked

Each row is one line in the checklist. Sources are the LA City Planning adaptive reuse page and LADBS bulletin IB-BC-2026-164. The full ordinance text has not been read.

| Requirement | What the published rule says | Evidence we look for | Layer | How it is confirmed |
| --- | --- | --- | --- | --- |
| Building age | 15 years or older uses the streamlined path; 5 to 15 years goes to discretionary review | Year built | CoStar | LADBS building records |
| Zone | Multifamily Residential, Commercial, Parking or Public Facilities zones | Zoning value, if present | CoStar | City zoning lookup (ZIMAS) |
| Unit count | Projects creating five or more residential units | Floor area and room dimensions | Matterport | Architect's layout |
| Height | Additional systems at 75 feet and above | Stories on record; height seen from the air | CoStar, Vexcel | Survey or building records |
| Exits per story | Residential egress standards for number of and distance between exits | Stair locations in the scan | Matterport | Architect and LADBS plan check |
| Escape openings for sleeping rooms | Each sleeping room needs an opening to the outside | Rooms on an exterior wall; what is outside that wall | Matterport, Vexcel | Architect on site |
| Fire separation distance | Exterior wall and opening rules depend on distance to neighbours | Distance to adjacent buildings | Vexcel | Survey |
| Fire access and exit discharge | Exits lead to a public way; fire vehicles can reach the building | Street frontage and access routes | Vexcel | Fire Department review |
| Elevator | Four stories or fewer may not need a gurney-sized elevator | Stories on record | CoStar | LADBS plan check |
| Stay length | Rentals over 30 consecutive days are outside short-term rental rules | Product setting | n/a | City Planning guidance |
| Sprinklers | Full sprinkler coverage required | Not in our data | none | Needs professional review |
| Fire alarm | Required throughout | Not in our data | none | Needs professional review |
| Seismic | Analysis at 75% of design ground motion, strengthening as required | Not in our data | none | Structural engineer |
| Historic status | Surveyed or designated resources follow a different review | Not in our data | none | Office of Historic Resources |

Sources: [LA City Planning: Adaptive Reuse](https://planning.lacity.gov/project-review/adaptive-reuse) · [LADBS IB-BC-2026-164](https://dbs.lacity.gov/sites/default/files/efs/forms_and_publications/publications/information-bulletins/building-code/2026/IB-BC-2026-164-Change_Occupancy_Office_Residential.pdf) · [City Planning press release, Feb. 9, 2026](https://planning.lacity.gov/odocument/0fa826b2-52c7-4ab7-ad29-e6edefed4493/Adaptive_Reuse_Ordinance_Feb_2026.pdf) · [Home-Sharing FAQ](https://planning.lacity.gov/ordinances/docs/HomeSharing/FAQ.pdf)

## The screen

The checklist screen for one space is the product. Everything else supports it.

- **Left: the requirement list.** One row per requirement with its evidence state.
- **Right: the evidence.** Selecting a row shows the evidence itself. Exits: the 3D view with stairs marked. Height: the aerial image. Age: the record value. Each view names its data source.
- **Each row expands** to show the rule summary with a link to the source, the evidence, and how it is confirmed.
- **Bottom: next steps.** Every "Needs professional review" and "Not enough data" row, grouped by who confirms it. This exports as a document the owner hands to an architect.
- **Top: the count per state** and the fixed notice. No score.

A second screen lists the owner's spaces with their counts so they can decide which to look at first.

## How the agent works

1. **Find spaces.** List vacant commercial space in LA from the CoStar data.
2. **Link the layers.** Match each space to its Matterport scan and its location for Vexcel.
3. **Gather evidence per requirement.** Read records, measure from the scan, inspect aerial imagery. Where room types are missing from the scan data, look at the scan's panorama images to find stairs, restrooms and exterior walls.
4. **Assign an evidence state** to each requirement, with the reason and the source.
5. **Cross-check.** If two layers disagree, for example stories on record against what the imagery shows, mark the row "Possible issue" and show both.
6. **Write the next-steps list.**

## Requirements

**Must have**

- Checklist screen for one space with the four evidence states and the fixed notice.
- Evidence view for each row, using the 3D view, aerial imagery or record values.
- Evidence gathered from all three layers for at least age, unit count, height, exits and escape openings.
- Next-steps list grouped by who confirms.
- Wording rules followed everywhere.

**Should have**

- List of spaces with counts per state.
- Panorama inspection to locate stairs and restrooms when scan labels are missing.
- Exportable report.
- The agent built with deepagents, with sub-agents per layer.

**Later: cost and return (phase 2)**

Only for spaces the owner chooses to pursue. Estimates the cost of the work the rules call for and the housing income, with every price an editable assumption that has a source. The calculation exists in `secondstay/economics.py` but is not part of the first screen.

**Out of scope**

- Any statement that a conversion is or is not allowed.
- Structural engineering, hidden plumbing capacity, historic review.
- Listings for residents, bookings or payments.
- Cities other than Los Angeles.

## What we know about the data

- The Matterport Model API works with our keys. About 14,900 scans are available across Houston and Los Angeles.
- Scans give room dimensions, room boundaries, floor areas, panorama images and coordinates.
- Most scans are apartments. Office and retail scans number in the hundreds.
- In one LA office and retail scan we inspected, room types were "Void" or "Other", room names were empty and no objects were detected. So stairs and restrooms may have to be found from panorama images, and many rows may show "Not enough data".
- Vexcel and the CoStar data have not been loaded yet.

Data rule from CoStar: real floor plans, model IDs and property-identifying data cannot go in the public repo or README. Showing them in the demo video and a temporary deployment is allowed.

## Demo plan

1. The owner opens their list of vacant spaces with the count per evidence state.
2. They open one space. The checklist appears.
3. They select "Exits per story". The 3D view shows the stairs the agent found.
4. They select "Height". The aerial image appears next to the record value.
5. One row shows "Possible issue" because two layers disagree. The agent shows both.
6. They open the next-steps list and export it for an architect.
7. Closing line: "We do not tell the owner the answer. We show what the data says and what is left to confirm."

## Team split

| Area | A: research | B: product |
| --- | --- | --- |
| Rules | Reads the ordinance text and bulletin; confirms each row of the requirements table and its source | Encodes the rows as data |
| Wording | Reviews every screen and the pitch against the wording rules | Applies the fixes |
| Cost data (phase 2) | Collects construction figures with sources | Keeps the cost model ready |
| Data | None | Keys, CoStar data, Matterport and Vexcel calls |
| Product | None | Evidence gathering, checklist screen, evidence views, next-steps export |
| Submission | Devpost text, sponsor track requirements | Demo spaces, video, slides, repo, deployment |
| Presentation | The problem, the rules, the wording | The live demo |

## Tracks, risks and open questions

**Tracks**

| Track | Why it fits |
| --- | --- |
| Business and Enterprise (main) | A due-diligence tool for property owners |
| CoStar: Inside and Out | Each layer supplies evidence for specific requirements |
| Amazon: Practical AI | An agent that gathers, cross-checks and explains evidence |
| LangChain: deepagents | The agent is built with deepagents |

**Risks**

| Risk | Mitigation |
| --- | --- |
| The product is read as giving legal conclusions | Wording rules, fixed notice, no score, A reviews every screen against the rules |
| Commercial scans lack room types | Panorama inspection; honest "Not enough data" rows |
| Few spaces have all three layers | Choose the demo spaces first |
| A requirement is summarised wrongly | A confirms every row against the source before the demo |
| Scope grows | Checklist screen first; cost model stays in phase 2 |

**Open questions**

- [ ] Does the CoStar data include zoning, year built, stories and vacancy by suite?
- [ ] What does the Vexcel API return for height and neighbouring buildings?
- [ ] How many LA commercial scans have usable room types?
- [ ] Which spaces will the demo use?
