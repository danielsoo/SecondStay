# Requirements research: what the published rules call for

Read on 2026-11-14. This is a preliminary evidence review, not a legal or code determination.
Final decisions are made by LADBS and licensed professionals.

## Sources read

| Short name | Document | What was read |
| --- | --- | --- |
| ARO page | [LA City Planning: Adaptive Reuse](https://planning.lacity.gov/project-review/adaptive-reuse) | Whole page |
| Bulletin | [LADBS IB-BC-2026-164, Change of Occupancy from Office to Residential](https://dbs.lacity.gov/sites/default/files/efs/forms_and_publications/publications/information-bulletins/building-code/2026/IB-BC-2026-164-Change_Occupancy_Office_Residential.pdf), effective 09-14-2026 | All 7 pages |

Not read: the ordinance text itself (No. 188,793), the building code sections the bulletin cites, the
Home-Sharing FAQ behind the stay-length row, and LADBS bulletin P/BC 2026-148 on reduced seismic forces.
The bulletin says of itself that it is general guidance and not a complete list of code requirements.

## Each checklist row against its source

| Row | What the source says | Where | Result |
| --- | --- | --- | --- |
| Building age | Buildings at least 15 years old qualify. Any existing building at least 5 years old qualifies subject to Zoning Administrator approval; buildings at least 5 but under 15 years old need a Class 1 Conditional Use Permit | ARO page, paragraph 2 and "Discretionary Approvals" | Confirmed. Added: under 5 years there is no path described |
| Zone | R2, RD1.5, RD2, RD3, RD4, RD5, RD6, RW2, R3, RAS3, R4, RAS4, R5, CR, C1, C1.5, C4, C2, C5, CM, P, PB, PF | ARO page, footnote 1 | Confirmed: the 23 classes in the code match. Added: manufacturing zones inside an Adaptive Reuse Subarea go to a Conditional Use Permit |
| Unit count | The ordinance covers conversions "resulting in the creation of five or more residential units". Minimum unit size rules were removed; units can be as small as the Building Code allows | ARO page, paragraph 1 and incentives list | Confirmed. Our 500 sq ft per unit is a planning assumption, not a rule |
| Height | High-rise provisions. Heights are "measured from the lowest level of fire department access level to the highest occupied level" | Bulletin IV (high-rise), V, VI | **Corrected.** The threshold is to the highest occupied level, not the roof. The row now estimates that level |
| Exits per story | Means of egress follow CBC Chapter 10: exits per story, distance between exits, travel distances. All exit stairways enclosed (CBC 1023). An existing fire escape in good condition may be a second means of egress | Bulletin IV | Confirmed in general. The number of exits per story is in CBC Chapter 10, which was not read; "two stairs per story" in the code is our working assumption |
| Escape openings | Where the change of occupancy calls for them, they follow CEBC 506.4 or 1011.5.6, with size tolerances for existing windows | Bulletin IV.3 | Confirmed. Which sleeping rooms need one is in the cited sections, not read |
| Fire separation distance | Wall ratings depend on fire separation distance (CBC 705.5), but office to residential "generally will not require an increase", and existing unrated openings may stay | Bulletin III | **Corrected.** This row no longer leads to any change |
| Fire access and exit discharge | Exit discharge under existing canopies may be accepted case by case with a water curtain | Bulletin IV.2 | Only partly covered. Fire vehicle access is not discussed in either source |
| Elevator | At least one gurney-sized car serving all occupied levels (CBC 3002.4.1a). Not needed for buildings of four stories or fewer above and below grade. Occupiable levels more than 120 ft up need a fire service access elevator | Bulletin V | Confirmed. Added the 120 ft rule |
| Stay length | Not checked | Home-Sharing FAQ, not read | Unverified |
| Sprinklers | "Buildings with new residential occupancy must be fully fire sprinklered"; NFPA 13, or 13R where permitted | Bulletin II and VI | Confirmed |
| Fire alarm | A fire alarm throughout the building, NFPA 72 (CBC 907.2) | Bulletin VI | Confirmed |
| Seismic | Analysed at 75 percent of the design earthquake ground motion and strengthened as required (CEBC 506.5.3 or 1006.3). Non-ductile concrete and unreinforced masonry buildings have their own rules | Bulletin IX | Confirmed |
| Historic status | Surveyed Historic Resources need Administrative Review. Designated resources and HPOZ properties need a Conditional Use Permit | ARO page | Confirmed |

## Answers to the open questions

1. **How is 75 ft measured?** To the highest occupied level, from the lowest level of fire department access (Bulletin IV). Our imagery gives the highest roof point, so the code now estimates the top floor as roof height less one story.
2. **Whole building or part?** The ARO page speaks of existing buildings and does not address part of one. The bulletin does: for a partial change of occupancy that does not change the Risk Category, LADBS will consider a modification of the seismic retrofit, case by case (Bulletin IX, last paragraph). Still open for the planning side.
3. **Which high-rise systems?** Smokeproof or pressurised exit stairs, Class I standpipes, fire pump and secondary water supply, emergency generator, fire command center, smoke control, emergency responder radio coverage (Bulletin IV and VI). The catalog now has one key per system we expect to be priced separately. An emergency helicopter landing facility is not called for if none exists.
4. **Elevator above four stories?** One gurney-sized car serving all occupied levels, and a fire service access elevator above 120 ft (Bulletin V).
5. **Which zones?** The 23 listed above. Manufacturing zones only inside an Adaptive Reuse Subarea, by Conditional Use Permit.
6. **Partly sprinklered buildings?** Not addressed. The rule is full coverage, so a system on record leads to a "confirm coverage" change.

## Decision table: evidence to changes

Implemented in `secondstay/changes.py`, `changes_for`. A requirement whose evidence already fits the rule produces nothing.

| Requirement | Evidence | Change | Certainty | Quantity |
| --- | --- | --- | --- | --- |
| Building age | 5 to under 15 years old | `planning.conditional_use_permit` | called_for | 1 |
| Building age | Under 5 years, or no year on record | none; the row itself flags it | | |
| Zone | Manufacturing zone (MR1, M1, MR2, M2, M3) | `planning.conditional_use_permit` | possible | 1 |
| Zone | Any other unlisted zone | none; no path is described | | |
| Historic status | Always | `historic.review` | unknown | 1 |
| Sprinklers | Record shows none | `sprinklers.install` | called_for | Building rentable area |
| Sprinklers | Record shows a system | `sprinklers.verify_coverage` | possible | 1 |
| Sprinklers | Nothing on record | `sprinklers.install` | unknown | Building rentable area |
| Fire alarm | Always | `fire_alarm.install` | unknown | Building rentable area |
| Height | Top occupied level estimated at 75 ft or more | five `highrise.*` changes | possible | 1 each; stairs unknown |
| Height | Estimated between 60 and 75 ft, or imagery and record do not fit together | five `highrise.*` changes | unknown | same |
| Height | Estimated above 120 ft | `elevator.fire_service_access` | possible | 1 |
| Elevator | More than four stories | `elevator.gurney_car` | possible | 1 |
| Seismic | Always | `seismic.evaluate` | called_for | 1 |
| Seismic | Always | `seismic.strengthen` | unknown | Building rentable area |
| Exits per story | Labelled scan of two or more floors, a floor with fewer than two stairs | `egress.add_stair` | possible | Number of such floors |
| Exits per story | Stairs not identified | `egress.add_stair` | unknown | none |
| Escape openings | Always, until windows are read from the scan | `escape.add_openings` | unknown | none |
| Unit count | Scan area, else building area | `units.fitout`, `units.kitchen`, `units.bathroom` | called_for | Area; units; units minus bathrooms in the scan |
| Fire separation, fire access, stay length | Any | none | | |

Why high-rise changes are "possible" and not "called_for": the rule applies, but an office tower often has
these systems already, and what is installed is not in our data.

Our own assumptions, not rules: 10 ft per story when no height is measured; top floor taken as roof height
less one story; 60 ft as the lower edge of "close to the threshold"; two stairs per story; 80% usable area
and 500 sq ft per unit; one kitchen and one bathroom per unit.

## What came out on the 89 buildings

Using each building's most informative scan. Median 16 changes per building.

| Certainty | Changes | Mostly |
| --- | --- | --- |
| called_for | 358 | Fit-out, kitchens, bathrooms, seismic analysis. Sprinkler installation on 3 buildings, a Conditional Use Permit on 1 |
| possible | 433 | High-rise systems on 51 buildings, gurney-sized elevator on 60, fire service elevator on 39, sprinkler coverage on 59, permit for 16 manufacturing-zone buildings, second stair on 4 |
| unknown | 513 | Fire alarm, seismic strengthening, historic review, escape openings on all; second stair on 85 |

Three changes never have a quantity yet: smokeproof stairs (number of stairs), second stair (85 buildings)
and escape openings.

## Rule summaries corrected in the checklist

- **Height:** measured to the highest occupied level, and the list of high-rise systems.
- **Fire separation distance:** generally no upgrade is called for.
- **Building age:** the 5-year minimum and the name of the approval.
- **Elevator, sprinklers, fire alarm, seismic, exits, escape openings, historic:** wording tightened and code sections added.

## Catalog changes the cost model needs to know

- `highrise.systems` is replaced by `highrise.smokeproof_stairs`, `highrise.fire_pump_water_supply`,
  `highrise.emergency_power`, `highrise.fire_command_center`, `highrise.smoke_control`.
- `elevator.upgrade` is replaced by `elevator.gurney_car` and `elevator.fire_service_access`.
- `separation.wall_upgrade` is removed.
- `planning.conditional_use_permit` is new.
- The bulletin also calls for mechanical, plumbing, lighting and power systems to meet the energy code for
  multifamily use (Bulletin VIII). There is no separate key; it belongs in the price of `units.fitout`.
- `changes_for` takes the current year as a third argument: `changes_for(facts, rows, current_year)`.
