"""Read every building's imagery and scans once, so the screen opens from cache.

``python -m secondstay.prefetch`` fills ``data/raw/`` (git-ignored) and prints
how much evidence each layer gave. Failed reads are not cached; run it again
to retry them.
"""

import datetime
from concurrent.futures import ThreadPoolExecutor

from . import costar, evidence, matterport, panoramas, permits, public_records, streets, vexcel, web
from .checklist import STATES, build_checklist, stairs_by_floor


def read_building(b: costar.Building) -> dict:
    outside = web.read_outside(b)
    scans = []
    for scan in b.scans:
        model, error = web.read_scan(scan.model_id)
        if model is None:
            scans.append({"model_id": scan.model_id, "error": error})
            continue
        facts = matterport.to_facts(model)
        scans.append({
            "model_id": scan.model_id,
            "area_sqft": sum(a for a in facts.floor_areas_sqft if a),
            "floors": len(facts.floor_areas_sqft),
            "labelled_rooms": sum(1 for r in facts.rooms if r.kind not in ("", "Void", "Other")),
            "stairs": sum(stairs_by_floor(facts).values()),
            "facts": facts,
        })
    return {"building": b, "outside": outside, "scans": scans}


def read_all_streets(buildings: list) -> None:
    """One OpenStreetMap request for every building not yet in the street cache."""
    import json

    todo = [
        b for b in buildings
        if b.latitude and b.longitude and not (web.STREET_CACHE / f"{b.property_id}.json").exists()
    ]
    if not todo:
        return
    try:
        found = streets.fetch_many([(b.latitude, b.longitude) for b in todo])
    except Exception as error:
        print(f"Streets not read: {error}")
        return
    web.STREET_CACHE.mkdir(parents=True, exist_ok=True)
    for b, roads in zip(todo, found):
        (web.STREET_CACHE / f"{b.property_id}.json").write_text(json.dumps(roads))


def best_rows(result: dict) -> tuple:
    """The checklist using the building's most informative scan: (scan, rows)."""
    b, outside = result["building"], result["outside"]
    readable = [s for s in result["scans"] if "facts" in s]
    best = max(readable, key=lambda s: matterport.scan_rank(s["facts"]), default=None)
    facts = costar.to_facts(b, best["facts"] if best else None)
    if best:
        facts.pano_reading = panoramas.reading(best["model_id"])
    facts.plan_reading = web.plan_reading(b)
    if outside.loaded:
        vexcel.to_facts(outside, facts)
    found = web.read_streets(b, outside)
    web.add_street_facts(facts, found, bool(found))
    rows = build_checklist(facts, datetime.date.today().year)
    summary, records, plans = evidence.load(b)
    return best, evidence.apply(rows, facts, summary, records, plans=plans)


def main() -> None:
    web.load_env()
    buildings = costar.load_buildings()
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(read_building, buildings))
    read_all_streets(buildings)
    for name, read in (("permits", permits.fetch_all), ("public records", public_records.fetch_all)):
        try:
            read(buildings)
        except Exception as error:  # a portal being down must not stop the rest
            print(f"{name.capitalize()} not read: {error}")

    scans = [s for r in results for s in r["scans"]]
    readable = [s for s in scans if "facts" in s]
    print(f"Buildings: {len(results)}")
    print(f"Imagery read: {sum(1 for r in results if r['outside'].loaded)}"
          f" · with height: {sum(1 for r in results if r['outside'].height_ft is not None)}")
    print(f"Scans: {len(scans)} · read: {len(readable)}"
          f" · with floor area: {sum(1 for s in readable if s['area_sqft'] > 0)}"
          f" · with room labels: {sum(1 for s in readable if s['labelled_rooms'])}"
          f" · with stairs labelled: {sum(1 for s in readable if s['stairs'])}")
    errors = sorted({r["outside"].error for r in results if r["outside"].error}
                    | {s["error"] for s in scans if "error" in s})
    for error in errors:
        print(f"  not read: {error}")

    print("\nEvidence found per building with its best scan (most first):")
    ranked = []
    for r in results:
        best, rows = best_rows(r)
        counts = {state: sum(1 for row in rows if row.state == state) for state in STATES}
        ranked.append((counts[STATES[0]], counts, best, r))
    ranked.sort(key=lambda item: -item[0])
    for found, counts, best, r in ranked[:15]:
        b = r["building"]
        scan = (f"scan {best['area_sqft']:,.0f} sq ft, {best['labelled_rooms']} labelled rooms, {best['stairs']} stairs"
                if best else "no scan read")
        print(f"  {b.property_id:>9}  {b.stories or '?':>2} st  " + " / ".join(str(n) for n in counts.values()) + f"  {scan}")
    print("  (columns: " + " / ".join(STATES) + ")")


if __name__ == "__main__":
    main()
