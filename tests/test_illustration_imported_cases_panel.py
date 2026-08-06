"""Imported Cases view: file-grouped tree, activation, remove/export intent.

The Imported Cases view is the third page of the List panel. It browses the
imported-case store grouped by source file: a single-case bundle shows the case
name as its node; a multi-case bundle is an expandable parent with a child per
case. The view is store-write-free — it emits intent that the window's
ImportedCasesController turns into dialogs and store writes.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from suiteview.illustration.models import case_store, imported_case_store
from suiteview.illustration.ui.imported_cases_panel import ImportedCasesView

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _inputs(marker="x"):
    return {"grids": {}, "controls": {}, "dynamic": {"lumpsum": marker}}


def _saved(name, tmp_path, *, policy="UL1"):
    store = tmp_path / "saved"
    case_store.save_case(name, policy_number=policy, region="CKPR",
                         company_code="01", inputs=_inputs(name),
                         overwrite=True, directory=store)
    return case_store.load_case(name, directory=store)


def _view(tmp_path):
    _app()
    view = ImportedCasesView()
    view.imported_directory = tmp_path / "imported"
    return view


def test_single_bundle_shows_case_name_node(tmp_path):
    view = _view(tmp_path)
    case = _saved("Solo", tmp_path)
    imported_case_store.save_imported_bundle(
        "Solo", [case], directory=view.imported_directory)
    view.refresh()

    assert view.tree.topLevelItemCount() == 1
    node = view.tree.topLevelItem(0)
    assert node.text(0) == "Solo"
    assert node.childCount() == 0
    kind, path, name = node.data(0, Qt.ItemDataRole.UserRole)
    assert kind == "case" and name == "Solo"


def test_multi_bundle_is_expandable_parent(tmp_path):
    view = _view(tmp_path)
    cases = [_saved("A", tmp_path, policy="UL1"),
             _saved("B", tmp_path, policy="UL2")]
    imported_case_store.save_imported_bundle(
        "Batch", cases, directory=view.imported_directory)
    view.refresh()

    assert view.tree.topLevelItemCount() == 1
    parent = view.tree.topLevelItem(0)
    assert parent.text(0).startswith("Batch")
    assert parent.childCount() == 2
    assert parent.data(0, Qt.ItemDataRole.UserRole)[0] == "bundle"
    child_names = [parent.child(i).text(0) for i in range(2)]
    assert child_names == ["A", "B"]


def test_double_click_case_emits_activation(tmp_path):
    view = _view(tmp_path)
    case = _saved("Solo", tmp_path)
    imported_case_store.save_imported_bundle(
        "Solo", [case], directory=view.imported_directory)
    view.refresh()

    captured = []
    view.case_activated.connect(lambda p, n: captured.append((p, n)))
    node = view.tree.topLevelItem(0)
    view._on_double_clicked(node, 0)
    assert len(captured) == 1 and captured[0][1] == "Solo"


def test_import_button_emits_request(tmp_path):
    view = _view(tmp_path)
    fired = []
    view.import_requested.connect(lambda: fired.append(True))
    view.import_btn.click()
    assert fired == [True]


def test_selected_cases_and_remove_payload(tmp_path):
    view = _view(tmp_path)
    cases = [_saved("A", tmp_path, policy="UL1"),
             _saved("B", tmp_path, policy="UL2")]
    imported_case_store.save_imported_bundle(
        "Batch", cases, directory=view.imported_directory)
    view.refresh()

    parent = view.tree.topLevelItem(0)
    parent.child(0).setSelected(True)
    parent.child(1).setSelected(True)
    items = view._selected_cases()
    assert sorted(n for _, n in items) == ["A", "B"]

    removed = []
    view.cases_remove_requested.connect(lambda x: removed.append(x))
    view._on_delete_key_pressed()
    assert len(removed) == 1 and sorted(n for _, n in removed[0]) == ["A", "B"]


def test_corrupt_store_surfaced_as_disabled_row(tmp_path):
    view = _view(tmp_path)
    folder = view.imported_directory
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "broken.cases.json").write_text("{not json", encoding="utf-8")
    view.refresh()
    assert view.tree.topLevelItemCount() == 1
    row = view.tree.topLevelItem(0)
    assert "unreadable" in row.text(0).lower()


# ── controller: import / activate ────────────────────────────────────


class _FakeWindow:
    def __init__(self):
        self.status = []
        self.activated = []

    def _show_status(self, text):
        self.status.append(text)

    def _activate_case(self, case):
        self.activated.append(case)


def _bundle_file(tmp_path, name, cases):
    from suiteview.illustration.models import case_bundle

    return case_bundle.write_bundle(tmp_path / name, cases, name=name)


def test_controller_imports_all_valid_bundle(tmp_path):
    from suiteview.illustration.ui.imported_case_controls import (
        ImportedCasesController,
    )

    _app()
    store = tmp_path / "imported"
    changed = []
    controller = ImportedCasesController(
        _FakeWindow(), directory=store,
        on_changed=lambda: changed.append(True))

    cases = [_saved("A", tmp_path, policy="UL1"),
             _saved("B", tmp_path, policy="UL2")]
    src = _bundle_file(tmp_path, "MyBatch", cases)

    controller.import_files([str(src)])
    bundles = imported_case_store.list_imported_bundles(directory=store)
    assert len(bundles) == 1
    assert [c.name for c in bundles[0].cases] == ["A", "B"]
    assert changed == [True]


def test_controller_activate_loads_case(tmp_path):
    from suiteview.illustration.ui.imported_case_controls import (
        ImportedCasesController,
    )

    _app()
    store = tmp_path / "imported"
    window = _FakeWindow()
    controller = ImportedCasesController(window, directory=store)
    case = _saved("Solo", tmp_path)
    bundle = imported_case_store.save_imported_bundle(
        "Solo", [case], directory=store)

    controller.activate_case(str(bundle.path), "Solo")
    assert len(window.activated) == 1
    assert window.activated[0].name == "Solo"
