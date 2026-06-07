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

from suiteview.audit import qdef_store, query_object_store, saved_query_store  # noqa: E402
from suiteview.audit.qdefinition import QDefinition  # noqa: E402
from suiteview.audit.query_object import (  # noqa: E402
    QueryObject, manual_sql_query_object, qdefinition_from_query_object,
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


def test_dataforge_group_save_publishes_query_object_metadata(tmp_home):
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover
        print(f"  group save publish SKIPPED (no PyQt6: {exc})")
        return

    from suiteview.audit.dataforge.dataforge_group import DataForgeGroup

    app = QApplication.instance() or QApplication([])
    assert app is not None

    group = DataForgeGroup("⚙ (new)", saved_forge_name="")
    qd = QDefinition(
        name="Policies [DataForge]",
        sql="SELECT * FROM POLICIES",
        dsn="FAKE_DSN",
        source_design="Policies",
        result_columns=["policy_number"],
        column_types={"policy_number": "str"},
        tables=["POLICIES"],
    )
    qd.query_object_config = {"dataforge": {"source_name": "Policies"}}
    group._sources[qd.name] = qd

    sources = group._dataforge_sources_for_save("RGA - EXECUL and Claims")
    assert len(sources) == 1
    obj = query_object_store.load_object("Policies [DataForge]")
    assert obj is not None
    assert obj.config["dataforge"] == {
        "forge_name": "RGA - EXECUL and Claims",
        "source_name": "Policies",
    }
    assert sources[0].definition["config"]["dataforge"]["forge_name"] == "RGA - EXECUL and Claims"
    print("  group save publishes DataForge QueryObject metadata  OK")


def test_dataforge_display_fields_add_reorder_and_aggregate():
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover
        print(f"  display fields SKIPPED (no PyQt6: {exc})")
        return

    from suiteview.audit.dataforge.dataforge_group import DataForgeGroup, ForgeDisplayTab

    app = QApplication.instance() or QApplication([])
    assert app is not None

    group = DataForgeGroup("⚙ (new)", saved_forge_name="")
    tab = group.display_tab
    tab.add_query_field("pol", "company_code")
    tab.add_query_field("pol", "policy_number")
    tab.add_query_field("pol", "face_amount")
    assert tab.display_all is False
    assert tab.get_selected_columns() == ["company_code", "policy_number", "face_amount"]

    tab._reorder_row("pol.face_amount", 1)
    assert tab.get_selected_columns() == ["company_code", "face_amount", "policy_number"]
    tab._rows[1].set_state({"aggregate": 2})  # SUM
    state = tab.get_state()

    restored = ForgeDisplayTab()
    restored.set_state(state)
    assert restored.get_selected_columns() == ["company_code", "face_amount", "policy_number"]
    assert restored._rows[1].aggregate == "SUM"

    aggregate_tab = group.display_tab
    aggregate_tab.set_state({
        "display_all": False,
        "fields": [
            {"field_key": "pol.company_code", "display_name": "company_code", "aggregate": 0},
            {"field_key": "pol.face_amount", "display_name": "face_amount", "aggregate": 2},
        ],
    })
    df = pd.DataFrame({
        "company_code": ["A", "A", "B"],
        "policy_number": ["100", "101", "200"],
        "face_amount": [10, 15, 7],
    })
    result = group._apply_display_columns(df)
    assert result.to_dict("records") == [
        {"company_code": "A", "SUM_face_amount": 25},
        {"company_code": "B", "SUM_face_amount": 7},
    ]
    print("  display fields add/reorder/aggregate  OK")


def test_dataforge_add_source_deep_copies_query_object_for_join_canvas(tmp_home):
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover
        print(f"  source copy SKIPPED (no PyQt6: {exc})")
        return

    from suiteview.audit.dataforge.dataforge_group import DataForgeGroup

    app = QApplication.instance() or QApplication([])
    assert app is not None

    original = _make_shared_query(
        "Policies",
        sql="SELECT policy_number, face_amount FROM POLICIES",
        cols=["policy_number", "face_amount"],
    )
    group = DataForgeGroup("⚙ (new)", saved_forge_name="MyForge")

    copied_qd = group.add_source_copy("Policies")

    assert copied_qd is not None
    assert copied_qd.name == "Policies [MyForge]"
    assert list(group._sources.keys()) == ["Policies [MyForge]"]
    # The added Source auto-appears on the join canvas (no manual add needed);
    # re-adding an already-shown Source is a no-op.
    assert "Policies [MyForge]" in [s.alias for s in group.joins_tab.model.sources]
    assert group.joins_tab.add_query_table("Policies [MyForge]") is False

    copied = query_object_store.load_object("Policies [MyForge]")
    reloaded_original = query_object_store.load_object("Policies")
    assert copied is not None
    assert reloaded_original is not None
    assert copied.name != reloaded_original.name
    assert copied.config["dataforge"] == {
        "forge_name": "MyForge",
        "source_name": "Policies",
    }

    copied.sql = "SELECT policy_number FROM PRIVATE_POLICIES"
    query_object_store.save_object(copied)
    reloaded_original = query_object_store.load_object("Policies")
    assert reloaded_original.sql == original.sql
    print("  DataForge source add deep-copies QueryObject + joins canvas add  OK")


def test_new_dataforge_saves_visual_query_source_from_ul_rates(tmp_home):
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover
        print(f"  visual source save SKIPPED (no PyQt6: {exc})")
        return

    from suiteview.audit.dataforge.dataforge_group import DataForgeGroup
    from suiteview.audit.saved_query import SavedQuery

    app = QApplication.instance() or QApplication([])
    assert app is not None

    saved_query_store.save_query(SavedQuery(
        name="UL Rates Visual",
        source_group="UL_Rates",
        dsn="UL_Rates",
        tables=["dbo.Rates"],
        sql="SELECT rate_id, duration FROM dbo.Rates",
        result_columns=["rate_id", "duration"],
        column_types={"rate_id": "int", "duration": "int"},
        config={"select_tab": {"display_all": False, "fields": [
            {"field_key": "dbo.Rates.rate_id", "display_name": "rate_id"},
            {"field_key": "dbo.Rates.duration", "display_name": "duration"},
        ]}},
    ))

    group = DataForgeGroup("⚙ (new)", saved_forge_name="")
    copied_qd = group.add_source_copy("UL Rates Visual")
    assert copied_qd is not None
    assert list(group._sources) == ["UL Rates Visual [DataForge]"]
    # Added Source auto-appears on the canvas; re-adding is a no-op.
    assert "UL Rates Visual [DataForge]" in [
        s.alias for s in group.joins_tab.model.sources]
    assert group.joins_tab.add_query_table("UL Rates Visual [DataForge]") is False
    group.display_tab.add_query_field("UL Rates Visual [DataForge]", "rate_id")
    assert query_object_store.object_exists("UL Rates Visual [DataForge]")
    assert saved_query_store.query_exists("UL Rates Visual [DataForge]")

    forge_name = "UL Rates Forge"
    group._promote_unsaved_source_names(forge_name)
    forge = DataForge(
        name=forge_name,
        sources=group._dataforge_sources_for_save(forge_name),
        config=group.get_config(),
    )
    dataforge_store.save_forge(forge)

    reloaded = dataforge_store.load_forge(forge_name)
    assert reloaded is not None
    assert not query_object_store.object_exists("UL Rates Visual [DataForge]")
    assert not saved_query_store.query_exists("UL Rates Visual [DataForge]")
    assert query_object_store.object_exists("UL Rates Visual [UL Rates Forge]")
    assert saved_query_store.query_exists("UL Rates Visual [UL Rates Forge]")
    assert reloaded.config["sources"] == ["UL Rates Visual [UL Rates Forge]"]
    assert reloaded.config["joins_tab"]["sources"][0]["alias"] == "UL Rates Visual [UL Rates Forge]"
    assert reloaded.config["display_tab"]["fields"][0]["field_key"] == "UL Rates Visual [UL Rates Forge].rate_id"
    restored_group = DataForgeGroup("⚙ UL Rates Forge", saved_forge_name=forge_name)
    restored_group.set_config(reloaded.config)

    assert list(restored_group._sources) == ["UL Rates Visual [UL Rates Forge]"]
    restored_qd = restored_group._sources["UL Rates Visual [UL Rates Forge]"]
    assert restored_qd.query_object_kind == "visual_query"
    assert restored_qd.dsn == "UL_Rates"
    assert restored_qd.result_columns == ["rate_id", "duration"]
    saved_qd = qdef_store.load_qdef("UL Rates Visual [UL Rates Forge]", forge_name=forge_name)
    assert saved_qd is not None
    assert saved_qd.query_object_config["dataforge"] == {
        "forge_name": forge_name,
        "source_name": "UL Rates Visual",
    }
    print("  new DataForge saves/reloads UL_Rates visual source  OK")


def test_dataforge_save_as_overwrite_replaces_stale_visual_copy(tmp_home):
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover
        print(f"  overwrite visual source SKIPPED (no PyQt6: {exc})")
        return

    from suiteview.audit.dataforge.dataforge_group import DataForgeGroup
    from suiteview.audit.saved_query import SavedQuery

    app = QApplication.instance() or QApplication([])
    assert app is not None

    saved_query_store.save_query(SavedQuery(
        name="Overwrite Visual",
        source_group="UL_Rates",
        dsn="UL_Rates",
        tables=["dbo.Rates"],
        sql="SELECT stale_rate_id FROM dbo.Rates",
        result_columns=["stale_rate_id"],
        column_types={"stale_rate_id": "int"},
    ))
    query_object_store.copy_object("Overwrite Visual", "Overwrite Visual [Overwrite Forge]")
    stale_obj = query_object_store.load_object("Overwrite Visual [Overwrite Forge]")
    assert stale_obj is not None
    stale_obj.config = {"dataforge": {
        "forge_name": "Overwrite Forge",
        "source_name": "Overwrite Visual",
    }}
    query_object_store.save_object(stale_obj)
    stale_qd = qdefinition_from_query_object(stale_obj)
    stale_qd.forge_name = "Overwrite Forge"
    qdef_store.save_qdef(stale_qd)
    dataforge_store.save_forge(DataForge(name="Overwrite Forge", sources=[], config={}))

    saved_query_store.save_query(SavedQuery(
        name="Overwrite Visual",
        source_group="UL_Rates",
        dsn="UL_Rates",
        tables=["dbo.Rates"],
        sql="SELECT current_rate_id FROM dbo.Rates",
        result_columns=["current_rate_id"],
        column_types={"current_rate_id": "int"},
    ))
    group = DataForgeGroup("⚙ (new)", saved_forge_name="")
    copied_qd = group.add_source_copy("Overwrite Visual")
    assert copied_qd is not None

    temp_saved = saved_query_store.load_query("Overwrite Visual [DataForge]")
    assert temp_saved is not None
    assert temp_saved.sql == "SELECT current_rate_id FROM dbo.Rates"

    group._delete_existing_forge_records("Overwrite Forge")
    group._promote_unsaved_source_names("Overwrite Forge")
    forge = DataForge(
        name="Overwrite Forge",
        sources=group._dataforge_sources_for_save("Overwrite Forge"),
        config=group.get_config(),
    )
    dataforge_store.save_forge(forge)

    promoted_saved = saved_query_store.load_query("Overwrite Visual [Overwrite Forge]")
    assert promoted_saved is not None
    assert promoted_saved.sql == "SELECT current_rate_id FROM dbo.Rates"
    assert not saved_query_store.query_exists("Overwrite Visual [DataForge]")
    assert not qdef_store.qdef_exists("Overwrite Visual [DataForge]", forge_name="Overwrite Forge")
    print("  DataForge Save As overwrite replaces stale visual copy  OK")


def test_query_object_browser_repairs_missing_dataforge_visual_copy(tmp_home):
    from suiteview.audit.query_object_viewer_window import (
        QueryObjectViewerWindow,
        _dataforge_info,
    )
    from suiteview.audit.saved_query import SavedQuery

    saved_query_store.save_query(SavedQuery(
        name="Browser Visual",
        source_group="UL_Rates",
        dsn="UL_Rates",
        tables=["dbo.Rates"],
        sql="SELECT rate_id FROM dbo.Rates",
        result_columns=["rate_id"],
        column_types={"rate_id": "int"},
    ))
    copied = query_object_store.copy_object(
        "Browser Visual", "Browser Visual [Browser Forge]")
    copied.config = {"dataforge": {
        "forge_name": "Browser Forge",
        "source_name": "Browser Visual",
    }}
    query_object_store.save_object(copied)
    dataforge_store.save_forge(DataForge(
        name="Browser Forge",
        sources=[DataForgeSource(
            query_name=copied.name,
            definition=copied.to_dict(),
        )],
        config={"sources": [copied.name]},
    ))
    saved_query_store.delete_query(copied.name)
    assert query_object_store.load_object(copied.name) is None

    viewer = QueryObjectViewerWindow.__new__(QueryObjectViewerWindow)
    viewer._ensure_dataforge_query_objects()

    repaired = query_object_store.load_object(copied.name)
    assert repaired is not None
    assert _dataforge_info(repaired) == ("Browser Forge", "Browser Visual")
    print("  Query Object Browser repairs missing DataForge visual copy  OK")


# ── Minimal temp-HOME fixture (works under pytest or the __main__ runner) ──

class _TmpHome:
    def __init__(self):
        self._dir = None
        self._old_home = None
        self._old_userprofile = None
        self._old_qo = None
        self._old_qdefs = None
        self._old_queries = None

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
        self._old_qdefs = qdef_store._QDEFS_DIR
        self._old_queries = saved_query_store._QUERIES_DIR
        dataforge_store._FORGES_DIR = (
            pathlib.Path(self._dir) / ".suiteview" / "saved_dataforges")
        qdef_store._QDEFS_DIR = (
            pathlib.Path(self._dir) / ".suiteview" / "qdefinitions")
        saved_query_store._QUERIES_DIR = (
            pathlib.Path(self._dir) / ".suiteview" / "saved_queries")
        return self

    def __exit__(self, *exc):
        import shutil
        dataforge_store._FORGES_DIR = self._old_forges
        qdef_store._QDEFS_DIR = self._old_qdefs
        saved_query_store._QUERIES_DIR = self._old_queries
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
    needs_home = [
        test_add_resync_refresh_and_run,
        test_missing_snapshot_raises,
        test_dataforge_group_save_publishes_query_object_metadata,
        test_dataforge_add_source_deep_copies_query_object_for_join_canvas,
        test_new_dataforge_saves_visual_query_source_from_ul_rates,
        test_dataforge_save_as_overwrite_replaces_stale_visual_copy,
        test_query_object_browser_repairs_missing_dataforge_visual_copy,
    ]
    no_fixture.append(test_dataforge_display_fields_add_reorder_and_aggregate)
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
