"""Connect the evidence screen to the cost model; edits last for one calculation."""

from copy import deepcopy
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from . import costar, cost_reading, costing, income_research, la_costs, rents
from .changes import from_dicts
from .economics import LEVELS, entry_issue, number, range_issue, spread

PRICE_PATH = Path(__file__).resolve().parent.parent / "assumptions.json"
TEAM = {"source": "Team assumption: edited in the cost screen", "confidence": "estimated",
        "notes": "Session-only input; confirm scope and obtain a quote before budgeting."}


@lru_cache(maxsize=1)
def apartment_listings(path, modified):
    return tuple(costar._jsonl(path))


def rent_seed(building):
    path = costar.kit_dir() / "data" / "apartment-listing.jsonl"
    try:
        listings = apartment_listings(path, path.stat().st_mtime_ns)
    except (OSError, ValueError):
        listings = ()
    result = rents.apartment_rent(listings, building, bedrooms=0, radius_miles=3)
    if not listings:
        result["reason"] = "Apartment listing data unavailable; enter a rent assumption."
    # The browser needs the method and count, not private comparable records.
    result.pop("comparables", None)
    return result


def object_fields(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(f"{label}: expected an object with fields {', '.join(allowed)}")


def checked_range(value, label, *, nullable=False, maximum=None):
    if value is None and nullable:
        return
    object_fields(value, LEVELS, label)
    issue = range_issue(value, maximum=maximum)
    if issue:
        raise ValueError(f"{label}: {issue}")


def calculate(context, options):
    object_fields(options, ("scenario", "selected_keys", "income", "prices", "globals", "quantities", "read_photos",
                            "read_income"), "Request")
    scenario = options.get("scenario", "base")
    if not isinstance(scenario, str) or scenario not in costing.SCENARIOS:
        raise ValueError("Unknown scenario")
    changes = from_dicts(context["changes"])
    photos = photo_reading(context, options.get("read_photos") is True)
    if photos.get("read"):
        changes, photos["considered"] = cost_reading.apply(changes, photos.pop("reading"))
    keys = {c.key for c in changes}
    selected = options.get("selected_keys", [c.key for c in changes if c.certainty == "called_for"])
    if not isinstance(selected, list) or any(not isinstance(k, str) or k not in keys for k in selected):
        raise ValueError("Select only changes in this space's change list")
    book = costing.load_prices(PRICE_PATH)
    la_book = with_la_prices(book)
    research = income_research.reading(context["building"], (context.get("outside") or {}).get("height_ft"),
                                       options.get("read_income") is True)
    researched = research.get("read") and (research.get("rent") or {}).get("monthly_rent_per_unit")
    rent = dict(research["rent"]) if researched else rent_seed(context["building"])
    kitchen = next((c for c in changes if c.key == "units.kitchen"), None)
    income = {"units": kitchen.quantity if kitchen else None,
              "monthly_rent_per_unit": rent["monthly_rent_per_unit"], "current_monthly_income": spread(0),
              "horizon_years": 5, "sources": {
                  "units": {"source": "Team assumption: " + (kitchen.quantity_basis if kitchen else "unit count unknown")},
                  "monthly_rent_per_unit": rent,
                  "current_monthly_income": {"source": "Owner's assumption: the office is unused, so it earns $0 today. "
                                                       "Enter today's net income if it is leased."},
                  "horizon_years": {"source": "Team assumption: 5-year comparison horizon"}}}
    defaults = {"income": deepcopy(income), "prices": deepcopy({k: book.entries.get(k, {}) for k in keys}),
                "globals": deepcopy(book.globals)}
    overrides = options.get("income", {})
    object_fields(overrides, ("units", "monthly_rent_per_unit", "current_monthly_income", "horizon_years"), "Income")
    for key, value in overrides.items():
        if key in ("units", "horizon_years"):
            if value is not None or key == "horizon_years":
                if not number(value) or value <= 0 or (key == "units" and int(value) != value):
                    raise ValueError(f"{key}: enter a positive {'whole number' if key == 'units' else 'number'}")
        else:
            checked_range(value, key, nullable=True)
        if value != income[key]:
            income[key] = value
            income["sources"][key] = TEAM.copy()
    quantities = options.get("quantities", {})
    object_fields(quantities, keys, "Quantities")
    for key, value in quantities.items():
        if value is not None and (not number(value) or value < 0):
            raise ValueError(f"{key}: quantity must be nonnegative or empty")
    changes = [replace(c, quantity=quantities[c.key], quantity_basis=TEAM["source"])
               if c.key in quantities and quantities[c.key] != c.quantity else c for c in changes]
    for group, allowed, entries in (("prices", keys, book.entries), ("globals", costing.GLOBALS, book.globals)):
        edits = options.get(group, {})
        object_fields(edits, allowed, group)
        for key, value in edits.items():
            parts = ("fixed", "rate") if group == "prices" else LEVELS
            object_fields(value, parts, key)
            if set(value) != set(parts):
                raise ValueError(f"{key}: fill in all {', '.join(parts)} values")
            original = {part: entries.get(key, {}).get(part) for part in parts}
            if value == original:
                continue
            entry = {**entries.get(key, {}), **value, **TEAM, "published": "", "accessed": ""}
            if group == "prices" and entry.get("unpriced_reason"):
                entry["excludes"] = "Scope and exclusions for this edited price need confirmation."
            entry.pop("unpriced_reason", None)
            issue = entry_issue(entry, key)
            if issue:
                raise ValueError(f"{key}: {issue}")
            entries[key] = entry
    results = costing.compare_scenarios(changes, book, income, selected_keys=selected)
    results.update(defaults=defaults, income=income, rent=rent, scenario=scenario,
                   sensitivity=costing.sensitivity(changes, book, income, scenario, selected_keys=selected))
    results["scope"] = ((kitchen.scope + ": " + kitchen.quantity_basis) if kitchen else "Residential unit count unknown")
    results["photos"] = photos
    results["income_research"] = research
    results["minimum"] = minimum(results["scenarios"]["base"], income.get("units"), results["scenarios"].get("with_possible"))
    results["la_prices"] = la_book
    return results


def with_la_prices(book):
    """Use the Los Angeles permit price book where it has a price; keep the earlier entry's source in its notes."""
    la = la_costs.load()
    if not la:
        return None
    for key, entry in la["prices"].items():
        earlier = book.entries.get(key) or {}
        notes = entry["notes"]
        if earlier.get("source"):
            notes += f" Earlier team price, kept for comparison: {earlier['source']}."
        book.entries[key] = {k: v for k, v in entry.items() if k not in ("examples", "permits", "period")} | {"notes": notes}
    return {"built": la["built"], "permits_read": la["permits_read"], "permits_kept": la["permits_kept"],
            "prices": la["prices"], "benchmarks": la["benchmarks"], "published": la.get("published", [])}


# Work measured over the converted area is shared between its homes; everything else is building-wide.
PER_HOME_KEYS = ("sprinklers.verify_coverage",)


def per_home_line(line):
    return line["key"].startswith("units.") or line["key"] in PER_HOME_KEYS


def one_home(base, homes, wider=None):
    """The least to open a single home. Converting even one home brings the whole building under the rules, so this is
    the building-wide called-for work in full plus one home's average share of the per-home work (fit-out, kitchen,
    bathroom). Soft costs and contingency are included through each line's cost with allowances."""
    lines = base["lines"]
    called = [l for l in lines if l["certainty"] == "called_for"]
    priced = [l for l in called if l["status"] == "priced" and l.get("cost_with_allowances")]
    per_home_lines = [l for l in priced if per_home_line(l)]
    building_lines = [l for l in priced if not per_home_line(l)]
    if not homes or not per_home_lines:
        return None
    building = {k: sum(l["cost_with_allowances"][k] for l in building_lines) for k in ("low", "typical")}
    per_home = {k: sum(l["cost_with_allowances"][k] for l in per_home_lines) / homes for k in ("low", "typical")}
    # Work the evidence leaves open (e.g. systems on record whose coverage needs confirming): priced from the scenario
    # that includes possible work, and reported as an amount that may be added, never inside the minimum. Building-wide
    # items count in full; items measured over the converted area count as one home's share.
    wider_lines = (wider or {}).get("lines") or []
    possible = [l for l in wider_lines if l["certainty"] == "possible"]
    possible_priced = [l for l in possible if l["status"] == "priced" and l.get("cost_with_allowances")]
    share = lambda l, k: l["cost_with_allowances"][k] / (homes if per_home_line(l) else 1)
    if_needed = {k: sum(share(l, k) for l in possible_priced) for k in ("low", "typical")}
    return {"homes": homes, "building": building, "per_home": per_home,
            "total": {k: building[k] + per_home[k] for k in ("low", "typical")},
            "building_priced": [l["title"] for l in building_lines],
            "per_home_items": [l["title"] for l in per_home_lines],
            "building_to_quote": [l["title"] for l in called if l["status"] != "priced" and not per_home_line(l)],
            "building_possible": [l["title"] for l in lines if l["certainty"] == "possible" and l["scope"] == "building"],
            "building_if_needed": if_needed if possible_priced else None,
            "building_if_needed_items": [{"title": l["title"], "low": share(l, "low"), "per_home": per_home_line(l)}
                                         for l in possible_priced],
            "building_possible_unpriced": [l["title"] for l in possible if l not in possible_priced
                                           and not per_home_line(l)]}


def minimum(base, homes=None, wider=None):
    """The least the published rules call for: called-for work only, at the low end of each price."""
    called = [line for line in base["lines"] if line["certainty"] == "called_for"]
    priced = [line for line in called if line["status"] == "priced"]
    total = base.get("total") or {}
    return {"low": total.get("low"), "typical": total.get("typical"), "one_home": one_home(base, homes, wider),
            "included": [{"key": l["key"], "title": l["title"], "quantity": l["quantity"], "unit": l["unit"],
                          "low": l["cost"]["low"], "typical": l["cost"]["typical"], "basis": l["quantity_basis"],
                          "source": l["source"], "rate": l["rate"]} for l in priced],
            "to_quote": [{"title": l["title"], "quantity": l["quantity"], "unit": l["unit"], "reason": l["reason"],
                          "basis": l["quantity_basis"]} for l in called if l["status"] != "priced"],
            "possible": sum(1 for l in base["lines"] if l["certainty"] == "possible"),
            "unknown": sum(1 for l in base["lines"] if l["certainty"] == "unknown")}


NO_TOUR = ("No Matterport 3D tour is on record for this space. That says nothing about whether the space could become "
           "housing; it only means the items read from tour photos (sprinkler heads, alarm devices, exit signs, existing "
           "water lines, windows) cannot be measured here, so their effect on the cost cannot be estimated.")


def photo_check_blocked():
    """Why this server cannot run the AI photo check, or "" when it can."""
    import importlib.util
    import os

    from . import agent
    if os.getenv("SECONDSTAY_OFFLINE"):
        return "The AI photo check is off in this public demo; it runs where a vision model is configured."
    try:
        agent.model_settings(vision=True)
    except agent.ConfigurationError:
        return "The AI photo check needs a vision model: set SECONDSTAY_VISION_MODEL and its API key."
    if importlib.util.find_spec("langchain_core") is None:
        return "The AI photo check needs the agent dependencies: pip install -e \".[agent]\"."
    return ""


def photo_reading(context, read_now=False):
    """The scan's requirement-related photo reading; sent to a model only when asked."""
    scan = (context.get("scan") or {}).get("model_id") or ""
    if not scan:
        return {"available": False, "read": False,
                "reason": NO_TOUR}
    reading = cost_reading.cached(scan)
    if reading is None:
        blocked = photo_check_blocked()
        if blocked:  # say so up front instead of offering a button that cannot finish
            return {"available": True, "read": False, "can_read": False, "reason": blocked}
    if reading is None and read_now:
        try:
            reading = cost_reading.read(scan)
        except (ValueError, LookupError) as error:  # missing model settings, no panoramas, or an unusable answer
            return {"available": True, "read": False, "reason": str(error)}
        except Exception as error:  # provider or network failure; never echo details that may hold credentials
            return {"available": True, "read": False, "reason": f"The photos could not be read ({type(error).__name__})."}
    if reading is None:
        return {"available": True, "read": False, "reason": "Not read yet."}
    return {"available": True, "read": True, "reading": reading, "method": reading.get("method"),
            "model": reading.get("model"), "notes": reading.get("notes", ""), "read_at": reading.get("read_at")}
