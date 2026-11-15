# Cost model handoff

This is a preliminary evidence review, not a legal or code determination. Final decisions are made by LADBS and licensed professionals.

B's work consumes the existing `Change` contract. It does not decide which work
applies. All monetary outputs are USD, with low / typical / high endpoints.
Totals cover only the priced subset of the selected changes. `partial`, `left_out`
and `not_in_scenario` must appear alongside every total in the screen. The range
is an assumption envelope, not a statistical confidence interval or full budget.

## API and ownership

```python
from secondstay.changes import load_changes
from secondstay.costing import load_prices, estimate, compare_scenarios, sensitivity

changes = load_changes("tests/fixtures/sample_changes.json")
prices = load_prices("assumptions.json")
income = {
    "units": 25,  # Team assumption for this synthetic example
    "monthly_rent_per_unit": {"low": 1800, "typical": 2000, "high": 2200},
    "horizon_years": 5,
}
base = estimate(changes, prices, income, "base")
comparison = compare_scenarios(changes, prices, income,
                               selected_keys=["units.bathroom"])
drivers = sensitivity(changes, prices, income, count=3)
```

`estimate` accepts either a flat price dictionary or the `PriceBook` returned by
`load_prices`. `PriceBook.entries`, `.globals`, `.notes`, and computed `.issues`
separate prices, global assumptions, file metadata, and unusable entries.
`print_prices(book)` returns editable JSON preserving every stored field; a caller
can write it to a file and reload it. Neither pricing nor sensitivity mutates inputs.

Scenarios are `base`, `with_possible`, `everything`, and `custom` (the latter uses
`selected_keys`). Unknown selected keys are reported. Repeated keys move together;
each Change pays its own fixed component. A zero quantity still incurs that fixed
component. An empty selection or entirely unpriced selection has no total.

Each line includes quantity, units, fixed/rate ranges, cost, status, inclusion,
source, confidence and exclusions. `cost_with_allowances` allocates the two global
markups to each included priced line. Removing a key removes exactly those amounts.
Global soft cost and contingency must both be usable before any total is returned.
Unusable line prices or quantities do not become zero. If both are missing, the
line reports the price issue first and also names the missing quantity.

`economics.evaluate(total, income, globals)` replaces the old `ConversionPlan`,
`Assumptions`, `load_assumptions`, and single-point evaluation API. Repository search
found no application caller of that API; its tests now exercise range inputs.
Results are plain JSON mappings. Omitted current income explicitly means the Team
assumption that the space earns nothing today. **Explicit null means unavailable**,
including a leased space with no rent evidence, and suppresses payback.
Income `sources` may attach source/confidence/notes by field; otherwise the input
is visibly labelled as a Team assumption.

Payback includes the construction delay and lost current income during construction.
The favorable end uses lower prices, duration, current income and operating share,
and higher rent and occupancy. The adverse end reverses these. A nonpositive gain
has no payback at that endpoint. An invalid horizon suppresses only horizon gain.
Five years is a **proposal awaiting team agreement**, not an agreed investment period.
No acquisition price, financing, tax benefits, rent growth, discounting, lease-up
ramp or terminal sale value is modeled. Operating share includes routine expenses;
it does not model capital replacement reserves separately.

Sensitivity moves each included price key's fixed and rate components together,
then each global and income range separately, keeping other inputs at typical.
No-payback endpoints rank first, then their horizon-gain difference; finite cases
rank by absolute change in payback years. Names break ties. If the horizon is
unavailable, no-payback ties use names because a horizon-gain difference is unknown.
Sensitivity describes only the priced subset when costs are incomplete.

## Price research and derivations

Access date for every source below: **2026-11-14**. In this first price book, two
catalog entries had published local anchors; the update of 2026-11-15 further down
adds Los Angeles permit prices and published figures. The two estimates
are **Team-assumption allocations**, not disaggregated contractor quotations.
No unsupported rate was inferred from a whole-project cost.

### sprinklers.install

[SFP Sherpas, commercial sprinkler retrofit guide](https://sfpsherpas.com/fire-sprinkler-code-upgrade-retrofit-california/),
publication date not stated. Its local commercial retrofit range is approximately
$3-$7/sqft. Team assumptions: $5 midpoint; regard that range as containing a 30%
soft-cost allowance and divide by 1.30, giving **$2.307692 / $3.846154 / $5.384615
per sqft**, fixed $0. The global soft-cost factor then adds the chosen allowance
once. No date/location escalation is applied. This allocation is unverified and
must be replaced by a separated contractor quote. Pumps, tanks, service upgrades,
access and testing need scope confirmation; no additional high-rise cost is priced.

### units.bathroom

[DN Builders Group, LA bathroom additions](https://dn-builders-group.com/blog/bathroom-addition-cost-los-angeles/),
published **2026-07-18**. A full bathroom within an existing house footprint is
$25,000-$50,000 all-in. Team assumptions: $37,500 midpoint; use this as a conversion
proxy and divide by 1.30 to allocate soft costs, giving **$19,230.769231 /
$28,846.153846 / $38,461.538462 per bathroom**, fixed $0. Local bathroom plumbing
remains included; do not count it again under plumbing runs. New footprint, central
risers and utility capacity are outside this proxy. Multifamily economies of scale
and accessibility scope are not separately quantified. No escalation is applied.

### soft_cost_share, contingency, months_to_convert

[City of Los Angeles CDBG guidance, printed p.11, PDF p.17](https://cityclerk.lacity.org/onlinedocs/2022/22-1205_rpt_mayor_10-07-22.pdf),
published **2022-10-07**. Construction estimate plus 30% anchors the typical soft
share. Team range: **25% / 30% / 33.333333%** of hard cost. A 25% share of total
would mean one-third of hard cost; these denominators are not interchangeable.
Rehabilitation contingency anchors **15% / 17.5% / 20%**, midpoint selected by team.
Applying contingency to hard plus soft cost follows the requested formula and is
a Team assumption, not a direct transcription of a source denominator.

For duration, the source's community-center example gives 12 months design,
3-4 bidding and 6-18 construction. Team proxy: **21 / 27.5 / 34 months**;
this is not an office-conversion schedule. Permitting and lease-up can extend it.
The 2022 ratios and durations are reused without escalation in 2026, explicitly a
Team assumption. Financing, acquisition and omitted work are outside these allowances.

### occupancy, operating_cost_share

[AECOM LA adaptive reuse analysis, Table 5, printed p.17, PDF p.177](https://planning.lacity.gov/odocument/572f2af1-6d0c-4950-8d86-b21d65634aba/CPC-2023-5986-CA%20Citywide%20Adaptive%20Reuse%20Recommendation%20Report%20-%20full.pdf),
study dated **2024-07-31**. Anchors: 5% vacancy and 30% operating expense ratio.
Team ranges are occupancy **90% / 95% / 98%** and operating share **25% / 30% / 35%**.
The endpoints and reuse of 2024 typical ratios without a 2026 adjustment are Team
assumptions. Utility metering, taxes and insurance need property-specific confirmation.

### Update 2026-11-15: Los Angeles permit prices, building-wide work and published figures

The entries above were the first price book. Where a later price exists, the cost
screen uses it and keeps the earlier source in the line's notes. Ranges are low /
typical / high. Rates from permits are the 25th percentile, median and 75th percentile.

**Los Angeles permit price book** (`la_permit_prices.json`, built by
`python -m secondstay.la_costs`, then `--building` for building-wide work). LADBS
building permits ([2020 to present](https://data.lacity.org/d/pi9x-tg5x),
[2010 to 2019](https://data.lacity.org/d/dyxf-7hc4)) were read by a language model,
which labelled each permit's work. New buildings, revisions and other work were left out.
Declared job values tend to run below final cost.

| Key | Unit | Low / typical / high | Permits | How it was measured |
|---|---|---|---|---|
| units.kitchen | each | $6,000 / $10,000 / $17,000 | 231 | Apartment kitchen work, value per kitchen stated |
| units.bathroom | each | $5,000 / $7,200 / $10,000 | 544 | Apartment bathroom work, value per bathroom stated |
| units.fitout | sqft | $31.66 / $58.33 / $71.57 | 521 | Interior work in commercial space, value per stated sq ft |
| sprinklers.install | sqft | $2.77 / $8.77 / $18.42 | 142 | Whole-building sprinkler jobs, value per sq ft of building |
| seismic.strengthen | sqft | $3.19 / $5.37 / $7.76 | 594 | Whole-building seismic strengthening, value per sq ft of building |
| highrise.emergency_power | lump | $30,000 / $55,000 / $100,000 | 21 | Generator jobs on buildings of at least 50,000 sq ft |
| elevator.fire_service_access | each | $65,000 / $180,000 / $240,000 | 25 | New or modernised cars on large buildings, value per car |

Building-wide permits rarely state the building's size, so each permit was joined by
its parcel number to the [LA County assessor's building area](https://public.gis.lacounty.gov/public/rest/services/LACounty_Cache/LACounty_Parcel/MapServer/0).
Fewer than 8 usable permits leaves a key out of the book: fire alarm (2), fire pump
(1), smoke control (4) and fire command center (0) fell short. LADBS fire sprinkler
and electrical permits were also checked; their values are those of the whole
project or are empty, so they were not used.

**sprinklers.verify_coverage** (confirm and adapt an existing system). It is now
measured in sq ft over the area to be converted, not as one study. No source prices
adapting a system alone, so the LA install rate above is used as an upper estimate.
Cross-check: LAFD estimated $6,000 per home to add sprinklers to existing residential
high-rises (2017 recommendation, reported by Gov1 in 2020; the link is kept in `la_permit_prices.json` under `published`),
about $9 per sq ft at 625 gross sq ft per home. That is close to the permit median.

**Elevators** (rules, not prices). [CBC 403.6.1](https://gocodebook.com/library/us/ca/ca-building-code/chapter-4-special-detailed-requirements-based-on-occupancy-and-use/section-403-high-rise-buildings-and-group-i-2-occupancies-having-occupied-floors)
(2025 edition): with an occupied floor more than 120 ft up, not fewer than two fire
service access elevators, or all elevators if fewer, each at least 3,500 lb and
meeting CBC 3002.4 (stretcher size). The change list therefore counts two fire
service access cars and no separate gurney-sized car. Below 120 ft, buildings of more
than four stories get one gurney-sized car (CBC 3002.4.1a).

**Published figures** (in `assumptions.json`, confidence "estimated"):

| Key | Unit | Low / typical / high | Source and reading |
|---|---|---|---|
| seismic.evaluate | lump | $15,000 / $40,000 / $100,000 | [MMCG Invest guide](https://www.mmcginvest.com/post/seismic-risk-in-commercial-real-estate-the-definitive-guide-for-lender-developers-and-investors), 2026-04-08: ASCE 41 Tier 2 $15,000-$40,000, Tier 3 $30,000-$100,000+. One industry guide; tall concrete buildings may cost more; coring and material testing are excluded |
| highrise.fire_pump_water_supply | lump | $90,000 / $350,000 / $675,000 | [San Francisco Budget and Legislative Analyst](https://media.api.sf.gov/documents/BLA.High_Rise_Sprinkler_Retrofit_Costs.080326.pdf), 2026-08-03, built from C-16 contractor interviews for a 50-unit residential high-rise. Low: pump only. Typical: pump $150,000 plus pump room $200,000. High: pump upgrade, pump room and fire service line |
| fire_alarm.install | sqft | $0.32 / $0.64 / $16.64 | Same report: alarm to NFPA 72 $200-$400 per home, electrical upgrades up to $10,000 per home, divided by 625 gross sq ft per home |
| highrise.fire_command_center | lump | $150,000 / $200,000 / $300,000 | Same report, a proxy: a dedicated 100-200 sq ft pump room. A command center is a dedicated room of at least 200 sq ft; its panels are excluded |

San Francisco figures are used without a location adjustment.

**Least to open one home.** Converting one home brings the whole building under
the rules. The screen therefore shows called-for building-wide work in full plus one
home's average share of the per-home work (fit-out, kitchen, bathroom, and coverage
adaptation over the converted area). Possible building-wide work is shown beside
it, as an amount that may be added, never inside the minimum.

### Keys still unpriced

| Key | Missing price basis |
|---|---|
| highrise.smoke_control | Too few LA permits; not in the San Francisco report |
| highrise.smokeproof_stairs | No LA permit key; not in the San Francisco report |
| planning.conditional_use_permit | Site-specific planning application and consultant scope |
| egress.add_stair | Per-story structural and enclosure design |
| escape.add_openings | Per-opening size, wall construction and support |
| historic.review | Fixed consultant scope and hours |
| units.plumbing_run | Main and riser routing; bathroom-local runs already counted |

Overlap checks: the AECOM construction benchmarks include MEP, interior work,
soft costs and contingency; they cannot be assigned to `units.fitout` and added
to individual systems. They are excluded from the price book. The
[LAFD high-rise study](https://cityclerk.lacity.org/onlinedocs/2020/20-0146_rpt_07-30-21.pdf)
(2021-07-30, Tables C-1 to C-3) includes permit fees and pump/standpipe/water work,
so its bundled rates are also not added. Price-book notes preserve exclusions and
the reason for each empty entry. An incomplete total is never a full project budget.

## Rent definitions and comparable choice

The encrypted kit's `concepts/metrics-and-formulas.md`, `concepts/apartments.md`,
`models/apartment-listing.md` and property field reference were read on 2026-11-14.
The kit stayed outside the repository; no private record or identifier is retained.

`rents.apartment_rent(listings, space, ...)` consumes raw `apartmentModels[]`.
Monthly `minRent`/`maxRent` use the midpoint when both are present, or the sole
positive endpoint. Zero means missing. `rentPricingType=1` is per unit;
`3` multiplies by positive `numBeds`. Per-bed (`2`) and unknown bases are excluded
because bedrooms do not establish physical bed occupancy. `monetaryUnit=0` is
treated as USD following this US-only kit's definition; other currencies except
`1` are excluded. Plans are equally weighted for the 25th/50th/75th percentiles
using linear interpolation. These are floor-plan asking rents, not achieved rents.
No concessions or unit-availability weights are applied.

**Default proposal: distance, 3 miles, minimum 3 floor plans**. This is configurable
and is a Team assumption. `bedrooms=0` selects studios. `primarySubmarketId` is
building-type-specific: an office submarket cannot safely identify apartment
competitors. Submarket mode requires the caller to supply the intended apartment
submarket. Distance uses great-circle miles and validated coordinates from listing
`address`, falling back to property `primaryAddress` joined on `propertyId`/`id`.
Comparable input positions identify used rows without exporting record IDs.

`properties` plus `metering_type=1` (master) or `2` (individual) can restrict
comparables to matching utility responsibility; missing/mismatched metering is
then excluded. Without this filter the output explicitly says metering was not
matched. Do not treat the resulting rent as evidence for an operating-cost ratio.

Kit check (2026-11-14): read 767 California apartment listings in memory. At the
first 20 apartment-community locations, one-bedroom selection found at least three
plans for every target under both methods. Median comparable counts were 1,038
within 3 miles and 76 within the same apartment submarket. These are aggregate
diagnostics, not office-target validation or representative market statistics.
Both methods also have synthetic boundary/filter tests. Distance remains the
default because it works across property types; the broad radius needs owner review.

The follow-up check used all 89 existing LA offices with scans, selected by the
existing adapter's criteria. Within 3 miles, 88 had at least three one-bedroom
plans (median 386). Matching their office `primarySubmarketId` directly found none
for all 89. This confirms the cross-property-type submarket mismatch. Office
asking-income calculations returned figures for 45 of 89 targets, consistent with
the adapter's coverage. Only aggregate counts were retained; individual records
were read in memory. This validates rent handling, not full conversion costs.

`office_income` consumes active `forLeaseSummary.spaces[]` without `dateOffMarket`.
`rateBasis=1` multiplies monthly rates by 12; `2` is yearly. Typical annual rent is
weighted by available sqft using each space's quote midpoint; low/high use the
lowest/highest quote. If any usable quote lacks a listing area, typical uses the
unweighted median of space quote midpoints, labelled as a Team assumption.
Target area is still required. Multiply by target space area / 12. Missing rates are not
zero. Mixed `serviceType` values are listed and labelled; no expense normalization
is invented. Caller must supply listings for the intended building once, without
duplicates. `vacancy_indicators` sums largest marketed space areas and current
tenancy areas, counts incomplete tenancy areas, and clamps the unrecorded share.

`build_income` combines these outputs and provenance for `estimate`. `space` holds
`area_sqft`, `rentable_sqft`, coordinates and optionally `primarySubmarketId`.
Its `units` and `vacant` arguments are explicit caller assumptions.

## Open questions for the handoff

- **Integration:** add the cost panel, scenario selector, omitted-work lists,
  sensitivity and notice. Update README's old score and recommendation language.
- **Integration/A:** supply planned unit count and source, target area, office
  asking-rent records and explicit space vacancy. Confirm scope across building
  and scanned-suite costs; building work may serve more than the modeled units.
- **Team:** confirm five-year horizon, apartment bedroom/metering filters and
  whether these local research anchors are sufficient for the demonstration.
- **A:** confirm final catalog, repeated-key possibility and high-rise package
  contents. New keys remain visibly unpriced until researched.
- **Owner to confirm:** older scoring module and its tests remain outside B's files.
- **Integration verified (2026-11-14):** A's real change generator and the financial
  adapter ran on 89 CoStar buildings and 883 listed suites without scans. Outputs
  serialized as strict JSON; suite fit-out quantities matched their listing areas.
  Studio rent comparables were available for 88 buildings. All 89 base estimates
  remained partial, and current income remained explicitly unknown. This does not
  validate contractor pricing, scan coverage or professional determinations.
- **Screen verification:** 144 automated tests and live local HTTP recalculation
  passed. Browser visual checks were blocked by unavailable browser access and
  unsupported URL-policy enforcement in the available Windows Firefox window.
- **Pricing:** obtain separated contractor quotes for the 7 keys still unpriced and
  replace the two provisional soft-cost allocations and the duration proxy.
