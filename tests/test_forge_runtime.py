"""Tests for the DataForge model + store + runtime orchestration.

Uses a fake fetcher and a temp HOME so it needs no live DB2/SQL Server and runs
on the minipc. Exercises: model round-trip, editable-copy Source creation,
Re-sync, Refresh (writes a real parquet Snapshot), staleness, and running a
saved 2-Source Forge end-to-end over Snapshots.
"""
import os
import sys
import tempfile

import pandas as pd

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from suiteview.audit import query_object_store  # noqa: E402
from suiteview.audit.query_object import (  # noqa: E402
    QueryObject, manual_sql_query_object,
)
from suiteview.audit.dataforge import dataforge_store, forge_runtime  # noqa: E402
from suiteview.audit.dataforge.dataforge_model import (  # noqa: E402
    DataForge, DataForgeSource, SourceSnapshot,
)


def test_model_round_trip():
    src = DataForgeSource(
        query_name="Policies", alias="pol",
        definition={"name": "Policies", "kind": "manual_sql"},
        filters=[{"column": "status", "mode": "equals", "value": "INFORCE"}],
        snapshot=SourceSnapshot(created_at="2026-06-06T10:00:00",
                                row_count=5, columns=["a", "b"], stale=True),
        synced_at="2026-06-06T09:00:00",
    )
    forge = DataForge(name="MyForge", sources=[src],
                      config={"joins": [], "limit": 100})
    restored = DataForge.from_dict(forge.to_dict())
    assert restored.name == "MyForge"
    assert len(restored.sources) == 1
    rs = restored.sources[0]
    assert rs.query_name == "Policies" and rs.alias == "pol"
    assert rs.filters[0]["value"] == "INFORCE"
    assert rs.snapshot.row_count == 5 and rs.snapshot.stale is True
    assert restored.config["limit"] == 100
    print("  model round-trip  OK")


def test_legacy_source_round_trip():
    # Old saved forges had only query_name + alias; must still load.
    legacy = {"query_name": "Old", "alias": "o"}
    s = DataForgeSource.from_dict(legacy)
    assert s.query_name == "Old" and s.alias == "o"
    assert s.definition == {} and s.filters == []
    assert s.snapshot.exists is False
    print("  legacy source round-trip  OK")


def _make_shared_query(name: str, sql: str = "",
                       cols: list[str] | None = None) -> QueryObject:
    obj = manual_sql_query_object(
        name=name, sql=sql or f"SELECT * FROM {name}", dsn="FAKE_DSN",
        result_columns=cols or ["company_code", "policy_number"])
    query_object_store.save_object(obj)
    return obj


def test_add_resync_refresh_and_run(tmp_home):
    # Two shared Queries in the store.
    _make_shared_query("Policies")
    _make_shared_query("Reins")

    forge = DataForge(name="ReinForge")
    pol = forge_runtime.add_query_as_source(forge, "Policies", alias="pol")
    forge_runtime.add_query_as_source(forge, "Reins", alias="re")
    assert pol.definition["name"] == "Policies"
    assert pol.snapshot.exists is False  # not pulled yet
    assert len(forge.sources) == 2

    # Fake fetcher keyed on the (editable) definition's SQL.
    data = {
        "SELECT * FROM Policies": pd.DataFrame({
            "company_code": ["A", "A", "B"],
            "policy_number": ["100", "101", "200"],
            "face_amount": [50000, 75000, 120000],
        }),
        "SELECT * FROM Reins": pd.DataFrame({
            "company_code": ["A", "B", "B"],
            "policy_number": ["100", "200", "999"],
            "reinsurer": ["XYZ", "XYZ", "ACME"],
        }),
    }

    def fake_fetch(obj: QueryObject) -> pd.DataFrame:
        return data[obj.sql]

    # Refresh both Sources -> writes real parquet Snapshots under the temp HOME.
    for s in forge.sources:
        snap = forge_runtime.refresh_source("ReinForge", s, fetch_fn=fake_fetch)
        assert snap.exists and snap.stale is False
        assert dataforge_store.has_source_snapshot("ReinForge",
                                                   s.effective_alias())
    assert forge.source_by_alias("pol").snapshot.row_count == 3
    assert forge.source_by_alias("re").snapshot.row_count == 3

    # Configure a 2-Source inner join (multi-key) + a Source filter on re.
    forge.config["joins"] = [{
        "left_source": "pol", "right_source": "re",
        "left_keys": ["company_code", "policy_number"],
        "right_keys": ["company_code", "policy_number"],
        "how": "inner",
    }]
    forge_runtime.set_source_filters(
        forge.source_by_alias("re"),
        [{"column": "reinsurer", "mode": "equals", "value": "XYZ"}])
    # Editing the filter marks the Snapshot stale ("Refresh to apply").
    assert forge.source_by_alias("re").snapshot.stale is True

    # The engine applies the Source filter itself, so we can run over the
    # already-cached Snapshots without re-pulling.
    result = forge_runtime.run_saved_forge(forge)
    df = result.dataframe
    # pol joined re on (A,100),(B,200); reinsurer==XYZ keeps both => 2 rows.
    assert len(df) == 2, df
    assert set(df["reinsurer"]) == {"XYZ"}, df["reinsurer"].tolist()
    print("  add/refresh/filter/run end-to-end:", len(df), "rows  OK")

    # Persist + reload the Forge, then run from disk Snapshots.
    dataforge_store.save_forge(forge)
    reloaded = dataforge_store.load_forge("ReinForge")
    assert reloaded is not None and len(reloaded.sources) == 2
    df2 = forge_runtime.run_saved_forge(reloaded).dataframe
    assert len(df2) == 2, df2
    print("  persist + reload + run-from-disk:", len(df2), "rows  OK")

    # Re-sync after the shared Query definition changes.
    _make_shared_query("Policies", sql="SELECT * FROM Policies WHERE active=1")
    reloaded.source_by_alias("pol").snapshot.stale = False
    did_change = forge_runtime.resync_source(reloaded.source_by_alias("pol"))
    assert did_change is True
    assert reloaded.source_by_alias("pol").definition["sql"].endswith("active=1")
    assert reloaded.source_by_alias("pol").snapshot.stale is True
    print("  re-sync pulls new definition + marks stale  OK")

    # Delete cleans up the Snapshot directory too.
    dataforge_store.delete_forge("ReinForge")
    assert dataforge_store.load_forge("ReinForge") is None
    assert not dataforge_store.has_source_snapshot("ReinForge", "pol")
    print("  delete removes forge + snapshots  OK")


def test_missing_snapshot_raises(tmp_home):
    _make_shared_query("Solo")
    forge = DataForge(name="SoloForge")
    forge_runtime.add_query_as_source(forge, "Solo", alias="solo")
    try:
        forge_runtime.run_saved_forge(forge)  # never refreshed
        assert False, "expected ValueError for missing Snapshot"
    except ValueError as e:
        assert "Snapshot" in str(e)
    print("  missing snapshot raises (no live pull on run)  OK")


# ── Minimal temp-HOME fixture (works under pytest or the __main__ runner) ──

class _TmpHome:
    def __init__(self):
        self._dir = None
        self._old_home = None
        self._old_userprofile = None
        self._old_qo = None

    def __enter__(self):
        import pathlib
        self._dir = tempfile.mkdtemp(prefix="forge_test_home_")
        self._old_home = os.environ.get("HOME")
        self._old_userprofile = os.environ.get("USERPROFILE")
        self._old_qo = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
        os.environ["HOME"] = self._dir
        os.environ["USERPROFILE"] = self._dir
        os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = os.path.join(
            self._dir, "query_objects")
        # dataforge_store caches its dir at import time via Path.home();
        # repoint it for the test.
        self._old_forges = dataforge_store._FORGES_DIR
        dataforge_store._FORGES_DIR = (
            pathlib.Path(self._dir) / ".suiteview" / "saved_dataforges")
        return self

    def __exit__(self, *exc):
        import shutil
        dataforge_store._FORGES_DIR = self._old_forges
        for key, val in (("HOME", self._old_home),
                         ("USERPROFILE", self._old_userprofile),
                         ("SUITEVIEW_QUERY_OBJECTS_DIR", self._old_qo)):
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        shutil.rmtree(self._dir, ignore_errors=True)


# pytest fixture
try:
    import pytest

    @pytest.fixture
    def tmp_home():
        with _TmpHome() as h:
            yield h
except ImportError:  # pragma: no cover
    pass


def main():
    print("=" * 60)
    print("DataForge model/store/runtime tests")
    print("=" * 60)
    no_fixture = [test_model_round_trip, test_legacy_source_round_trip]
    needs_home = [test_add_resync_refresh_and_run, test_missing_snapshot_raises]
    for t in no_fixture:
        print(f"- {t.__name__}")
        t()
    for t in needs_home:
        print(f"- {t.__name__}")
        with _TmpHome() as h:
            t(h)
    print("=" * 60)
    print(f"All {len(no_fixture) + len(needs_home)} tests passed.")


if __name__ == "__main__":
    main()
