# Requirements Document

## Introduction

The cost model is the financial half of SecondStay, owned by Teammate B. It takes the change list that Teammate A produces (the `Change` dataclass in `secondstay/changes.py`) and turns it into cost ranges per change, a total per scenario, the income the space could earn as housing, a payback range, and the inputs that move payback the most. It also builds the income inputs (rent per unit, what the space earns today, how empty the building is) from CoStar records passed in by the caller.

The cost model outputs numbers and ranges only. It never says whether a conversion is allowed or worth doing, never gives a score or an overall result, and every result carries the fixed notice. It replaces the conclusion strings in the current `secondstay/economics.py` ("Convert", "Do not convert") and keeps the payback arithmetic.

The current `assumptions.json` is keyed by cost names (`fitout_cost_per_sqft`, `cost_per_bathroom`, ...) and the current loader raises when a value is empty. This feature rekeys the file by catalog change key and treats empty values as "not priced" instead of raising.

Constraints that apply to all requirements:

- B edits only: `secondstay/costing.py` (new), `secondstay/economics.py`, `secondstay/rents.py` (new), `assumptions.json`, `tests/test_costing.py` (new), `tests/test_economics.py`, `tests/fixtures/sample_changes.json`, `docs/cost-sources.md` (new).
- B does not edit Teammate A's files (`secondstay/changes.py`, `secondstay/checklist.py`, `tests/test_changes.py`, `tests/test_checklist.py`, `docs/requirements-research.md`) or integration's files (`secondstay/web.py`, `secondstay/static/`, `secondstay/costar.py`, `secondstay/matterport.py`, `secondstay/vexcel.py`, `secondstay/prefetch.py`, `PRD.md`, `README.md`). Requests for those files go in the Open questions list.
- Work happens on a branch named `cost`. `.env` and `data/raw/` stay git-ignored. Generated files and caches are not committed.
- No real CoStar record, address, property id, floor plan or Matterport model id goes in the repo, tests or docs.

## Glossary

- **Change**: One piece of work the published rules call for, as defined by the `Change` dataclass in `secondstay/changes.py`. Fields: key, requirement, title, certainty, quantity, unit, quantity_basis, scope, reason, source_url, confirmed_by.
- **Change_List**: The ordered list of Changes for one space, produced by Teammate A's rules work.
- **Catalog**: The `CATALOG` mapping in `secondstay/changes.py` from change key to unit.
- **Range**: Three values of one quantity at the levels low, typical and high.
- **Ordered_Range**: A Range where low ≤ typical ≤ high.
- **Price_Book**: The contents of `assumptions.json`: Price_Entries, Global_Entries and file notes.
- **Price_Entry**: The Price_Book record for one change key: unit, Fixed_Range, Rate_Range, source, publication date, date accessed, confidence, an excludes note, notes, and an optional reason for leaving the key unpriced.
- **Fixed_Range**: The Range of the fixed dollar amount of a Price_Entry, paid once per Change whatever its quantity.
- **Rate_Range**: The Range of the dollar amount per unit of quantity of a Price_Entry.
- **Global_Entry**: A Price_Book record that applies to the whole estimate: soft cost share, contingency, months to convert, occupancy, operating cost share. Each holds a Range plus source, publication date, date accessed, confidence and notes.
- **Share_Entry**: A Global_Entry whose values are fractions: soft cost share, contingency, occupancy, operating cost share.
- **File_Notes**: Top-level Price_Book keys that start with "_", such as `_about`.
- **Usable_Entry**: A Price_Entry or Global_Entry whose values are all filled in, numeric, finite, form an Ordered_Range, lie in the allowed interval, and whose source is not empty.
- **Price_Book_Loader**: The function that reads `assumptions.json` into a Price_Book.
- **Price_Book_Printer**: The function that writes a Price_Book back into the `assumptions.json` file format.
- **Cost_Model**: The `estimate(changes, prices, income, scenario)` function in `secondstay/costing.py` and the functions it uses.
- **Line**: The Cost_Model output for one Change.
- **Line_Range**: The Range of the dollar cost of one priced Line before soft costs and contingency.
- **Line_Status**: One of "priced", "not priced", "quantity unknown".
- **Scenario**: The set of Changes that count toward a total. One of Base, With_Possible, Everything, Custom.
- **Base**: The Scenario holding Changes with certainty "called_for".
- **With_Possible**: The Scenario holding Changes with certainty "called_for" or "possible".
- **Everything**: The Scenario holding every Change in the Change_List.
- **Custom**: The Scenario holding the Changes whose keys are in a selection made by the owner.
- **Multiplier**: (1 + soft cost share) × (1 + contingency) at one level.
- **Scenario_Total**: The Range of the total dollar cost of a Scenario after the Multiplier.
- **Left_Out_List**: The Changes in a Scenario whose Line_Status is "not priced" or "quantity unknown", each with its reason.
- **Not_In_Scenario_List**: The Changes in the Change_List that the chosen Scenario excludes.
- **Estimate**: The full Cost_Model result for one Change_List, Price_Book and Scenario.
- **Scenario_Comparison**: The Estimates for several Scenarios of one Change_List, side by side.
- **Income_Inputs**: Unit count, monthly rent per unit Range, current monthly income Range and horizon years, supplied by the caller. Occupancy, operating cost share and months to convert come from the Price_Book.
- **Payback_Calculator**: The function that turns a Scenario_Total and Income_Inputs into monthly net income, monthly gain, payback and gain over the horizon.
- **Payback_Result**: The output of the Payback_Calculator.
- **Favourable_End**: For each input, the value that shortens payback: low for every price, soft cost share, contingency, months to convert, operating cost share and current monthly income; high for monthly rent per unit and occupancy.
- **Unfavourable_End**: For each input, the value at the opposite end of its Range from the Favourable_End.
- **Sensitivity_Analyzer**: The function that ranks inputs by how much they move payback for one space.
- **Sensitivity_Input**: One input the Sensitivity_Analyzer varies.
- **Swing**: For one Sensitivity_Input, the absolute difference between payback years with that input at its low value and at its high value, every other input at typical.
- **Rent_Module**: The pure functions in `secondstay/rents.py` that build Income_Inputs from CoStar records passed in as arguments.
- **Comparable**: An apartment floor-plan asking rent record that the Rent_Module selects for a space.
- **Team_Assumption**: A value set by the SecondStay team rather than taken from a published source.
- **Fixed_Notice**: The text "This is a preliminary evidence review, not a legal or code determination. Final decisions are made by LADBS and licensed professionals."
- **Banned_Words**: The pattern used in `tests/test_checklist.py`: the words legal, illegal, compliant, approved, eligible, pass, passes, fail, fails, verdict (whole words, any case), and the phrases "can be converted" and "cannot be converted".
- **Cost_Sources_Doc**: The file `docs/cost-sources.md`.
- **Owned_Files**: The files B may edit, listed in the Introduction.
- **Test_Suite**: All tests under `tests/`.

## Requirements

### Requirement 1: Price book keyed by change key

**User Story:** As Teammate B, I want the price book to hold one entry per catalog change key, so that every Change can be matched to its price without a translation table.

#### Acceptance Criteria

1. THE Price_Book SHALL contain one Price_Entry for each key in the Catalog.
2. THE Price_Entry SHALL record the unit, Fixed_Range, Rate_Range, source, publication date, date accessed, confidence, excludes note and notes.
3. THE Price_Entry SHALL record the same unit as the Catalog records for the same key.
4. THE Price_Book SHALL hold soft cost share, contingency, months to convert, occupancy and operating cost share as Global_Entries.
5. THE Price_Book SHALL record each confidence as one of "observed", "estimated" or "needs inspection".
6. WHERE a Price_Entry is deliberately left unpriced, THE Price_Entry SHALL record the reason for leaving the key unpriced.
7. THE Price_Book SHALL hold the cost previously stored under fitout_cost_per_sqft, cost_per_bathroom, plumbing_cost_per_ft, cost_per_kitchen, sprinkler_cost_per_sqft, fire_alarm_cost_per_sqft and seismic_cost_per_sqft in the Price_Entries units.fitout, units.bathroom, units.plumbing_run, units.kitchen, sprinklers.install, fire_alarm.install and seismic.strengthen.
8. THE Price_Book SHALL hold the share previously stored under permit_design_share in the soft cost share Global_Entry.

### Requirement 2: Loading the price book

**User Story:** As Teammate B, I want a half-filled price book to load without errors, so that the cost model runs while research is still filling in prices.

#### Acceptance Criteria

1. WHEN the Price_Book file is read, THE Price_Book_Loader SHALL return every Price_Entry and Global_Entry in the file, including entries with empty values.
2. THE Price_Book_Loader SHALL keep File_Notes separate from Price_Entries and Global_Entries.
3. IF a Fixed_Range, Rate_Range or Global_Entry Range has an empty value, THEN THE Price_Book_Loader SHALL mark the entry as not a Usable_Entry with the reason "price not filled in".
4. IF an entry has an empty source, THEN THE Price_Book_Loader SHALL mark the entry as not a Usable_Entry with the reason "no source recorded".
5. IF an entry has a value that is not a number or is not finite, THEN THE Price_Book_Loader SHALL mark the entry as not a Usable_Entry with a reason naming the field.
6. IF an entry has a Range with low greater than typical or typical greater than high, THEN THE Price_Book_Loader SHALL mark the entry as not a Usable_Entry with the reason "range out of order".
7. IF a Price_Entry has a negative value, THEN THE Price_Book_Loader SHALL mark the Price_Entry as not a Usable_Entry with the reason "negative price".
8. IF a Share_Entry has a value below 0 or above 1, THEN THE Price_Book_Loader SHALL mark the Share_Entry as not a Usable_Entry with the reason "share outside 0 to 1".
9. IF the months to convert Global_Entry has a negative value, THEN THE Price_Book_Loader SHALL mark the Global_Entry as not a Usable_Entry with the reason "negative duration".
10. IF the Price_Book file is missing or is not valid JSON, THEN THE Price_Book_Loader SHALL raise an error that names the file path.

### Requirement 3: Writing the price book back

**User Story:** As an owner editing an assumption, I want the edited price book saved in the same format, so that my change survives a reload.

#### Acceptance Criteria

1. THE Price_Book_Printer SHALL format a Price_Book as JSON in the Price_Book file format, including File_Notes.
2. FOR ALL Price_Books, loading then printing then loading SHALL produce an equivalent Price_Book (round-trip property).
3. FOR ALL Price_Book files that the Price_Book_Loader reads, printing the loaded Price_Book SHALL keep every key, value and text field of the file.

### Requirement 4: Pricing one change

**User Story:** As an owner, I want each change priced as a low-to-high range, so that I see what each piece of work may cost and where the price came from.

#### Acceptance Criteria

1. WHEN a Change has a Usable_Entry, a finite quantity of zero or more, and a unit equal to the Price_Entry unit, THE Cost_Model SHALL set the Line_Status to "priced".
2. WHEN a Line is priced, THE Cost_Model SHALL compute the Line_Range at each level as the Fixed_Range value plus the Rate_Range value multiplied by the Change quantity, both at that level.
3. THE Cost_Model SHALL produce one Line per Change in the Change_List, in the order of the Change_List.
4. THE Line SHALL include the change key, title, requirement, certainty, scope, quantity, unit, quantity basis, Fixed_Range, Rate_Range, Line_Range, Line_Status, reason, source, confidence and whether the Change is in the Scenario.
5. FOR ALL priced Lines, THE Cost_Model SHALL produce a Line_Range that is an Ordered_Range (invariant).
6. FOR ALL Change_Lists and Price_Books, THE Cost_Model SHALL leave the Change_List and the Price_Book unchanged after producing an Estimate.
7. FOR ALL Change_Lists and Price_Books, THE Cost_Model SHALL produce the same Estimate each time it is given the same inputs (idempotence).

### Requirement 5: Changes the model cannot price

**User Story:** As an owner, I want changes without a price or a size shown by name with the reason, so that the total does not hide missing work.

#### Acceptance Criteria

1. IF a Change key has no Price_Entry, THEN THE Cost_Model SHALL set the Line_Status to "not priced" with the reason "no price for this change key".
2. IF a Change key has a Price_Entry that is not a Usable_Entry, THEN THE Cost_Model SHALL set the Line_Status to "not priced" with the reason the Price_Book_Loader recorded.
3. IF a Change key has a Price_Entry that records a reason for leaving the key unpriced, THEN THE Cost_Model SHALL set the Line_Status to "not priced" with that recorded reason.
4. IF a Change unit differs from the Price_Entry unit, THEN THE Cost_Model SHALL set the Line_Status to "not priced" with a reason naming both units.
5. IF a Change quantity is None, THEN THE Cost_Model SHALL set the Line_Status to "quantity unknown" with a reason that includes the Change quantity basis.
6. IF a Change quantity is negative or not finite, THEN THE Cost_Model SHALL set the Line_Status to "quantity unknown" with the reason "quantity is not a usable number".
7. IF a Change meets a "not priced" condition and a "quantity unknown" condition, THEN THE Cost_Model SHALL set the Line_Status to "not priced" with a reason naming both conditions.
8. WHILE a Line_Status is "not priced" or "quantity unknown", THE Cost_Model SHALL report the Line_Range as empty.
9. FOR ALL Change_Lists and Price_Books, including empty, partly filled and malformed Price_Entries, THE Cost_Model SHALL return an Estimate without raising an exception.

### Requirement 6: Scenarios

**User Story:** As an owner, I want to see the total for called-for work, for called-for plus possible work, for everything, and for my own selection, so that I can ask "what if the building already has sprinklers?".

#### Acceptance Criteria

1. WHEN the Base Scenario is chosen, THE Cost_Model SHALL include the Changes with certainty "called_for".
2. WHEN the With_Possible Scenario is chosen, THE Cost_Model SHALL include the Changes with certainty "called_for" or "possible".
3. WHEN the Everything Scenario is chosen, THE Cost_Model SHALL include every Change in the Change_List.
4. WHEN the Custom Scenario is chosen, THE Cost_Model SHALL include every Change whose key is in the owner's selection, whatever its certainty.
5. IF the owner's selection names a key that no Change in the Change_List carries, THEN THE Cost_Model SHALL list that key in the Estimate with the reason "not in the change list".
6. IF a Scenario name other than Base, With_Possible, Everything or Custom is given, THEN THE Cost_Model SHALL raise an error that lists the four Scenario names.

### Requirement 7: Scenario total

**User Story:** As an owner, I want each scenario total as a range that includes design, permits and contingency, so that I see the full likely spread of cost.

#### Acceptance Criteria

1. THE Cost_Model SHALL compute the Scenario_Total at each level as the sum of the Line_Range values at that level over the priced Lines in the Scenario, multiplied by the Multiplier at that level.
2. THE Cost_Model SHALL report the Scenario_Total as its low, typical and high values together.
3. THE Cost_Model SHALL report the soft cost amount and the contingency amount at each level next to the Scenario_Total.
4. THE Cost_Model SHALL report, for each priced Line in the Scenario, the Line_Range multiplied by the Multiplier at each level.
5. IF the soft cost share or contingency Global_Entry is not a Usable_Entry, THEN THE Cost_Model SHALL report the Scenario_Total as empty with a reason naming the entry.
6. IF the Scenario holds no priced Line, THEN THE Cost_Model SHALL report the Scenario_Total as empty with the reason "no priced changes in this scenario".
7. FOR ALL Estimates with a Scenario_Total, THE Cost_Model SHALL produce a Scenario_Total that is an Ordered_Range (invariant).
8. FOR ALL Change_Lists, reordering the Change_List SHALL produce the same Scenario_Total within a relative tolerance of 1e-9 (confluence).
9. FOR ALL Custom selections with a Scenario_Total, removing one key while the remaining selection still holds a priced Line SHALL lower the Scenario_Total at each level by the sum of the Line_Range values of the priced Changes with that key multiplied by the Multiplier at that level, within a relative tolerance of 1e-9.
10. FOR ALL Custom selections A and B where A is a subset of B and both have a Scenario_Total, THE Cost_Model SHALL report a Scenario_Total for A no greater than the Scenario_Total for B at each level (metamorphic property).
11. FOR ALL Change_Lists where Base, With_Possible and Everything each have a Scenario_Total, THE Cost_Model SHALL report Base ≤ With_Possible ≤ Everything at each level.
12. FOR ALL Change_Lists, adding a Change whose Line_Status is "not priced" or "quantity unknown" SHALL leave the Scenario_Total unchanged.

### Requirement 8: What is left out of the total

**User Story:** As an owner, I want the changes left out of a total listed next to it, so that I know the total is incomplete and why.

#### Acceptance Criteria

1. THE Estimate SHALL include the Left_Out_List, giving for each Change its key, title, Line_Status and reason.
2. THE Estimate SHALL include the Not_In_Scenario_List, giving for each Change its key, title, certainty and the reason "not in this scenario".
3. FOR ALL Estimates, THE Cost_Model SHALL place each Change in the Change_List in exactly one of: the priced Lines in the Scenario, the Left_Out_List, or the Not_In_Scenario_List (invariant).

### Requirement 9: Scenario comparison

**User Story:** As an owner or an agent, I want all scenarios side by side, so that I can see how cost and payback move when the change list changes.

#### Acceptance Criteria

1. WHEN a Scenario_Comparison is requested, THE Cost_Model SHALL return the Estimates for Base, With_Possible and Everything.
2. WHEN a Scenario_Comparison is requested with an owner's selection, THE Cost_Model SHALL also return the Estimate for Custom.
3. THE Scenario_Comparison SHALL report, for each Scenario other than Base that has a Scenario_Total, the difference from the Base Scenario_Total at each level.
4. WHEN a Scenario_Comparison is requested with Income_Inputs, THE Scenario_Comparison SHALL include the Payback_Result for each Scenario.

### Requirement 10: Monthly income as housing

**User Story:** As an owner, I want the monthly income as housing and the gain over what the space earns today, so that I can compare the two.

#### Acceptance Criteria

1. THE Payback_Calculator SHALL compute monthly net income as unit count × monthly rent per unit × occupancy × (1 − operating cost share).
2. THE Payback_Calculator SHALL compute monthly gain as monthly net income minus current monthly income.
3. THE Payback_Calculator SHALL compute the high end of monthly net income and monthly gain from each input at its Favourable_End, the low end from each input at its Unfavourable_End, and typical from each input at typical.
4. IF the unit count is missing or below 1, THEN THE Payback_Calculator SHALL report monthly net income, monthly gain, payback and gain over the horizon as empty with the reason "unit count not available".
5. IF the monthly rent per unit Range is missing or is not an Ordered_Range, THEN THE Payback_Calculator SHALL report monthly net income, monthly gain, payback and gain over the horizon as empty with the reason "rent per unit not available".
6. IF the occupancy, operating cost share or months to convert Global_Entry is not a Usable_Entry, THEN THE Payback_Calculator SHALL report the affected values as empty with a reason naming the entry.
7. IF the current monthly income is not given, THEN THE Payback_Calculator SHALL use 0 and label the value as the Team_Assumption "vacant: earns nothing today".

### Requirement 11: Payback and gain over the horizon

**User Story:** As an owner, I want payback as a range in years and the gain over the time the space stays available, so that I can judge the numbers myself.

#### Acceptance Criteria

1. WHEN monthly gain at a level is greater than 0, THE Payback_Calculator SHALL compute payback years at that level as (months to convert + (Scenario_Total + current monthly income × months to convert) / monthly gain) / 12.
2. IF monthly gain at a level is 0 or less, THEN THE Payback_Calculator SHALL report payback at that level as empty with the reason "monthly income as housing is no more than the space earns today at these inputs".
3. THE Payback_Calculator SHALL compute gain over the horizon at each level as monthly gain × max(0, horizon years × 12 − months to convert) − Scenario_Total − current monthly income × months to convert.
4. THE Payback_Calculator SHALL compute the shorter payback end and the higher gain over the horizon from each input at its Favourable_End, the longer payback end and the lower gain from each input at its Unfavourable_End, and typical from each input at typical.
5. FOR ALL Payback_Results, THE Payback_Calculator SHALL report the shorter end ≤ typical ≤ the longer end for every payback value present (invariant).
6. FOR ALL Payback_Results where payback at the Favourable_End is empty, THE Payback_Calculator SHALL report payback at typical and at the Unfavourable_End as empty.
7. FOR ALL Payback_Results, THE Payback_Calculator SHALL report gain over the horizon as an Ordered_Range (invariant).
8. THE Payback_Calculator SHALL accept horizon years as an input, with a default of 5 years labelled as a Team_Assumption.
9. IF horizon years is not a positive number, THEN THE Payback_Calculator SHALL report gain over the horizon as empty with the reason "horizon must be a positive number of years".
10. IF the Scenario_Total is empty, THEN THE Payback_Calculator SHALL report payback and gain over the horizon as empty with the reason "cost total not available".
11. THE Payback_Result SHALL include the Scenario_Total, monthly net income, monthly gain, payback in years and gain over the horizon, each as a Range, plus horizon years and the reason for every empty value.

### Requirement 12: Numbers only, no recommendation

**User Story:** As the team, I want the cost output to state numbers and ranges only, so that SecondStay never reads as telling the owner what to do.

#### Acceptance Criteria

1. THE Payback_Result SHALL hold numbers, Ranges, labels and reasons, with no recommendation field, no score and no overall result.
2. THE Cost_Model, Payback_Calculator, Sensitivity_Analyzer and Rent_Module SHALL produce results with no field named "verdict" and no text beginning with "Convert" or "Do not convert".
3. FOR ALL results of the Cost_Model, Payback_Calculator, Sensitivity_Analyzer and Rent_Module, every text value other than the Fixed_Notice SHALL contain no match of the Banned_Words.
4. THE Cost_Model, Payback_Calculator, Sensitivity_Analyzer and Rent_Module SHALL include the Fixed_Notice in every result.
5. THE Cost_Model, Payback_Calculator, Sensitivity_Analyzer and Rent_Module SHALL label each input value in a result with its source and confidence, or as a Team_Assumption.

### Requirement 13: What moves payback the most

**User Story:** As an owner or an agent, I want to know which three inputs move payback the most, so that I know which figure to firm up first.

#### Acceptance Criteria

1. WHEN sensitivity is requested for one Change_List, Price_Book, Income_Inputs and Scenario, THE Sensitivity_Analyzer SHALL compute payback years with each Sensitivity_Input at its low value and at its high value while every other input stays at typical.
2. THE Sensitivity_Analyzer SHALL use as Sensitivity_Inputs the price of each key with a priced Line in the Scenario (Fixed_Range and Rate_Range moved together), soft cost share, contingency, months to convert, monthly rent per unit, occupancy, operating cost share and current monthly income.
3. THE Sensitivity_Analyzer SHALL return the three Sensitivity_Inputs with the largest Swing, largest first, by default.
4. WHERE the caller gives a count, THE Sensitivity_Analyzer SHALL return that many Sensitivity_Inputs instead of three.
5. WHERE fewer Sensitivity_Inputs exist than the count asked for, THE Sensitivity_Analyzer SHALL return every Sensitivity_Input.
6. THE Sensitivity_Analyzer SHALL report for each returned Sensitivity_Input its name, low value, high value, payback at the low value, payback at the high value and Swing.
7. IF payback is empty at the low or high value of a Sensitivity_Input, THEN THE Sensitivity_Analyzer SHALL rank that Sensitivity_Input ahead of every Sensitivity_Input with a finite Swing and mark the empty end "no payback at this value".
8. WHEN two or more Sensitivity_Inputs have an empty payback end, THE Sensitivity_Analyzer SHALL order those Sensitivity_Inputs by the difference in gain over the horizon between their low and high values, largest first.
9. WHEN two Sensitivity_Inputs rank equally, THE Sensitivity_Analyzer SHALL order the two Sensitivity_Inputs by name.
10. IF payback at typical is empty, THEN THE Sensitivity_Analyzer SHALL return an empty ranking with the reason the Payback_Calculator gave.
11. FOR ALL rankings, THE Sensitivity_Analyzer SHALL report each Swing as 0 or more (invariant).
12. FOR ALL rankings of Sensitivity_Inputs with finite Swings, THE Sensitivity_Analyzer SHALL order the returned Sensitivity_Inputs so that each returned Swing is at least as large as every Swing after it and every Swing left out of the ranking (invariant).

### Requirement 14: Rent per unit from apartment comparables

**User Story:** As an owner, I want the rent per unit taken from nearby apartment asking rents, so that the income side rests on market data and says which comparables it used.

#### Acceptance Criteria

1. THE Rent_Module SHALL compute monthly rent per unit from apartment floor-plan asking rent records that the caller passes in.
2. WHERE the distance method is chosen, THE Rent_Module SHALL select as Comparables the floor plans of communities within a caller-given radius in miles of the space's latitude and longitude, measured as great-circle distance.
3. WHERE the submarket method is chosen, THE Rent_Module SHALL select as Comparables the floor plans of communities in the same submarket as the space.
4. WHERE a bedroom count is given, THE Rent_Module SHALL keep only Comparables with that bedroom count.
5. THE Rent_Module SHALL convert every asking rent to dollars per unit per month, following the definitions in the CoStar kit's `concepts/metrics-and-formulas.md` and `concepts/apartments.md`, before comparing rents.
6. IF a record's asking rent is zero, missing, or on a basis the Rent_Module cannot convert, THEN THE Rent_Module SHALL leave the record out and count it under its reason.
7. THE Rent_Module SHALL report the rent per unit Range as the 25th percentile, median and 75th percentile of the Comparable rents.
8. IF fewer Comparables are found than the caller-given minimum, with a default of 3, THEN THE Rent_Module SHALL report the rent per unit Range as empty with a reason giving the count found.
9. THE Rent_Module SHALL report the method used, the radius or submarket, the number of Comparables, the number of records left out by reason, and the label "asking rent, not achieved rent".
10. FOR ALL Comparable sets, THE Rent_Module SHALL report a rent per unit Range that is an Ordered_Range lying between the lowest and highest Comparable rent (invariant).
11. FOR ALL records and spaces, widening the radius SHALL keep every Comparable selected at the smaller radius (metamorphic property).
12. THE Rent_Module SHALL compute results from the records passed in as arguments, with no file or network reads.

### Requirement 15: What the space earns today

**User Story:** As an owner, I want the income I give up shown next to the housing income, so that payback counts what the space already earns.

#### Acceptance Criteria

1. WHERE the caller marks the space as vacant, THE Rent_Module SHALL report current monthly income as 0 with the label "vacant: earns nothing today".
2. WHERE the caller marks the space as leased, THE Rent_Module SHALL compute current monthly income as the office asking rent in dollars per square foot per year × the space area in square feet / 12.
3. THE Rent_Module SHALL convert each office asking rent on a monthly basis to a yearly basis by multiplying by 12 before use.
4. THE Rent_Module SHALL report the current monthly income Range with low from the lowest asking rent given and high from the highest asking rent given.
5. IF an office asking rent is 0, THEN THE Rent_Module SHALL treat the rent as not given.
6. IF no office asking rent is given for a leased space, THEN THE Rent_Module SHALL report current monthly income as empty with the reason "no asking rent on record".
7. IF the asking rents used have different service types, THEN THE Rent_Module SHALL list the service types and label the figure "mixed service types".
8. THE Rent_Module SHALL label current monthly income from asking rents "asking rent, not achieved rent".

### Requirement 16: How empty the building is

**User Story:** As an owner, I want indications of how much of the building is empty, so that I can see how much space a conversion could use.

#### Acceptance Criteria

1. THE Rent_Module SHALL compute marketed area as the sum of the largest square footage of each space on an active listing that has no date off market.
2. THE Rent_Module SHALL compute the share with no tenancy on record as (rentable area − area of current tenancies) / rentable area.
3. THE Rent_Module SHALL label marketed area "marketed is not vacant" and the share with no tenancy on record "no tenancy on record is not the same as vacant".
4. THE Rent_Module SHALL report the number of current tenancies that have no area on record.
5. IF the rentable area is missing or is 0 or less, THEN THE Rent_Module SHALL report the share with no tenancy on record as empty with the reason "rentable area not on record".
6. IF the area of current tenancies exceeds the rentable area, THEN THE Rent_Module SHALL report the share with no tenancy on record as 0 with the note "tenancies on record exceed rentable area".
7. FOR ALL records, THE Rent_Module SHALL report the share with no tenancy on record between 0 and 1 inclusive (invariant).

### Requirement 17: Results an agent or screen can use

**User Story:** As the integration teammate, I want plain JSON results, so that the screen and the agent can render and reason over them without importing cost-model classes.

#### Acceptance Criteria

1. THE Cost_Model, Payback_Calculator, Sensitivity_Analyzer and Rent_Module SHALL return results that convert to JSON values made only of objects, arrays, strings, finite numbers, booleans and null.
2. FOR ALL results, converting to JSON then parsing SHALL produce a value equal to the converted result (round-trip property).
3. THE Cost_Model SHALL accept Change objects built by `from_dicts` in `secondstay/changes.py`, including Changes with fields added later with defaults.

### Requirement 18: Sourced Los Angeles prices

**User Story:** As a judge or an owner, I want every price traced to a published source with its date and exclusions, so that I can trust the ranges.

#### Acceptance Criteria

1. THE Price_Book SHALL hold, for each Catalog key, either a Usable_Entry with a Los Angeles figure or a recorded reason for leaving the key unpriced.
2. THE Cost_Sources_Doc SHALL hold one section per Usable_Entry naming the key, the source, the publication date, the date accessed, what the figure excludes, and why the entry is split between fixed and rate the way it is.
3. WHERE a source figure includes work that another entry prices, such as a per-square-foot conversion cost that includes sprinklers or soft costs, THE Cost_Sources_Doc SHALL name the overlap and how it was removed from one of the entries.
4. WHERE a source figure is from a year before 2026 or from outside Los Angeles, THE Cost_Sources_Doc SHALL record the adjustment applied, labelled as a Team_Assumption.
5. THE Cost_Sources_Doc SHALL record the soft cost share, contingency and months to convert ranges with their sources.
6. THE Cost_Sources_Doc SHALL record the proposed default horizon and whether the team has agreed to it.
7. THE Cost_Sources_Doc SHALL record the chosen rent comparable method, distance or submarket, and the reason for the choice.
8. THE Cost_Sources_Doc SHALL carry the Fixed_Notice.
9. THE Cost_Sources_Doc SHALL hold an Open questions list for requests to files outside the Owned_Files.
10. THE Price_Book and the Cost_Sources_Doc SHALL contain no match of the Banned_Words in any text other than the Fixed_Notice.

### Requirement 19: Boundaries with the rest of the project

**User Story:** As a teammate, I want the cost model to stay inside its own files and data, so that A's rules work and the integration code keep working.

#### Acceptance Criteria

1. THE Cost_Model SHALL take every building fact from the Change_List or the Income_Inputs, with no import of `SpaceFacts` or `secondstay/checklist.py`.
2. THE Test_Suite SHALL use made-up buildings only, with no real CoStar record, address, property id, floor plan or Matterport model id.
3. THE sample Change_List in `tests/fixtures/sample_changes.json` SHALL keep five Changes that cover all three certainties, include at least one Change with no quantity, use Catalog keys with their Catalog units, and use requirement keys from the checklist.
4. WHEN the Test_Suite is run, THE Test_Suite SHALL report every test as succeeding, including the tests in `tests/test_changes.py` and `tests/test_checklist.py`.
5. THE Test_Suite SHALL check, using the sample Change_List, that the Base Scenario_Total leaves out the "possible" and "unknown" Changes, that an unknown key shows "not priced", that a None quantity shows "quantity unknown", and that an empty Price_Book produces no Scenario_Total.

## Open questions

These are requests or decisions outside B's files. The same list goes into `docs/cost-sources.md`.

1. **README wording (integration).** `README.md` says SecondStay "tells commercial property owners which of their vacant spaces can become housing", gives "a 0-100 feasibility score" and says "whether it pays back". These conflict with the wording rules (no score, no conclusion).
2. **Older scoring module (owner to confirm).** `secondstay/scoring.py` and `tests/test_scoring.py` return a `verdict` with "Strong candidate" and "Poor fit". Neither file is in B's list, so B leaves them alone.
3. **Unit count (integration and A).** The Payback_Calculator needs a unit count. Proposal: integration passes the count from the checklist "units" row. Which field carries it?
4. **Office asking rent (integration).** `secondstay/costar.py` already computes an area-weighted office asking rent per building. Integration decides whether to pass raw listing records to the Rent_Module or reuse that figure.
5. **Rendering (integration).** `secondstay/web.py` needs a view for the Scenario_Comparison, the Left_Out_List and the sensitivity ranking. B only supplies JSON results.
6. **Horizon (team).** B proposes 5 years as the default horizon. The team needs to agree.
7. **Comparables (team).** Rent comparables by distance or by submarket: B will compare both on made-up data and on the kit, then record the choice.
8. **Credible sources (team).** Which Los Angeles cost sources the judges are likely to accept.
9. **Kit definitions (B, during design).** The rent normalization rules in the kit's `concepts/metrics-and-formulas.md` and `concepts/apartments.md` were not available while writing these requirements. The design will name the exact fields and conversions.
10. **Repeated keys (A).** The Custom Scenario selects Changes by key. If one Change_List carries the same key twice, both Changes move together. A to confirm whether that can happen.
