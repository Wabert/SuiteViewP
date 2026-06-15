"""Tests for query identity (QueryObject.id + id-keyed store) and the
QueryOrganizer (bookmark-style groups for the Query Object browser).

All offline/minipc-safe: temp dirs, synthetic objects, no live DB.
See DATAFORGE_DESIGN.md section 8.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from suiteview.audit import qdef_store, query_object_store, saved_query_store  # noqa: E402
from suiteview.audit.query_object import (  # noqa: E402
    QueryObject, adhoc_source_object, manual_sql_query_object,
    query_display_name,
)
from suiteview.audit.query_organizer import (  # noqa: E402
    COMMONS_GROUP_ID,
    COMMONS_GROUP_NAME,
    QueryOrganizer,
)
from suiteview.audit.dataforge import dataforge_store  # noqa: E402
from suiteview.audit.dataforge.dataforge_model import DataForge  # noqa: E402


class _TmpHome:
    """Temp HOME + repointed stores (mirrors test_forge_runtime's fixture)."""

    def __enter__(self):
        self._dir = tempfile.mkdtemp(prefix="organizer_test_home_")
        self._old_env = {k: os.environ.get(k) for k in
                         ("HOME", "USERPROFILE", "SUITEVIEW_QUERY_OBJECTS_DIR",
                          "SUITEVIEW_QUERY_ORGANIZER_FILE")}
        os.environ["HOME"] = self._dir
        os.environ["USERPROFILE"] = self._dir
        os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = os.path.join(
            self._dir, "query_objects")
        os.environ["SUITEVIEW_QUERY_ORGANIZER_FILE"] = os.path.join(
            self._dir, "query_organizer.json")
        self._old_forges = dataforge_store._FORGES_DIR
        self._old_qdefs = qdef_store._QDEFS_DIR
        self._old_queries = saved_query_store._QUERIES_DIR
        dataforge_store._FORGES_DIR = (
            Path(self._dir) / ".suiteview" / "saved_dataforges")
        qdef_store._QDEFS_DIR = (
            Path(self._dir) / ".suiteview" / "qdefinitions")
        saved_query_store._QUERIES_DIR = (
            Path(self._dir) / ".suiteview" / "saved_queries")
        return self

    def __exit__(self, *exc):
        import shutil
        dataforge_store._FORGES_DIR = self._old_forges
        qdef_store._QDEFS_DIR = self._old_qdefs
        saved_query_store._QUERIES_DIR = self._old_queries
        for key, val in self._old_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        shutil.rmtree(self._dir, ignore_errors=True)


try:
    import pytest

    @pytest.fixture
    def tmp_home():
        with _TmpHome() as h:
            yield h
except ImportError:  # pragma: no cover
    pass


def _make(name: str, dsn: str = "NEON_DSN") -> QueryObject:
    obj = manual_sql_query_object(
        name=name, sql=f"SELECT 1 -- {name}", dsn=dsn,
        result_columns=["a", "b"])
    query_object_store.save_object(obj, force_new=True)
    return obj


def _organizer() -> QueryOrganizer:
    return QueryOrganizer(Path(os.environ["SUITEVIEW_QUERY_ORGANIZER_FILE"]))


def _organizer_no_seed() -> QueryOrganizer:
    """An organizer whose file already exists (suppresses first-run seeding)."""
    org = _organizer()
    org.load()
    org.save()
    return org


# -- Identity / store -------------------------------------------------------

def test_id_round_trip_and_display_name():
    obj = manual_sql_query_object(name="Q", sql="SELECT 1", dsn="UL_Rates",
                                  result_columns=["a"])
    assert obj.id and len(obj.id) == 32
    restored = QueryObject.from_dict(obj.to_dict())
    assert restored.id == obj.id
    assert query_display_name(restored) == "Q [UL_Rates]"
    csv = adhoc_source_object("Claims", source_type="csv",
                              metadata={"path": "x.csv"}, columns=["p"])
    assert query_display_name(csv) == "Claims [CSV]"
    print("  id round-trip + display name  OK")


def test_legacy_file_migration_keeps_id_stable(tmp_home):
    objects_dir = Path(os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"])
    objects_dir.mkdir(parents=True, exist_ok=True)
    legacy = {"name": "Old Query", "kind": "manual_sql", "dsn": "NEON_DSN"}
    (objects_dir / "Old Query.json").write_text(
        json.dumps(legacy), encoding="utf-8")

    first = query_object_store.load_object("Old Query")
    assert first is not None and first.id
    # Migration persisted: the legacy file is gone, the id-form file exists,
    # and a second load yields the SAME id (stability is the whole point).
    assert not (objects_dir / "Old Query.json").exists()
    second = query_object_store.load_object("Old Query")
    assert second.id == first.id
    print("  legacy migration, stable id  OK")


def test_duplicate_names_allowed_and_id_lookup(tmp_home):
    from datetime import timedelta

    a = _make("Same Name")
    b = _make("Same Name")
    assert a.id != b.id
    # Same-microsecond saves make "newest" ambiguous — pin b strictly newer.
    b.updated_at = max(b.updated_at, a.updated_at + timedelta(microseconds=1))
    query_object_store.save_object(b)
    names = [o.name for o in query_object_store.list_objects()]
    assert names.count("Same Name") == 2
    assert query_object_store.load_object_by_id(a.id).id == a.id
    assert query_object_store.load_object_by_id(b.id).id == b.id
    # Name lookup returns the newest match (compat seam).
    assert query_object_store.load_object("Same Name").id == b.id
    # Id-precise delete removes only one twin.
    query_object_store.delete_object_by_id(a.id)
    assert query_object_store.load_object_by_id(a.id) is None
    assert query_object_store.load_object_by_id(b.id) is not None
    print("  duplicate names + id lookup/delete  OK")


def test_republish_adopts_existing_id(tmp_home):
    original = _make("Premiums")
    # A rebuild-and-save flow (fresh id, same name) must overwrite, not fork.
    rebuilt = manual_sql_query_object(name="Premiums", sql="SELECT 2",
                                      dsn="NEON_DSN", result_columns=["a"])
    assert rebuilt.id != original.id
    query_object_store.save_object(rebuilt)
    assert rebuilt.id == original.id  # adopted
    objs = [o for o in query_object_store.list_objects()
            if o.name == "Premiums"]
    assert len(objs) == 1 and objs[0].sql == "SELECT 2"
    print("  republish adopts id (no fork)  OK")


def test_copy_by_id_keeps_name_new_id(tmp_home):
    src = _make("Reins")
    copied = query_object_store.copy_object_by_id(src.id)
    assert copied.id != src.id and copied.name == "Reins"
    assert len([o for o in query_object_store.list_objects()
                if o.name == "Reins"]) == 2
    print("  copy_object_by_id keeps name, new id  OK")


def test_send_query_to_forge_persists_builder_source_copy(tmp_home):
    src = _make("Policies")
    dataforge_store.save_forge(DataForge(
        name="Builder Forge",
        config={"sources": []},
    ))

    org = _organizer_no_seed()
    assert org.send_query_to_forge(src.id, "Builder Forge") is True

    copy_name = "Policies [Builder Forge]"
    copied = query_object_store.load_object(copy_name)
    assert copied is not None
    assert copied.id != src.id
    # The dataforge tag also carries query_object_id (for id resolution on the
    # qdef round-trip), so assert the forge/source linkage rather than exact eq.
    assert copied.config["dataforge"]["forge_name"] == "Builder Forge"
    assert copied.config["dataforge"]["source_name"] == "Policies"
    assert qdef_store.qdef_exists(copy_name, forge_name="Builder Forge")

    reloaded = dataforge_store.load_forge("Builder Forge")
    assert reloaded is not None
    assert reloaded.config["sources"] == [copy_name]
    assert [source.query_name for source in reloaded.sources] == [copy_name]
    source_tag = reloaded.sources[0].definition["config"]["dataforge"]
    assert source_tag["forge_name"] == "Builder Forge"
    assert source_tag["source_name"] == "Policies"
    print("  send query to forge persists builder source copy  OK")


# -- Organizer ---------------------------------------------------------------

def test_groups_create_move_delete(tmp_home):
    a, b = _make("A"), _make("B")
    org = _organizer_no_seed()
    org.reconcile(query_object_store.list_objects(), [])
    group = org.create_group("Claims Work")

    org.move_query(a.id, group["id"])
    assert org.query_location(a.id) == group["id"]
    assert org.query_location(b.id) is None  # at root

    # Move back to root at index 0.
    org.move_query(a.id, None, 0)
    assert org.query_location(a.id) is None
    commons = org.commons_group()
    assert commons["id"] == COMMONS_GROUP_ID
    assert commons["name"] == COMMONS_GROUP_NAME
    assert commons["items"][0]["query_id"] == a.id
    assert not org.rename_group(COMMONS_GROUP_ID, "Other")
    org.move_root_item(commons, len(org.items))
    assert org.items[-1] is commons
    org.reconcile(query_object_store.list_objects(), [])
    assert org.items[-1]["id"] == COMMONS_GROUP_ID

    # Deleting a group keeps its queries (refs move to root).
    org.move_query(b.id, group["id"])
    kept = org.delete_group(group["id"], keep_queries=True)
    assert kept == [b.id]
    assert org.query_ref(b.id) is not None
    assert any(child["query_id"] == b.id for child in org.commons_group()["items"])
    print("  groups: create/move/delete  OK")


def test_reconcile_seeds_prunes_appends(tmp_home):
    cy = manual_sql_query_object(name="CL", sql="s", dsn="NEON_DSN",
                                 result_columns=["a"])
    cy.kind = "cyberlife_query"
    query_object_store.save_object(cy, force_new=True)
    _make("ML")  # manual_sql kind

    org = _organizer()
    changed = org.reconcile(query_object_store.list_objects(), ["F1"])
    assert changed
    # First run seeded kind groups.
    assert "Cyberlife" in org.group_names()
    assert "Manual SQL" in org.group_names()
    assert org.forge_ref("F1") is not None

    # A new unorganized query appears at root on the next reconcile...
    c = _make("New One")
    org.reconcile(query_object_store.list_objects(), ["F1"])
    assert org.query_ref(c.id) is not None
    # ...and a deleted query's ref is pruned.
    query_object_store.delete_object_by_id(c.id)
    org.reconcile(query_object_store.list_objects(), [])
    assert org.query_ref(c.id) is None
    assert org.forge_ref("F1") is None  # forge gone too
    org.save()
    reloaded = _organizer()
    reloaded.load()
    assert "Cyberlife" in reloaded.group_names()
    print("  reconcile: seed/prune/append + persistence  OK")


def test_reconcile_skips_forge_owned_copies(tmp_home):
    owned = manual_sql_query_object(name="X [Forge: F]", sql="s",
                                    dsn="NEON_DSN", result_columns=["a"])
    owned.config["dataforge"] = {"forge_name": "F", "source_name": "X"}
    query_object_store.save_object(owned, force_new=True)
    org = _organizer_no_seed()
    org.reconcile(query_object_store.list_objects(), [])
    assert org.query_ref(owned.id) is None
    print("  reconcile skips forge-owned copies  OK")


def test_copy_query_and_clone_group(tmp_home):
    a, b = _make("A"), _make("B")
    org = _organizer_no_seed()
    org.reconcile(query_object_store.list_objects(), [])
    group = org.create_group("Originals")
    org.move_query(a.id, group["id"])
    org.move_query(b.id, group["id"])

    copied = org.copy_query(a.id, group["id"])
    assert copied.id != a.id and copied.name == "A"
    assert org.query_location(copied.id) == group["id"]

    clone = org.clone_group(group["id"])
    assert clone["name"] == "Originals (2)"
    assert len(clone["items"]) == 3  # a, b, and the copy -- all re-copied
    clone_ids = {c["query_id"] for c in clone["items"]}
    assert clone_ids.isdisjoint({a.id, b.id, copied.id})  # all new ids
    print("  copy query + clone group (deep)  OK")


def test_forge_membership_and_clone(tmp_home):
    q = _make("Policies")
    dataforge_store.save_forge(DataForge(name="MyForge"))
    org = _organizer_no_seed()
    org.reconcile(query_object_store.list_objects(), ["MyForge"])

    # Copy into the forge: standalone query stays.
    assert org.send_query_to_forge(q.id, "MyForge")
    forge = dataforge_store.load_forge("MyForge")
    assert len(forge.sources) == 1
    assert forge.sources[0].definition["name"] == "Policies [MyForge]"
    assert query_object_store.load_object_by_id(q.id) is not None

    # Move a second query in: standalone query is consumed.
    q2 = _make("Reins")
    org.reconcile(query_object_store.list_objects(), ["MyForge"])
    assert org.send_query_to_forge(q2.id, "MyForge", move=True)
    assert query_object_store.load_object_by_id(q2.id) is None
    assert org.query_ref(q2.id) is None
    assert len(dataforge_store.load_forge("MyForge").sources) == 2

    # Extract a Source back out as a standalone query (move semantics).
    out = org.extract_query_from_forge("MyForge", "Reins [MyForge]",
                                       remove_source=True)
    assert out is not None and out.name == "Reins [MyForge]"
    assert query_object_store.load_object_by_id(out.id) is not None
    assert len(dataforge_store.load_forge("MyForge").sources) == 1
    assert "dataforge" not in (out.config or {})

    # Clone the forge with its Snapshot.
    dataforge_store.save_source_snapshot(
        "MyForge", "Policies [MyForge]", pd.DataFrame({"a": [1, 2]}))
    clone_name = org.clone_forge("MyForge")
    assert clone_name == "MyForge (2)"
    assert dataforge_store.forge_exists(clone_name)
    cloned = dataforge_store.load_forge(clone_name)
    assert len(cloned.sources) == 1
    snap = dataforge_store.load_source_snapshot(clone_name, "Policies [MyForge]")
    assert snap is not None and len(snap) == 2
    assert org.forge_ref(clone_name) is not None
    print("  forge membership (copy/move/extract) + clone  OK")


def test_browser_tree_builds_from_organizer(tmp_home):
    try:
        from PyQt6.QtCore import QRect, Qt
        from PyQt6.QtGui import QPainter, QPixmap
        from PyQt6.QtWidgets import QApplication, QAbstractItemView, QStyleOptionViewItem
    except Exception as exc:  # pragma: no cover
        print(f"  browser tree SKIPPED (no PyQt6: {exc})")
        return

    from suiteview.audit.query_object_viewer_window import (
        QueryObjectViewerWindow, _payload,
    )
    import suiteview.audit.query_organizer as qorg

    app = QApplication.instance() or QApplication([])
    assert app is not None

    a = _make("Claims Pull")            # goes into a group
    b = _make("Loose One", dsn="UL_Rates")  # stays at root
    dataforge_store.save_forge(DataForge(name="Claims Forge"))

    org = _organizer_no_seed()
    org.reconcile(query_object_store.list_objects(), ["Claims Forge"])
    group = org.create_group("Claims Work")
    org.move_query(a.id, group["id"])
    org.save()
    qorg._organizer = None  # the window's singleton must reload from disk

    window = QueryObjectViewerWindow()
    try:
        app.processEvents()
        # Walk the top level: expect Commons, the user group, and the forge.
        kinds = {}
        for i in range(window.tree.topLevelItemCount()):
            item = window.tree.topLevelItem(i)
            kinds.setdefault(_payload(item).get("type"), []).append(item)
        assert {"group", "forge"} <= set(kinds), kinds.keys()

        commons_item = next(item for item in kinds["group"]
                            if _payload(item)["group_id"] == COMMONS_GROUP_ID)
        assert _payload(commons_item)["name"] == COMMONS_GROUP_NAME
        assert commons_item.childCount() == 1
        loose = commons_item.child(0)
        def expected_query_payload(query_id, name):
            return {"type": "query", "id": query_id,
                "name": name, "badge": "SQL",
                "badge_color": "#5A3218",
                "badge_fill": "#5A3218",
                "badge_text_color": "#FFFFFF"}

        loose_payload = _payload(loose)
        assert loose_payload == expected_query_payload(b.id, "Loose One")
        assert "[UL_Rates]" in loose.text(0)

        group_item = next(item for item in kinds["group"]
                          if _payload(item).get("name") == "Claims Work")
        assert _payload(group_item)["name"] == "Claims Work"
        assert group_item.childCount() == 1
        child = group_item.child(0)
        assert _payload(child) == expected_query_payload(a.id, "Claims Pull")
        assert "[NEON_DSN]" in child.text(0)

        forge_item = kinds["forge"][0]
        assert _payload(forge_item) == {"type": "forge", "name": "Claims Forge"}

        # Delegate paint covers the custom pill rendering path that real Qt
        # painting uses for groups, DataForges, and query badge colors.
        delegate = window.tree.itemDelegate()
        for painted_item in (commons_item, group_item, forge_item, loose):
            pixmap = QPixmap(280, 40)
            pixmap.fill(Qt.GlobalColor.white)
            painter = QPainter(pixmap)
            option = QStyleOptionViewItem()
            option.rect = QRect(0, 0, 260, 30)
            delegate.paint(painter, option, window.tree.indexFromItem(painted_item))
            painter.end()

        window.edit_search.setText("loose")
        app.processEvents()
        assert window.tree.topLevelItemCount() == 1
        assert not window.tree.dragEnabled()
        assert not window.tree.acceptDrops()
        filtered_parent = window.tree.topLevelItem(0)
        assert _payload(filtered_parent)["group_id"] == COMMONS_GROUP_ID
        assert filtered_parent.childCount() == 1
        filtered = filtered_parent.child(0)
        assert _payload(filtered) == expected_query_payload(b.id, "Loose One")

        window.edit_search.setText("claims")
        app.processEvents()
        filtered_kinds = {}
        for i in range(window.tree.topLevelItemCount()):
            item = window.tree.topLevelItem(i)
            filtered_kinds.setdefault(_payload(item).get("type"), []).append(item)
        assert {"group", "forge"} <= set(filtered_kinds), filtered_kinds.keys()
        assert filtered_kinds["group"][0].childCount() == 1

        # Drop-position resolution: OnItem over the group targets the group.
        window.edit_search.clear()
        app.processEvents()
        assert window.tree.dragEnabled()
        assert window.tree.acceptDrops()
        kinds = {}
        for i in range(window.tree.topLevelItemCount()):
            item = window.tree.topLevelItem(i)
            kinds.setdefault(_payload(item).get("type"), []).append(item)
        group_item = kinds["group"][0]
        if _payload(group_item)["group_id"] == COMMONS_GROUP_ID:
            group_item = kinds["group"][1]
        child = group_item.child(0)
        on_item = QAbstractItemView.DropIndicatorPosition.OnItem
        below = QAbstractItemView.DropIndicatorPosition.BelowItem
        assert window._drop_position(group_item, on_item) == (group["id"], None)
        dest_group, index = window._drop_position(child, below)
        assert dest_group == group["id"] and index == 1
        print("  browser tree from organizer + payloads + drop positions  OK")
    finally:
        window.close()
        qorg._organizer = None


def main():
    no_fixture = [test_id_round_trip_and_display_name]
    needs_home = [
        test_legacy_file_migration_keeps_id_stable,
        test_duplicate_names_allowed_and_id_lookup,
        test_republish_adopts_existing_id,
        test_copy_by_id_keeps_name_new_id,
        test_groups_create_move_delete,
        test_reconcile_seeds_prunes_appends,
        test_reconcile_skips_forge_owned_copies,
        test_copy_query_and_clone_group,
        test_forge_membership_and_clone,
        test_browser_tree_builds_from_organizer,
    ]
    print("=" * 60)
    print("Query identity + organizer tests")
    print("=" * 60)
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
