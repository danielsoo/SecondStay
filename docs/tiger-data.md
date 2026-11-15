# Tiger Data store

`data/raw/` holds licensed and private material (CoStar records, Matterport scans, Vexcel imagery, hand-traced interior models, model readings). It is git-ignored and never enters the public repository. A Tiger Data service (TimescaleDB on PostgreSQL) keeps it, so a fresh checkout can be restored, and it serves the permit history as time series.

Set `TIGER_DATABASE_URL` in `.env` to the service URL, install the `db` extra (`pip install -e '.[db]'`), then:

| Command | What it does |
| --- | --- |
| `python -m secondstay.tiger push` | Uploads new or changed files under `data/raw/` (one row per file: path, sha256, bytes). |
| `python -m secondstay.tiger restore` | Writes stored files that are missing locally. A local file that differs is kept unless `--force` is given. Paths outside `data/raw/` are refused. |
| `python -m secondstay.tiger permits` | Reloads the permit hypertables from the cached files, compresses them and refreshes the yearly continuous aggregates. |
| `python -m secondstay.tiger runs` | Stores the finished evidence-agent runs saved under `data/raw/agent_runs/`. New live runs are stored automatically when they finish. |
| `python -m secondstay.tiger status` | Local against stored files, row counts, and compression per hypertable. |

## Time series

- `building_permits`: every LADBS permit matched to a building by parcel number (about 30,000 rows), segmented by `property_id`, with the requirement topics each permit names.
- `city_cost_permits`: the city-wide permit searches behind the cost estimate (about 9,000 rows), segmented by search.
- Both are hypertables partitioned on the issue date and stored in compressed columnar form (about 70 to 75% smaller on the first load).
- `building_permits_yearly` and `city_cost_permits_yearly` are continuous aggregates of permits and declared valuation per year. The evidence view for sprinklers, fire alarm, elevators and exits reads the first one through `/api/spaces/<id>/permit-years.json` and draws all permits on the parcel by year.

## Evidence checks

`agent_runs` holds each finished live run of the evidence agent: building, space, scan, status, start time and the whole run as JSON. The building page lists them through `/api/spaces/<id>/reviews` (merged with any files under `data/raw/agent_runs/`) and opens on the latest completed check, so the model only runs when someone chooses **Run again**. Test runs are never stored, and the test suite cannot reach the service unless `TIGER_TEST_DATABASE=1` is set.

Declared valuation is what the applicant wrote on the permit, not what the work cost; many permits carry none. Permits record work that was filed, not what is installed today. Without `TIGER_DATABASE_URL` the route answers 503 and the screen leaves the chart out; every other view reads `data/raw/` as before.
