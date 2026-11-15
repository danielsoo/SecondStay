"""Pure CoStar rent and leasing calculations. Callers supply records, never paths."""

import math
from collections import Counter
from statistics import median

from .economics import NOTICE, input_record, json_safe, number, spread

ASKING = "asking rent, not achieved rent"
SOURCE = "CoStar kit: concepts/metrics-and-formulas.md; concepts/apartments.md; models/apartment-listing.md"


def _positive(value):
    return number(value) and value > 0


def _coordinates(address):
    lat, lon = address.get("latitude"), address.get("longitude")
    return number(lat) and number(lon) and -90 <= lat <= 90 and -180 <= lon <= 180


def _distance(a, b):
    lat1, lat2 = math.radians(a["latitude"]), math.radians(b["latitude"])
    dlon = math.radians(b["longitude"] - a["longitude"])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 3958.7613 * 2 * math.asin(math.sqrt(min(1, max(0, h))))


def _percentile(values, fraction):
    position = (len(values) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def apartment_rent(listings, space, *, method="distance", radius_miles=3,
                   bedrooms=None, min_comparables=3, properties=(), metering_type=None):
    """Use one midpoint per floor plan; percentiles are unweighted across plans.

    Per-bedroom rents multiply by bedrooms. Per-bed rents lack a reliable bed
    count and are excluded. Currency 0 is USD in this US-only kit, per its guide.
    """
    if method not in ("distance", "submarket"):
        raise ValueError("method must be distance or submarket")
    if not _positive(radius_miles) or not isinstance(min_comparables, int) or isinstance(min_comparables, bool) or min_comparables < 1:
        raise ValueError("radius_miles must be positive and min_comparables a positive integer")
    if bedrooms is not None and (not number(bedrooms) or bedrooms < 0 or int(bedrooms) != bedrooms):
        raise ValueError("bedrooms must be a nonnegative integer")
    if metering_type not in (None, 1, 2):
        raise ValueError("metering_type must be 1 or 2 when supplied")
    properties = {p["id"]: p for p in properties}
    target = space.get("primaryAddress") or space
    submarket = space.get("primarySubmarketId")
    result = {"monthly_rent_per_unit": None, "method": method,
              "radius_miles": radius_miles if method == "distance" else None,
              "submarket": submarket if method == "submarket" else None, "bedrooms": bedrooms,
              "count": 0, "comparables": [], "excluded": {}, "reason": None,
              "label": ASKING, "source": SOURCE, "confidence": "estimated", "notice": NOTICE,
              "metering_type": metering_type,
              "notes": ("Matched utility metering" if metering_type else
                        "Utility metering not matched; operating costs require a separate assumption"),
              "selection_assumption": "Team assumption: caller-selected radius, bedroom filter and minimum count"}
    if method == "distance" and not _coordinates(target):
        result["reason"] = "space coordinates not available"
        return json_safe(result)
    if method == "submarket" and not submarket:
        result["reason"] = "space submarket not available"
        return json_safe(result)
    excluded, rents = Counter(), []
    for listing_index, listing in enumerate(listings):
        prop = properties.get(listing.get("propertyId"), {})
        address = listing.get("address") or {}
        if not _coordinates(address):
            address = prop.get("primaryAddress") or {}
        distance, selection_reason = None, None
        if method == "distance":
            if not _coordinates(address):
                selection_reason = "coordinates not available"
            else:
                distance = _distance(target, address)
                if distance > radius_miles:
                    selection_reason = "outside radius"
        elif (listing.get("primarySubmarketId") or prop.get("primarySubmarketId")) != submarket:
            selection_reason = "different submarket"
        if metering_type and (prop.get("propertyApartment") or {}).get("apartmentMeteringType") != metering_type:
            selection_reason = "utility metering not matched"
        for plan_index, plan in enumerate(listing.get("apartmentModels") or []):
            reason = selection_reason
            if not reason and bedrooms is not None and plan.get("numBeds") != bedrooms:
                reason = "different bedroom count"
            currency = plan.get("monetaryUnit", listing.get("monetaryUnit"))
            basis = plan.get("rentPricingType")
            values = [plan[k] for k in ("minRent", "maxRent") if _positive(plan.get(k))]
            if not reason and currency not in (0, 1):
                reason = "currency not supported"
            if not reason and (basis not in (1, 3) or (basis == 3 and not _positive(plan.get("numBeds")))):
                reason = "rent basis not convertible to a unit"
            if not reason and not values:
                reason = "no asking rent on record"
            if not reason and len(values) == 2 and values[0] > values[1]:
                reason = "rent range out of order"
            if reason:
                excluded[reason] += 1
                continue
            rent = median(values) * (plan["numBeds"] if basis == 3 else 1)
            if not number(rent):
                excluded["rent exceeds numeric range"] += 1
                continue
            rents.append(rent)
            # Input positions identify comparables without exporting private property or plan IDs.
            result["comparables"].append({"listing_index": listing_index, "plan_index": plan_index,
                                           "monthly_rent": rent, "distance_miles": distance})
    result.update(count=len(rents), excluded=dict(sorted(excluded.items())))
    if len(rents) < min_comparables:
        result["reason"] = f"only {len(rents)} comparables; need {min_comparables}"
    else:
        rents.sort()
        result["monthly_rent_per_unit"] = spread(*(_percentile(rents, q) for q in (.25, .5, .75)))
    return json_safe(result)


def _spaces(listings):
    for listing in listings:
        if listing.get("listingStatus") != 1 or listing.get("dateOffMarket"):
            continue
        for space in (listing.get("forLeaseSummary") or {}).get("spaces") or []:
            if not space.get("dateOffMarket"):
                yield space


def office_income(listings, area_sqft, *, vacant):
    """Typical rent is weighted by marketed SF; low/high use quoted endpoints."""
    result = {"current_monthly_income": None, "reason": None, "label": ASKING,
              "service_types": [], "service_label": None, "source": SOURCE,
              "confidence": "estimated", "notes": "", "notice": NOTICE}
    if not isinstance(vacant, bool):
        result["reason"] = "vacancy assumption not available"
    elif vacant:
        result.update(current_monthly_income=spread(0), label="vacant: earns nothing today",
                      source="Team assumption: space is vacant")
    elif not _positive(area_sqft):
        result["reason"] = "space area not available"
    else:
        quotes, midpoints, weighted, weights, services = [], [], [], [], set()
        for space in _spaces(listings):
            if space.get("rateBasis") not in (1, 2):
                continue
            rates = [space[k] for k in ("rateLow", "rateHigh") if _positive(space.get(k))]
            if not rates or (len(rates) == 2 and rates[0] > rates[1]):
                continue
            yearly = [r * (12 if space["rateBasis"] == 1 else 1) for r in rates]
            if not all(number(r) for r in yearly):
                continue
            quotes.extend(yearly)
            midpoints.append(median(yearly))
            services.add(str(space.get("serviceType") or "unknown"))
            area = space.get("squareFeetMax") or space.get("squareFeetMin")
            if _positive(area):
                weighted.append(median(yearly) * area)
                weights.append(area)
        if not quotes:
            result["reason"] = "no asking rent on record"
        else:
            if len(weights) == len(midpoints):
                typical = sum(weighted) / sum(weights)
                result["notes"] = "Typical asking rent weighted by marketed square feet"
            else:
                typical = median(midpoints)
                result["notes"] = ("Team assumption: unweighted median of space quote midpoints; "
                                   "some listing areas are missing")
            values = spread(min(quotes) * area_sqft / 12, typical * area_sqft / 12, max(quotes) * area_sqft / 12)
            if all(number(v) for v in values.values()):
                result["current_monthly_income"] = values
            else:
                result["reason"] = "income exceeds numeric range"
        result["service_types"] = sorted(services)
        result["service_label"] = "mixed service types" if len(services) > 1 else next(iter(services), None)
    return json_safe(result)


def vacancy_indicators(listings, tenancies, rentable_sqft):
    """Caller supplies one building's records; marketed area is not vacancy."""
    marketed, occupied, missing = 0, 0, 0
    for space in _spaces(listings):
        areas = [space[k] for k in ("squareFeetMin", "squareFeetMax") if _positive(space.get(k))]
        marketed += max(areas, default=0)
    for tenancy in tenancies:
        if tenancy.get("toDate"):
            continue
        spaces = tenancy.get("spaces") or []
        areas = [s.get("squareFeetOccupied") for s in spaces]
        if not areas or any(not number(a) or a < 0 for a in areas):
            missing += 1
        occupied += sum(a for a in areas if number(a) and a >= 0)
    reason = "rentable area not on record" if not _positive(rentable_sqft) else None
    if not number(occupied) or not number(marketed):
        reason = "area exceeds numeric range"
    return json_safe({"marketed_area_sqft": marketed, "marketed_label": "marketed is not vacant",
                      "share_no_tenancy": None if reason else max(0, min(1, 1 - occupied / rentable_sqft)),
                      "tenancy_label": "no tenancy on record is not the same as vacant",
                      "tenancies_missing_area": missing, "occupied_area_sqft": occupied,
                      "reason": reason, "notes": "tenancies on record exceed rentable area"
                      if not reason and occupied > rentable_sqft else "", "source": SOURCE,
                      "confidence": "estimated", "notice": NOTICE})


def build_income(apartment_listings, space, *, units, vacant, office_listings=(),
                 tenancies=(), horizon_years=5, **comparable_options):
    """space supplies area_sqft/rentable_sqft, coordinates and primarySubmarketId."""
    office_listings = list(office_listings)
    rent = apartment_rent(apartment_listings, space, **comparable_options)
    current = office_income(office_listings, space.get("area_sqft"), vacant=vacant)
    return json_safe({"units": units, "monthly_rent_per_unit": rent["monthly_rent_per_unit"],
            "current_monthly_income": current["current_monthly_income"], "horizon_years": horizon_years,
            "sources": {"units": input_record(units, label="planned unit count"),
                        "monthly_rent_per_unit": rent, "current_monthly_income": current,
                        "horizon_years": input_record(horizon_years, label="horizon; 5-year proposal pending team agreement")},
            "rent": rent, "current_income": current,
            "vacancy": vacancy_indicators(office_listings, tenancies, space.get("rentable_sqft")),
            "notice": NOTICE})
