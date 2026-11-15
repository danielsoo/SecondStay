"""Range arithmetic for income and simple payback, without a recommendation."""

import math

LEVELS = ("low", "typical", "high")
NOTICE = ("This is a preliminary evidence review, not a legal or code determination. "
          "Final decisions are made by LADBS and licensed professionals.")
NO_PAYBACK = "monthly income as housing is no more than the space earns today at these inputs"


def number(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def spread(low, typical=None, high=None):
    return dict(zip(LEVELS, (low, low if typical is None else typical, low if high is None else high)))


def range_issue(values, *, maximum=None, negative="negative price"):
    if not isinstance(values, dict) or any(values.get(k) is None for k in LEVELS):
        return "price not filled in"
    for key in LEVELS:
        if not number(values[key]):
            return f"{key} is not a finite number"
    if any(values[k] < 0 for k in LEVELS):
        return negative
    if maximum is not None and any(values[k] > maximum for k in LEVELS):
        return "share outside 0 to 1"
    if not values["low"] <= values["typical"] <= values["high"]:
        return "range out of order"
    return None


def entry_issue(entry, key):
    if not isinstance(entry, dict):
        return "price not filled in"
    if entry.get("unpriced_reason"):
        return entry["unpriced_reason"] if isinstance(entry["unpriced_reason"], str) else "unpriced reason must be text"
    if not isinstance(entry.get("source"), str) or not entry["source"].strip():
        return "no source recorded"
    if key == "months_to_convert":
        return range_issue(entry, negative="negative duration")
    if key in ("soft_cost_share", "contingency", "occupancy", "operating_cost_share"):
        return range_issue(entry, maximum=1, negative="share outside 0 to 1")
    for field in ("fixed", "rate"):
        issue = range_issue(entry.get(field))
        if issue:
            return f"{field}: {issue}"
    return None


def json_safe(value):
    """Keep invalid input diagnostics serializable with strict JSON encoders."""
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (int, float)) and not isinstance(value, bool) and not number(value):
        return None
    return value


def input_record(value, metadata=None, label="caller-supplied input"):
    metadata = metadata if isinstance(metadata, dict) else {}
    return json_safe({"value": value, "source": metadata.get("source") or f"Team assumption: {label}",
                      "confidence": metadata.get("confidence") or "estimated",
                      "notes": metadata.get("notes", "")})


def evaluate(cost, income, globals):
    """Omitted current income means vacant; explicit null means unavailable.

    Payback low is favorable; income and horizon gain low are adverse.
    """
    income = income or {}
    horizon, units = income.get("horizon_years", 5), income.get("units")
    rent, current = income.get("monthly_rent_per_unit"), income.get("current_monthly_income", spread(0))
    metadata = income.get("sources") or {}
    result = {"cost": cost, "monthly_net_income": None, "monthly_gain": None,
              "payback_years": None, "gain_over_horizon": None, "horizon_years": horizon,
              "reasons": {}, "inputs": {}, "notice": NOTICE}
    for key, value in (("units", units), ("monthly_rent_per_unit", rent),
                       ("current_monthly_income", current), ("horizon_years", horizon)):
        label = "vacant: earns nothing today" if key == "current_monthly_income" and key not in income else key
        if key == "horizon_years" and key not in income:
            label = "5-year horizon proposed; team agreement pending"
        result["inputs"][key] = input_record(value, metadata.get(key), label)
    for key in ("occupancy", "operating_cost_share", "months_to_convert"):
        entry = globals.get(key)
        result["inputs"][key] = input_record(entry, entry, key)
    reason = None
    if not number(units) or units < 1 or int(units) != units:
        reason = "unit count not available"
    elif range_issue(rent):
        reason = "rent per unit not available"
    for key in ("occupancy", "operating_cost_share"):
        if not reason and entry_issue(globals.get(key), key):
            reason = f"{key}: {entry_issue(globals.get(key), key)}"
    affected = ("monthly_net_income", "monthly_gain", "payback_years", "gain_over_horizon")
    if reason:
        result["reasons"] = {k: reason for k in affected}
        return json_safe(result)
    occupancy, operating = globals["occupancy"], globals["operating_cost_share"]
    net = {level: units * rent[level] * occupancy[level] * (1 - operating[opposite])
           for level, opposite in zip(LEVELS, reversed(LEVELS))}
    if not all(number(v) for v in net.values()):
        result["reasons"] = {k: "income exceeds numeric range" for k in affected}
        return json_safe(result)
    result["monthly_net_income"] = net
    if range_issue(current):
        result["reasons"] = {k: "current monthly income not available" for k in affected[1:]}
        return json_safe(result)
    result["monthly_gain"] = {k: net[k] - current[opposite] for k, opposite in zip(LEVELS, reversed(LEVELS))}
    duration_issue = entry_issue(globals.get("months_to_convert"), "months_to_convert")
    if range_issue(cost) or duration_issue:
        reason = "cost total not available" if range_issue(cost) else f"months_to_convert: {duration_issue}"
        result["reasons"].update(payback_years=reason, gain_over_horizon=reason)
        return json_safe(result)
    duration = globals["months_to_convert"]
    payback, gains, empty = {}, {}, {}
    for level, opposite in zip(LEVELS, reversed(LEVELS)):
        gain = result["monthly_gain"][opposite]
        lost = current[level] * duration[level]
        value = (duration[level] + (cost[level] + lost) / gain) / 12 if gain > 0 else None
        payback[level] = value if number(value) else None
        if payback[level] is None:
            empty[level] = NO_PAYBACK if gain <= 0 else "payback exceeds numeric range"
        if number(horizon) and horizon > 0:
            gains[opposite] = gain * max(0, horizon * 12 - duration[level]) - cost[level] - lost
    result["payback_years"] = payback
    if empty:
        result["reasons"]["payback_years"] = empty
    if gains and all(number(v) for v in gains.values()):
        result["gain_over_horizon"] = gains
    else:
        result["reasons"]["gain_over_horizon"] = ("gain exceeds numeric range" if gains else
                                                  "horizon must be a positive number of years")
    return json_safe(result)
