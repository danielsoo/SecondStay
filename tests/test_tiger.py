"""Tiger Data store: the parts that need no database."""

import os

import pytest

from secondstay import tiger


def test_local_files_hash_every_file_but_finder_litter(tmp_path):
    (tmp_path / "permits").mkdir()
    (tmp_path / "permits" / "1.json").write_text("[]")
    (tmp_path / ".DS_Store").write_text("x")
    files = tiger.local_files(tmp_path)
    assert list(files) == ["permits/1.json"]
    assert files["permits/1.json"] == tiger.sha256(b"[]")
    assert tiger.local_files(tmp_path / "missing") == {}


def test_push_sends_only_new_or_changed_files():
    local = {"a": "1", "b": "2", "c": "3"}
    assert tiger.plan_push(local, {"a": "1", "b": "old"}) == ["b", "c"]


def test_restore_writes_missing_files_and_keeps_local_edits_unless_forced():
    remote = {"a": "1", "b": "2", "c": "3"}
    local = {"a": "1", "b": "edited"}
    assert tiger.plan_restore(remote, local) == (["c"], ["b"])
    assert tiger.plan_restore(remote, local, force=True) == (["b", "c"], [])


def test_restore_refuses_paths_outside_data_raw(tmp_path):
    assert tiger.safe_target(tmp_path, "vexcel/1.json") == (tmp_path / "vexcel/1.json").resolve()
    with pytest.raises(ValueError):
        tiger.safe_target(tmp_path, "../.env")


def test_permit_rows_keep_dated_records_once_with_their_topics():
    records = [
        {"number": "1", "kind": "Building", "type": "Bldg-Alter/Repair", "issued": "2019-04-02",
         "work": "INSTALL FIRE SPRINKLERS ON 5TH FLOOR", "valuation": "12000"},
        {"number": "1", "kind": "Building", "issued": "2019-04-02", "work": "duplicate"},
        {"number": "2", "kind": "Electrical", "issued": "", "work": "no date"},
        {"number": "3", "kind": "Mechanical", "issued": "2021-01-05T00:00:00.000", "valuation": "n/a"},
    ]
    rows = tiger.permit_rows("101", records)
    assert [(r[2], r[3]) for r in rows] == [("1", "Building"), ("3", "Mechanical")]
    first = rows[0]
    assert first[0].year == 2019 and first[0].tzinfo is not None
    assert first[1] == 101
    assert first[8] == 12000.0
    assert "sprinklers" in first[9]
    assert rows[1][8] is None  # a valuation that is not a number is left empty, never guessed


def test_cost_rows_read_the_city_wide_search_cache():
    records = [
        {"permit_nbr": "26016-1", "issue_date": "2026-11-05T00:00:00.000", "valuation": "280000",
         "work_desc": " INTERIOR REMODEL ", "permit_sub_type": "Commercial"},
        {"permit_nbr": "26016-1", "issue_date": "2026-11-05T00:00:00.000"},
        {"permit_nbr": "", "issue_date": "2026-11-05"},
    ]
    rows = tiger.cost_rows("interior", records)
    assert len(rows) == 1
    assert rows[0][1:] == ("interior", "26016-1", "Commercial", "INTERIOR REMODEL", 280000.0)


def test_missing_connection_is_reported_not_guessed(monkeypatch, tmp_path):
    monkeypatch.delenv(tiger.ENV_KEY, raising=False)
    monkeypatch.setattr(tiger, "REPO_ROOT", tmp_path)
    with pytest.raises(tiger.NotConfigured):
        tiger.database_url()
    (tmp_path / ".env").write_text(f"{tiger.ENV_KEY}='postgres://u@h/db'\n")
    assert tiger.database_url() == "postgres://u@h/db"


@pytest.mark.skipif(not os.getenv("TIGER_TEST_DATABASE"), reason="set TIGER_TEST_DATABASE=1 to run against the real service")
def test_round_trip_against_the_service(tmp_path):
    (tmp_path / "probe").mkdir()
    (tmp_path / "probe" / "round_trip.txt").write_bytes(b"secondstay")
    tiger.push(tmp_path)
    (tmp_path / "probe" / "round_trip.txt").unlink()
    assert tiger.restore(tmp_path)["written"] >= 1
    assert (tmp_path / "probe" / "round_trip.txt").read_bytes() == b"secondstay"
    with tiger.connect(autocommit=True) as conn:  # the probe must not be restored into data/raw later
        conn.execute("DELETE FROM raw_files WHERE path = 'probe/round_trip.txt'")
