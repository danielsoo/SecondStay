# CoStar kit: where the fields are and how the layers link

Notes from reading `costar-hackathon-kit` (index, models, schemas, concepts) and profiling the Los Angeles records.
Counts only; no record, address or model id from the kit belongs in this repo.

## Scope we use

- Los Angeles is `primaryAddress.researchMarketId == 20`. Of 1,581 LA properties, 1,417 are apartments.
- Non-residential LA properties: 98 office, 24 industrial, 24 retail, 10 flex, 8 other.
- Office is `propertyType == 5`. Standing buildings are `constructionStatus == 1` (97 of 98). 89 of those have a scan.

## Fields for the checklist (all on `data/commercial-property.jsonl`)

| Need | Field | Filled on LA offices | Notes |
| --- | --- | --- | --- |
| Year built | `constructionEvents[]` with `eventType == 2` (ConstructionComplete) | 98 of 98 | Not `eventType 1` (GroundBreaking, 8 of 98). Types 3 to 5 are renovations |
| Zone | `zoningDescription` | 98 of 98 | Free text: "C2", "LAC2", "C2-1VL-O, Los Angeles", "[Q] M1-2D-SN". `costar.base_zone` reduces it to a zone class; 4 values do not match one |
| Stories | `numStoriesAboveGrade` | 98 of 98 | Range 1 to 44; 35 buildings are 4 stories or fewer |
| Height | `buildingHeightInFeet` | 6 of 98 | Mostly empty, so height still has to come from imagery |
| Sprinklers | `hasSprinklers`, `sprinklerType` | 68 of 98 (63 yes, 5 no) | Presence only, not coverage. The PRD listed this as not in our data |
| Elevators | `propertyOffice.structural.elevators[]` | when recorded | Count by type (1 = passenger). No cab size |
| Floor size | `grossTypicalFloorSquareFeet`, `floors[].floorSize` | 98 of 98 | |
| Rentable area | `rentableBuildingAreaSquareFeet` | 98 of 98 | Vacancy denominator |
| Slab to slab | `propertyOffice.structural.slabToSlabHeightFeet` | some | Useful later for ceiling height |

## Vacancy and rent

There is no vacancy field for offices (`vacancyPercent` exists only for apartments). Two indications:

- **Marketed space**: `commercial-listing-summary.jsonl`, `forLeaseSummary.spaces[]` on listings with `listingStatus == 1`,
  dropping spaces with a `dateOffMarket`. Each space has `suite`, `floorName`, `squareFeetMax`, `spaceUse`, `rateHigh`/`rateLow`
  and `rateBasis` (1 monthly, 2 yearly). 75 of the 89 offices have marketed space; 45 have an asking rent. A rate of 0 means none given.
  Available is not vacant: a marketed space can still be occupied. Rents mix service types.
- **Tenancies**: `location-occupancy.jsonl` where `toDate` is null, summing `spaces[].squareFeetOccupied`.
  Rentable area minus that is space with no tenancy on record. Median office is about 59% accounted for. Some tenancies have no area.

Achieved rents are on `location-occupancy` `leaseDeal.rateActual` when a lease comp exists.

## Keys that link the layers

| From | To | Key |
| --- | --- | --- |
| CoStar building | Matterport scan | `commercial-properties.csv` `PropertyId` + `MatterportModelId`; the same id is `attachments[].videoKey` where `videoExternalReferenceType` is 36 or 234. `caption` often names the suite or tenant |
| Matterport scan | CoStar building | The reverse lookup of the above. One scan can belong to two neighbouring properties |
| CoStar building | Vexcel location | `primaryAddress.latitude` / `longitude` (98 of 98). `parcelNumbers` (APN) is there for ZIMAS and assessor lookups |
| Listing, tenancy, sale | CoStar building | `propertyId`; sale comps use `entities[].propertyId` |

A scan is of a suite or floor, not the building. 255 scans cover 90 LA offices, so the screen lets the owner pick the scan.
Linking a scan to one marketed suite has no key; the attachment caption is the only hint.

## Tools folder

`tools/expand_records.py` only writes each record to its own JSON file for browsing. There is no SDK or MCP server in the kit.
The index says Matterport connection details come in a separate zip.

## Vexcel (`secondstay/vexcel.py`)

API 2.0, reference at `https://api.vexcelgroup.com/v2/api-docs`. The key goes in the `X-API-KEY` header.

| Need | Call | Notes |
| --- | --- | --- |
| Footprints of the building and its neighbours | `/structure/extract` with a box around the CoStar point | GeoJSON; `footprint.wkt` per structure. Roof height fields exist but came back empty for the LA offices we tried |
| Height | `/dsm/elevation` (roof surface) minus `/dtm/elevation` (ground), metres | Sampled on a 6 by 6 grid over the footprint and the highest point kept, because footprints often include a low podium. Includes rooftop equipment |
| Distance to neighbours | measured between footprint outlines | A podium, deck or attached structure can be a separate footprint, so the closest one is not always another building |
| Image | `/ortho/extract` with the same box, `zoom=19` | Shown with the footprints drawn over it |

One building costs about 40 calls the first time and is then cached under `data/raw/vexcel/`.
Street frontage and fire access are not derived yet; `/oriented/*` has the oblique views that would help.

## PRD open questions

- Zoning, year built and stories: yes, on every LA office. Vacancy by suite: not directly; marketed suites and current tenancies only.
- Vexcel: height and neighbouring footprints work as above. On six offices tried, imagery height fits the stories on record (10 to 21 ft per story).
- CoStar also carries building and aerial photos (`attachments[]`, `attachmentType` 1 = aerial), shown under the Vexcel image.
