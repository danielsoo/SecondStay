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

Access date for every source below: **2026-11-14**. Two catalog entries have
published local anchors; thirteen deliberately remain unpriced. The two estimates
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

### Why the remaining keys are unpriced

| Key | Missing price basis / intended scale |
|---|---|
| sprinklers.verify_coverage | Survey scope and access; fixed study quote needed |
| fire_alarm.install | Isolated retrofit system rate per sqft not established |
| seismic.evaluate | Investigation/testing scope; fixed engineer quote needed |
| seismic.strengthen | Structural design; no defensible per-sqft rate yet |
| highrise.systems | Package not settled; pump overlap with sprinklers unresolved |
| egress.add_stair | Per-story structural/enclosure design and dimensions |
| escape.add_openings | Per-opening size, wall construction and support |
| elevator.upgrade | Per-elevator equipment/shaft/modernization scope |
| separation.wall_upgrade | Wall height, assembly and access per linear foot |
| historic.review | Fixed consultant scope/hours |
| units.fitout | Residual interior scope after separately priced systems |
| units.kitchen | New kitchenette scope, not a household remodel proxy |
| units.plumbing_run | Main/riser routing and capacity; bathroom-local runs already counted |

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
- **Integration after merge:** run A's real change generator across the 89-building
  cohort. B cannot fabricate those change lists from raw building records.
- **Pricing:** obtain separated contractor quotes for the 13 unpriced keys and
  replace the two provisional soft-cost allocations and the duration proxy.
