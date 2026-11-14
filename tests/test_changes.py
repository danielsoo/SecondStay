"""The change-list contract. The sample list is a made-up building."""

import re
from pathlib import Path

import pytest

from secondstay.changes import (
    CATALOG, CERTAINTIES, UNITS, Change, from_dicts, load_changes, to_dicts,
)
from secondstay.checklist import build_checklist, SpaceFacts

SAMPLE = Path(__file__).parent / "fixtures" / "sample_changes.json"
BANNED = re.compile(
    r"\b(legal|illegal|compliant|approved|eligible|pass|passes|fail|fails|verdict)\b"
    r"|can be converted|cannot be converted",
    re.I,
)


def test_sample_list_loads_and_round_trips():
    changes = load_changes(SAMPLE)
    assert len(changes) == 5
    assert {c.certainty for c in changes} == set(CERTAINTIES)
    assert any(c.quantity is None for c in changes)  # the cost model must cope with this
    assert from_dicts(to_dicts(changes)) == changes


def test_sample_list_uses_the_catalog_and_real_requirement_keys():
    rows = {r.key for r in build_checklist(SpaceFacts(), 2026)}
    for change in load_changes(SAMPLE):
        assert CATALOG[change.key] == change.unit
        assert change.requirement in rows


def test_catalog_units_are_known():
    assert set(CATALOG.values()) <= set(UNITS)


def test_unknown_fields_are_ignored_and_bad_values_refused():
    item = to_dicts(load_changes(SAMPLE))[0]
    assert from_dicts([{**item, "added_later": 1}])[0].key == item["key"]
    for field, value in (("certainty", "certain"), ("unit", "m2"), ("scope", "floor")):
        with pytest.raises(ValueError):
            Change(**{**item, field: value})


def test_sample_wording_follows_the_rules():
    for change in load_changes(SAMPLE):
        text = " ".join([change.title, change.reason, change.quantity_basis, change.confirmed_by])
        assert not BANNED.search(text), (change.key, BANNED.search(text).group(0))
