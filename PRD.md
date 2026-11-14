# SecondStay PRD

As of 2026-11-14

## Summary

SecondStay is an AI agent that tells commercial property owners which of their vacant spaces can become furnished housing for stays of 1 to 6 months, what the conversion would cost, and whether it pays back.

The customer is the building owner. The residents are people a 12-month lease does not fit: interns, travelling nurses, visiting researchers, people relocating.

Pitch: "SecondStay finds which empty commercial spaces could become homes, shows what would have to change, and tells owners whether the numbers justify the next step."

Scope for HackPrinceton: Los Angeles only, office buildings only, preliminary feasibility only.

## Problem

Owners of vacant offices cannot tell which spaces are worth converting to housing without paying an architect to walk each one.

- **Offices sit empty while housing is short.** LA City Planning describes office vacancy as historically high since the pandemic and adopted a citywide ordinance in 2026 to encourage conversion.
- **Most offices are not ready to live in.** They lack showers and kitchens, and the law also requires sprinklers, fire alarms, residential egress and a seismic review.
- **The cost depends on the specific space.** A bathroom next to an existing restroom is cheap. One 100 feet from the nearest plumbing is not.
- **Screening is manual today.** An owner with many properties has no fast way to find the few where conversion makes sense.

## Users and goals

| Who | What they want | What SecondStay gives them |
| --- | --- | --- |
| Building owner or operator (customer) | Income from space that sits empty | A ranked shortlist, a conversion plan and a convert / do not convert verdict per space |
| Developer or investor | Candidates worth a site visit | Evidence-backed screening before paying for design |
| Resident (not a user of the product) | A furnished home for a few months | Nothing directly. Their needs set the requirements, such as a private bathroom |

**Success at the hackathon**

- The agent screens real LA buildings using all three data layers.
- It rejects at least one building and explains why.
- Changing one assumption on screen changes the verdict.
- A practitioner we interviewed confirms the cost assumptions are in a realistic range.

## How the agent works

The owner asks: "Which of my vacant spaces could become temporary housing, and what is the lowest-cost way to convert them?"

1. **Find candidates.** Filter the CoStar data for vacant office space in LA.
2. **Check eligibility.** Keep buildings that are at least 15 years old, in an eligible zone, and large enough for five or more units.
3. **Inspect the inside.** Read room dimensions and room types from the Matterport scan. Work out how many units fit and how far each new bathroom is from existing plumbing.
4. **Inspect the outside.** Use Vexcel aerial imagery for daylight clearance to neighbouring buildings, parking and entrances.
5. **Cost it.** Apply the cost assumptions to the conversion plan.
6. **Decide.** Compare housing income with what the space earns today, over the time the space is available. Reject what does not pay back.
7. **Report.** Show a shortlist with evidence, split into observed facts, estimates, and items that need a site inspection.

| Data layer | What the agent takes from it |
| --- | --- |
| CoStar building data | Vacant space, year built, floors, size, current office income, nearby residential rents |
| Matterport 3D scans | Room dimensions, room types, location of existing restrooms and kitchens, windows |
| Vexcel aerial imagery | Distance to neighbouring buildings, parking, entrances |

## Requirements

**Must have**

- Load the CoStar data and list vacant LA office space.
- Eligibility screen: building age, zone, five or more units.
- Pull rooms and dimensions for a building from the Matterport API.
- Generate a conversion plan: unit count, bathrooms to add, plumbing run to the nearest existing restroom.
- Cost and payback calculation with a verdict and a stated reason.
- A web page with the ranked shortlist, the 3D view of the top candidate, and editable assumptions that recalculate the verdict.
- Every figure labelled as observed, estimated, or needs inspection.

**Should have**

- Vexcel checks for daylight clearance and parking.
- Two plans per space: most units, and least construction.
- Markers in the 3D view showing where units and bathrooms would go.
- The agent built with deepagents, with separate sub-agents for search, interior review, exterior review and reporting.

**Out of scope**

- Zoning or permit decisions. The product screens; it does not approve.
- Structural engineering and hidden plumbing capacity.
- Matching residents, bookings or payments.
- Cities other than Los Angeles and building types other than office.

## LA rules the product encodes

Conversion is legal in Los Angeles through the Citywide Adaptive Reuse Ordinance (No. 188,793), effective February 1, 2026. The product uses these rules as its eligibility screen and as the list of work it must cost. The full ordinance text has not been read; the points below come from the city's guidance page, press release and the LADBS bulletin.

**Eligibility screen**

| Rule | How the agent checks it |
| --- | --- |
| Conversion creates five or more residential units | Unit count from the conversion plan |
| Building is at least 15 years old (5 to 15 needs discretionary review) | Year built in CoStar data |
| Located in a Multifamily Residential, Commercial, Parking or Public Facilities zone | Zoning field, if present in the CoStar data |
| Stays longer than 30 days fall outside short-term rental rules | Product targets 31 days to 6 months |

**Work the law requires, from LADBS bulletin IB-BC-2026-164**

- Full sprinkler coverage of the building.
- Fire alarm throughout the building.
- Egress brought to residential standard, with emergency escape openings for sleeping rooms.
- Seismic analysis at 75% of the design earthquake ground motion, with strengthening as required.
- Extra systems for buildings 75 feet and taller.

**What is relaxed**

- No minimum unit size beyond the Building Code.
- Wall insulation and existing windows need not meet the current energy code.
- Buildings of four stories or fewer may be exempt from the gurney-sized elevator.
- A partial conversion can request relief from the seismic requirement, case by case.

Consequence for the product: small low-rise buildings that already have sprinklers are the best candidates, so building height and existing sprinklers are inputs to the verdict.

Sources: [LA City Planning: Adaptive Reuse](https://planning.lacity.gov/project-review/adaptive-reuse) · [LADBS IB-BC-2026-164](https://dbs.lacity.gov/sites/default/files/efs/forms_and_publications/publications/information-bulletins/building-code/2026/IB-BC-2026-164-Change_Occupancy_Office_Residential.pdf) · [City Planning press release, Feb. 9, 2026](https://planning.lacity.gov/odocument/0fa826b2-52c7-4ab7-ad29-e6edefed4493/Adaptive_Reuse_Ordinance_Feb_2026.pdf) · [Home-Sharing FAQ](https://planning.lacity.gov/ordinances/docs/HomeSharing/FAQ.pdf)

## Cost and payback model

The model contains no built-in prices. Every price is an input with a source, shown on screen as an editable assumption.

**Inputs**

| Input | Source | Owner | In code today |
| --- | --- | --- | --- |
| Area, unit count, bathrooms to add, plumbing run, kitchens to add | Matterport scan | B | Yes |
| Fit-out cost per sq ft | Research | A | Yes |
| Cost per bathroom, plumbing cost per ft, cost per kitchen | Research | A | Yes |
| Sprinkler cost per sq ft, fire alarm cost | Research | A | To add |
| Seismic evaluation and retrofit cost range | Research | A | To add |
| Permit and design cost | Research | A | To add |
| Months to convert | Research | A | Yes |
| Occupancy, operating cost share | Research | A | Yes |
| Monthly rent per unit | CoStar data | B | Yes |
| Current monthly income of the space | CoStar data | B | Yes |
| Years the space stays available | Owner, set on screen | B | Yes |

**Outputs**

- Conversion cost with a breakdown by item.
- Monthly net income as housing, and the gain over what the space earns today.
- Payback period in years.
- Net gain over the years the space is available.
- Verdict: convert, or do not convert, with the reason.

**Rejection rules**

- Housing would earn no more than the space earns today.
- The cost is not recovered within the time the space is available.

Code: `secondstay/economics.py` and `secondstay/scoring.py`.

## Demo plan

The demo runs the agent on three real LA buildings and ends with the verdict changing when one assumption changes.

1. The owner types the question. The agent lists vacant office space and applies the eligibility screen.
2. **Building 1 is rejected.** A tall building: the high-rise requirements and long plumbing runs make it too costly. The agent states the reason.
3. **Building 2 is rejected or marginal.** It passes the physical checks but does not pay back in the time available.
4. **Building 3 is accepted.** A low-rise building with restrooms close to the proposed units. The 3D view shows where units and bathrooms would go.
5. The presenter changes one assumption, such as construction cost up 30% or the space needed back in two years. The verdict updates live.
6. The final screen separates observed facts, estimates, and items that need a site inspection.

Data rule from CoStar: real floor plans, model IDs and property-identifying data cannot go in the public repo or README. Showing them in the demo video and a temporary deployment is allowed.

## Team split

The two roles meet at one file, `assumptions.json`. A fills it; B builds the product that reads it.

| Area | A: research | B: product |
| --- | --- | --- |
| Cost data | Researches every construction and operating figure for LA, each with a low, typical and high value and a source | Builds with placeholder values labelled as placeholders until A's file arrives |
| Data | None | Keys, CoStar data, Matterport and Vexcel API calls, rents and current income from the data |
| Product | None | Screening, conversion plan, agent, web page, 3D view |
| Outside contact | Peri interview with a contractor, architect or broker: name, role, quote, photo | Technical questions at the CoStar table |
| Submission | Devpost text and sponsor track requirements | Demo buildings, demo flow, video, slides, repo, deployment |
| Presentation | The problem and the evidence | The live demo |

**Order of work**

1. B hands A an empty `assumptions.json` template.
2. A starts the Peri outreach and the cost research in parallel.
3. B builds against placeholders.
4. A's file replaces the placeholders. No code changes.
5. Three to four hours before the deadline: A finishes the submission text, B records the demo.

## Tracks, risks and open questions

**Tracks**

| Track | Why it fits |
| --- | --- |
| Business and Enterprise (main) | An analysis tool for property owners and investors |
| CoStar: Inside and Out | All three data layers drive the verdict |
| Amazon: Practical AI | A multi-step agent that searches, inspects, costs and decides |
| LangChain: deepagents | The agent is built with deepagents |
| Peri: Forward Deployed | Cost assumptions validated with a practitioner we interviewed |

**Risks**

| Risk | Mitigation |
| --- | --- |
| Cost figures look invented | Every figure has a source and is editable on screen; the Peri interview validates the range |
| Matterport data lacks plumbing or window detail | Use room type and dimensions; mark the rest as needs inspection |
| Few LA buildings have all three layers | Pick the three demo buildings first, before building features |
| Judges ask whether this is legal | The LA ordinance section answers it; the product screens and does not approve |
| Scope grows | Must-have list only until the demo runs end to end |

**Open questions**

- [ ] Does the CoStar data include zoning, vacancy by floor or suite, and residential rents?
- [ ] Does the Matterport API mark restrooms and windows, or only room labels and dimensions?
- [ ] Do the buildings show whether sprinklers already exist?
- [ ] Which three LA buildings will the demo use?
- [ ] Who will the Peri interview be with?
