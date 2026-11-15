from secondstay import costing, finances, la_costs


def permit(n, value, **label):
    row = {"permit_nbr": f"P{n}", "issue_date": f"2025-01-{n % 28 + 1:02d}T00:00:00.000", "valuation": str(value),
           "dataset": "pi9x-tg5x", "work_desc": "private text"}
    lab = {"kind": "kitchen_bath", "kitchens": None, "bathrooms": None, "homes": None, "sqft": None,
           "structure": "unknown", "new_building": False, "revision": False, "scope": "kitchen remodel"}
    return row, {**lab, **label}


def book_from(pairs):
    rows = [r for r, _ in pairs]
    labels = {r["permit_nbr"]: lab for r, lab in pairs}
    return la_costs.build(rows, labels, "2026-11-09")


def test_per_kitchen_quartiles_leave_out_revisions_new_buildings_and_misreads():
    pairs = [permit(i, 10_000 * (i % 4 + 1), kitchens=1) for i in range(12)]
    pairs += [permit(100, 501, kitchens=1, revision=True), permit(101, 900_000, kitchens=1, new_building=True),
              permit(102, 10_000, kitchens=91)]  # $110 a kitchen: a misread count
    book = book_from(pairs)
    entry = book["prices"]["units.kitchen"]
    assert entry["permits"] == 12 and entry["rate"]["typical"] == 25_000.0
    assert entry["source"].startswith("https://data.lacity.org/") and entry["fixed"]["typical"] == 0
    assert all("private text" not in str(e) for e in entry["examples"])  # descriptions never leave data/raw


def test_too_few_permits_leave_the_key_out():
    book = book_from([permit(i, 8_000, bathrooms=1) for i in range(la_costs.MIN_PERMITS - 1)])
    assert "units.bathroom" not in book["prices"]


def test_conversions_are_a_benchmark_never_a_price():
    book = book_from([permit(i, 3_000_000, kind="office_to_residential", homes=30) for i in range(5)])
    assert "office_to_residential_per_home" in book["benchmarks"] and not book["prices"]


def test_la_prices_replace_the_book_entry_and_keep_the_earlier_source(monkeypatch):
    built = book_from([permit(i, 9_000, kitchens=1) for i in range(10)])
    monkeypatch.setattr(la_costs, "load", lambda: built)
    book = costing.price_book({"units.kitchen": {"unit": "each", "source": "https://example.org/old",
                                                 "fixed": {"low": 0, "typical": 0, "high": 0},
                                                 "rate": {"low": 1, "typical": 2, "high": 3}}})
    summary = finances.with_la_prices(book)
    entry = book.entries["units.kitchen"]
    assert entry["rate"]["typical"] == 9_000.0 and "example.org/old" in entry["notes"]
    assert summary["prices"]["units.kitchen"]["permits"] == 10 and "examples" not in entry
