"""Price the shared change list; no building facts or rule decisions live here."""

import json
import math
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from .economics import LEVELS, NOTICE, entry_issue, evaluate, input_record, json_safe, number, spread

GLOBALS = ("soft_cost_share", "contingency", "months_to_convert", "occupancy", "operating_cost_share")
SCENARIOS = ("base", "with_possible", "everything", "custom")


@dataclass
class PriceBook:
    entries: dict
    globals: dict
    notes: dict

    @property
    def issues(self):
        return {key: issue for key, entry in {**self.entries, **self.globals}.items()
                if (issue := entry_issue(entry, key))}


def price_book(data):
    if isinstance(data, PriceBook):
        return data
    return PriceBook({k: v for k, v in data.items() if not k.startswith("_") and k not in GLOBALS},
                     {k: v for k, v in data.items() if k in GLOBALS},
                     {k: v for k, v in data.items() if k.startswith("_")})


def load_prices(path="assumptions.json"):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("expected a JSON object")
        return price_book(data)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot read price book {path}: {exc}") from exc


def print_prices(prices):
    """Return editable JSON, preserving notes and unknown entry fields."""
    book = price_book(prices)
    return json.dumps({**book.notes, **book.entries, **book.globals}, indent=2, ensure_ascii=False) + "\n"


def estimate(changes, prices, income=None, scenario="base", *, selected_keys=()):
    """Return all lines, priced-subset totals and omissions; never invent missing prices."""
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {', '.join(SCENARIOS)}")
    book, changes, selected = price_book(prices), list(changes), set(selected_keys)
    result = {"scenario": scenario, "lines": [], "total": None, "subtotal": None,
              "soft_costs": None, "contingency": None, "total_reason": None,
              "left_out": [], "not_in_scenario": [], "unknown_selection": [],
              "inputs": {k: input_record(book.globals.get(k), book.globals.get(k), k) for k in GLOBALS},
              "notice": NOTICE}
    for change in changes:
        included = (scenario == "everything" or (scenario == "custom" and change.key in selected)
                    or (scenario in ("base", "with_possible") and change.certainty == "called_for")
                    or (scenario == "with_possible" and change.certainty == "possible"))
        raw_entry = book.entries.get(change.key)
        entry = raw_entry if isinstance(raw_entry, dict) else {}
        reason = ("no price for this change key" if change.key not in book.entries
                  else entry_issue(raw_entry, change.key))
        if entry and entry.get("unit") != change.unit:
            mismatch = f"unit mismatch: change {change.unit}, price {entry.get('unit')}"
            reason = f"{reason}; {mismatch}" if reason else mismatch
        quantity_reason = None
        if change.quantity is None:
            quantity_reason = f"quantity unknown: {change.quantity_basis}"
        elif not number(change.quantity) or change.quantity < 0:
            quantity_reason = "quantity is not a usable number"
        status = "not priced" if reason else "quantity unknown" if quantity_reason else "priced"
        reason = "; ".join(r for r in (reason, quantity_reason) if r) or None
        cost = None
        if status == "priced":
            cost = {k: entry["fixed"][k] + entry["rate"][k] * change.quantity for k in LEVELS}
            if not all(number(v) for v in cost.values()):
                cost, status, reason = None, "not priced", "line cost exceeds numeric range"
        line = {"key": change.key, "title": change.title, "requirement": change.requirement,
                "certainty": change.certainty, "scope": change.scope, "quantity": change.quantity,
                "unit": change.unit, "quantity_basis": change.quantity_basis,
                "fixed": entry.get("fixed"), "rate": entry.get("rate"), "cost": cost,
                "cost_with_allowances": None, "status": status, "reason": reason,
                "source": entry.get("source"), "confidence": entry.get("confidence"),
                "published": entry.get("published"), "accessed": entry.get("accessed"),
                "excludes": entry.get("excludes"), "notes": entry.get("notes"),
                "quantity_source": "Change.quantity_basis", "in_scenario": included}
        result["lines"].append(line)
        if not included:
            result["not_in_scenario"].append({"key": change.key, "title": change.title,
                                              "certainty": change.certainty, "reason": "not in this scenario"})
        elif status != "priced":
            result["left_out"].append({"key": change.key, "title": change.title,
                                       "status": status, "reason": reason})
    if scenario == "custom":
        result["unknown_selection"] = [{"key": key, "reason": "not in the change list"}
                                       for key in sorted(selected - {c.key for c in changes})]
    priced = [line for line in result["lines"] if line["in_scenario"] and line["status"] == "priced"]
    result["partial"] = bool(result["left_out"])
    issues = [f"{key}: {entry_issue(book.globals.get(key), key)}"
              for key in ("soft_cost_share", "contingency") if entry_issue(book.globals.get(key), key)]
    if not priced:
        result["total_reason"] = "no priced changes in this scenario"
    elif issues:
        result["total_reason"] = "; ".join(issues)
    else:
        try:
            subtotal = {k: math.fsum(line["cost"][k] for line in priced) for k in LEVELS}
            soft = {k: subtotal[k] * book.globals["soft_cost_share"][k] for k in LEVELS}
            contingency = {k: (subtotal[k] + soft[k]) * book.globals["contingency"][k] for k in LEVELS}
            total = {k: subtotal[k] + soft[k] + contingency[k] for k in LEVELS}
            if not all(number(v) for v in total.values()):
                raise OverflowError
            result.update(subtotal=subtotal, soft_costs=soft, contingency=contingency, total=total)
            for line in priced:
                line["cost_with_allowances"] = {k: line["cost"][k] * (1 + book.globals["soft_cost_share"][k])
                                                * (1 + book.globals["contingency"][k]) for k in LEVELS}
        except OverflowError:
            result["total_reason"] = "total exceeds numeric range"
    result["payback"] = evaluate(result["total"], income, book.globals) if income is not None else None
    return json_safe(result)


def compare_scenarios(changes, prices, income=None, *, selected_keys=None):
    changes = list(changes)
    names = SCENARIOS if selected_keys is not None else SCENARIOS[:3]
    estimates = {name: estimate(changes, prices, income, name, selected_keys=selected_keys or ()) for name in names}
    base = estimates["base"]["total"]
    for name, item in estimates.items():
        item["difference_from_base"] = ({k: item["total"][k] - base[k] for k in LEVELS}
                                        if name != "base" and base is not None and item["total"] is not None else None)
    return {"scenarios": estimates, "notice": NOTICE}


def sensitivity(changes, prices, income, scenario="base", *, selected_keys=(), count=3):
    """One input at a time; a change key moves its fixed and rate parts together."""
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("count must be a nonnegative integer")
    changes, selected_keys = list(changes), tuple(selected_keys)
    book = price_book(prices)
    baseline = estimate(changes, book, income, scenario, selected_keys=selected_keys)
    payback = baseline["payback"]
    result = {"ranking": [], "reason": None, "notice": NOTICE, "partial": baseline["partial"]}
    if not payback or payback["payback_years"] is None or payback["payback_years"]["typical"] is None:
        reason = payback["reasons"].get("payback_years") if payback else "income inputs not available"
        result["reason"] = reason.get("typical") if isinstance(reason, dict) else reason
        return result
    keys = sorted({line["key"] for line in baseline["lines"] if line["in_scenario"] and line["status"] == "priced"})
    inputs = [("price", key) for key in keys] + [("global", key) for key in GLOBALS]
    inputs += [("income", key) for key in ("monthly_rent_per_unit", "current_monthly_income")]
    ranking = []
    for kind, key in inputs:
        ends, values = [], []
        for level in ("low", "high"):
            altered_book, altered_income = deepcopy(book), deepcopy(income)
            if kind == "price":
                entry = altered_book.entries[key]
                value = {part: entry[part][level] for part in ("fixed", "rate")}
                for part in value:
                    entry[part] = spread(value[part])
            elif kind == "global":
                entry = altered_book.globals[key]
                value = entry[level]
                entry.update(spread(value))
            else:
                value = altered_income.get(key, spread(0))[level]
                altered_income[key] = spread(value)
            ends.append(estimate(changes, altered_book, altered_income, scenario, selected_keys=selected_keys)["payback"])
            values.append(value)
        low, high = (end["payback_years"]["typical"] for end in ends)
        swing = abs(high - low) if low is not None and high is not None else None
        gains = [end["gain_over_horizon"] for end in ends]
        gain_swing = abs(gains[1]["typical"] - gains[0]["typical"]) if all(g is not None for g in gains) else None
        source = book.entries.get(key) if kind == "price" else book.globals.get(key) if kind == "global" else (income.get("sources") or {}).get(key)
        ranking.append({"name": key, "low_value": values[0], "high_value": values[1],
                        "payback_at_low": low, "payback_at_high": high, "swing_years": swing,
                        "gain_swing": gain_swing, "low_reason": "no payback at this value" if low is None else None,
                        "high_reason": "no payback at this value" if high is None else None,
                        "input": input_record({"low": values[0], "high": values[1]}, source, key)})
    ranking.sort(key=lambda row: (row["swing_years"] is not None,
                                 -(row["swing_years"] if row["swing_years"] is not None else row["gain_swing"] or 0), row["name"]))
    result["ranking"] = ranking[:count]
    return json_safe(result)
