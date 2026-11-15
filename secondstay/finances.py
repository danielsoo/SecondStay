"""Connect the evidence screen to the cost model; edits last for one calculation."""

from copy import deepcopy
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from . import costar, costing, rents
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
    object_fields(options, ("scenario", "selected_keys", "income", "prices", "globals", "quantities"), "Request")
    scenario = options.get("scenario", "base")
    if not isinstance(scenario, str) or scenario not in costing.SCENARIOS:
        raise ValueError("Unknown scenario")
    changes = from_dicts(context["changes"])
    keys = {c.key for c in changes}
    selected = options.get("selected_keys", [c.key for c in changes if c.certainty == "called_for"])
    if not isinstance(selected, list) or any(not isinstance(k, str) or k not in keys for k in selected):
        raise ValueError("Select only changes in this space's change list")
    book = costing.load_prices(PRICE_PATH)
    rent = rent_seed(context["building"])
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
    return results
