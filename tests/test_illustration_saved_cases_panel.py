"""Saved Cases view + Save button: browsing, search, activation, save/copy.

The Saved Cases view is the second page of the merged List side panel
(behind its Policies | Saved Cases toggle): a FLAT two-column case list —
Saved date | Case Name, newest first, no policy grouping, header-click
sorting (the Saved column sorts chronologically) — under a live search bar
filtering on the visible Case Name ONLY. Activating a row
restores the case's FROZEN IllustrationPolicyData snapshot with a visible
as-of indicator and no DB2 round trip; v1 cases fall back to a live load
with a note. Right-click a case for Rename / Copy / Delete. The lookup
bar's Save button (next to Run Values) drives the save flow, pre-filling
the loaded case's name in snapshot mode (one confirm re-saves it) or
"CO-POLICY - PLANCODE - mm/dd/yyyy " otherwise.
"""
import os
from datetime import date, datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QAbstractItemView, QApplication, QMessageBox

from suiteview.illustration.models import case_store
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
)
from suiteview.illustration.ui.case_controls import (
    copy_case_default_name,
    default_case_name,
)
from suiteview.illustration.ui.main_window import IllustrationWindow
from suiteview.illustration.ui.saved_cases_panel import (
    format_saved_date,
    format_saved_stamp,
)
from suiteview.illustration.ui.styles import (
    ILLUSTRATION_HEADER_COLORS,
    ILLUSTRATION_SNAPSHOT_HEADER_COLORS,
)

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


# ── stubs (session-state test pattern) ───────────────────────────────


class _StubPolicy:
    available_companies: list = []
    exists = True
    system_code = "I"

    def __init__(self, policy_number, company_code="01", **_kwargs):
        self.policy_number = policy_number
        self.company_code = company_code or "01"
        self.policy_id = f"{policy_number}  QXXX"
        self.status_description = "Active"
        self.status_code = "0"
        self.issue_date = date(2010, 5, 15)
        self.base_issue_age = 40
        self.valuation_date = date(2026, 6, 15)
        self.maturity_age = 121
        self.attained_age = 56
        self.policy_year = 17
        self.policy_month = 1
        self.billing_frequency = 1
        self.modal_premium = 100.0
        self.base_plancode = ""
        self.total_loan_balance = 0


class _StubDB:
    def __init__(self, region):
        self.region = region

    def connect(self):
        pass

    def close(self):
        pass


class _CountingPolicyFactory:
    """PolicyInformation stand-in that counts constructions (DB2 loads)."""

    def __init__(self):
        self.calls = 0

    def __call__(self, policy_number, company_code=None, system_code="I",
                 region="CKPR"):
        self.calls += 1
        return _StubPolicy(policy_number, company_code)


class _RecordingMsgBox:
    StandardButton = QMessageBox.StandardButton
    questions: list = []
    warnings: list = []
    infos: list = []
    criticals: list = []
    answer = QMessageBox.StandardButton.Yes

    @classmethod
    def reset(cls):
        cls.questions, cls.warnings, cls.infos, cls.criticals = [], [], [], []
        cls.answer = QMessageBox.StandardButton.Yes

    @classmethod
    def question(cls, parent, title, text, *args, **kwargs):
        cls.questions.append(text)
        return cls.answer

    @classmethod
    def warning(cls, parent, title, text, *args, **kwargs):
        cls.warnings.append(text)

    @classmethod
    def information(cls, parent, title, text, *args, **kwargs):
        cls.infos.append(text)

    @classmethod
    def critical(cls, parent, title, text, *args, **kwargs):
        cls.criticals.append(text)


def _make_window(monkeypatch, tmp_path, illustration_data=None):
    _app()
    # All store reads/writes (panel, controller, window) land in the tmp
    # folder — never the user's real ~/.suiteview/illustration_cases.
    monkeypatch.setattr(case_store, "default_cases_dir", lambda: tmp_path)
    factory = _CountingPolicyFactory()
    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.PolicyInformation", factory)
    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.DB2Connection", _StubDB)
    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.QMessageBox", _RecordingMsgBox)
    monkeypatch.setattr(
        "suiteview.illustration.ui.case_controls.QMessageBox", _RecordingMsgBox)
    _RecordingMsgBox.reset()

    def _fake_checks(self, policy_number, region, company_code):
        self._illustration_data = illustration_data
        return [], None

    monkeypatch.setattr(IllustrationWindow, "_policy_load_checks", _fake_checks)
    window = IllustrationWindow()
    window.policy_tab.load_data_from_policy = lambda *a, **kw: None
    window.policy_tab.set_rate_warnings = lambda *a, **kw: None
    return window, factory


def _snapshot(policy_number="POLA", form="ULFRM19") -> IllustrationPolicyData:
    return IllustrationPolicyData(
        policy_number=policy_number, region="CKPR", company_code="01",
        plancode="", form_number=form,
        issue_date=date(2019, 11, 9), issue_age=50, attained_age=56,
        rate_sex="F", rate_class="N",
        face_amount=250000.0, db_option="A",
        modal_premium=310.25, billing_frequency=1,
        current_interest_rate=0.045,
        policy_year=7, valuation_date=date(2026, 6, 9), maturity_age=121,
        segments=[CoverageSegment(
            coverage_phase=1, issue_date=date(2019, 11, 9), issue_age=50,
            face_amount=250000.0, maturity_date=date(2090, 11, 9))],
    )


def _case_inputs(marker="1,000") -> dict:
    return {
        "grids": {"unscheduled_premiums": [[0, ["07/09/2027", marker]]]},
        "controls": {"exact_days": True},
        "dynamic": {"sections": {}, "riders": {}},
    }


def _save_case(tmp_path, name, policy="POLA", snapshot=None,
               saved_at=None) -> case_store.SavedCase:
    case = case_store.save_case(
        name, policy_number=policy, region="CKPR", company_code="01",
        inputs=_case_inputs(), policy_snapshot=snapshot, overwrite=True,
        directory=tmp_path)
    if saved_at is not None:
        import json
        data = json.loads(case.path.read_text(encoding="utf-8"))
        data["saved_at"] = saved_at.isoformat(timespec="seconds")
        case.path.write_text(json.dumps(data), encoding="utf-8")
        case = case_store.load_case(name, directory=tmp_path)
    return case


def _case_row(panel, name):
    for i in range(panel.case_tree.topLevelItemCount()):
        item = panel.case_tree.topLevelItem(i)
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data[0] == "case" and data[1] == name:
            return item
    return None


def _visible_names(panel):
    names = []
    for i in range(panel.case_tree.topLevelItemCount()):
        item = panel.case_tree.topLevelItem(i)
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data[0] == "case" and not item.isHidden():
            names.append(data[1])
    return names


# ── list population ──────────────────────────────────────────────────


def test_cases_listed_flat_two_columns_newest_first(monkeypatch, tmp_path):
    old = _save_case(tmp_path, "Baseline", snapshot=_snapshot(),
                     saved_at=datetime(2026, 6, 1, 9, 5))
    new = _save_case(tmp_path, "What-if B", snapshot=_snapshot(),
                     saved_at=datetime(2026, 7, 2, 15, 30))
    _save_case(tmp_path, "Other", policy="POLB",
               snapshot=_snapshot("POLB", form="ULA19"),
               saved_at=datetime(2026, 6, 15, 9, 0))

    window, _ = _make_window(monkeypatch, tmp_path)
    panel = window.policy_list_window.cases_view

    # Flat list — one row per case, NO policy grouping nodes.
    tree = panel.case_tree
    assert tree.topLevelItemCount() == 3
    assert all(tree.topLevelItem(i).childCount() == 0 for i in range(3))
    assert tree.headerItem().text(0) == "Saved"
    assert tree.headerItem().text(1) == "Case Name"

    # Newest first; column 0 = last-modified date, column 1 = case name.
    assert [tree.topLevelItem(i).text(1) for i in range(3)] == [
        "What-if B", "Other", "Baseline"]
    assert tree.topLevelItem(0).text(0) == "07/02/2026"
    assert tree.topLevelItem(2).text(0) == "06/01/2026"
    assert format_saved_date(new.saved_at) == "07/02/2026"
    assert format_saved_date(old.saved_at) == "06/01/2026"

    # Hover keeps the fuller details: policy identity (now that there is no
    # policy node), time, region, app version, snapshot presence.
    tooltip = tree.topLevelItem(0).toolTip(1)
    assert "Policy: 01 - POLA  [ULFRM19]" in tooltip
    assert f"Saved: {format_saved_stamp(new.saved_at)}" in tooltip
    assert "Saved: 7/2/2026 3:30 PM" in tooltip
    assert "Region: CKPR" in tooltip
    assert "App version:" in tooltip
    assert "frozen at save time" in tooltip
    assert tree.topLevelItem(0).toolTip(0) == tooltip
    window.close()


def test_v1_case_tooltip_flags_missing_snapshot(monkeypatch, tmp_path):
    import json
    path = tmp_path / "legacy.case.json"
    path.write_text(json.dumps({
        "kind": case_store.CASE_KIND, "schema_version": 1, "name": "Legacy",
        "policy_number": "POLA", "region": "CKPR", "company_code": "01",
        "saved_at": "2026-06-01T09:30:00", "app_version": "2.1",
        "inputs": _case_inputs(),
    }), encoding="utf-8")
    window, _ = _make_window(monkeypatch, tmp_path)
    item = _case_row(window.policy_list_window.cases_view, "Legacy")
    assert item is not None
    assert item.text(0) == "06/01/2026"
    assert item.text(1) == "Legacy"
    # Form unknown (no snapshot) → no bracket segment in the tooltip.
    assert "Policy: 01 - POLA" in item.toolTip(1)
    assert "[" not in item.toolTip(1).splitlines()[0]
    assert "No policy snapshot" in item.toolTip(1)
    window.close()


# ── search filtering ─────────────────────────────────────────────────


def test_search_filters_on_case_name_only(monkeypatch, tmp_path):
    # Names carry the policy where the user kept the default prefix; the
    # search must match ONLY what the Case Name column shows — transparent.
    _save_case(tmp_path, "01-POLA - Baseline", policy="POLA",
               snapshot=_snapshot("POLA", form="FPL83"),
               saved_at=datetime(2026, 7, 18, 9, 0))
    _save_case(tmp_path, "What-if B", policy="POLA",
               snapshot=_snapshot("POLA", form="FPL83"),
               saved_at=datetime(2026, 8, 2, 9, 0))
    _save_case(tmp_path, "Other Case", policy="POLB",
               snapshot=_snapshot("POLB", form="ULA19"),
               saved_at=datetime(2026, 7, 18, 9, 0))
    window, _ = _make_window(monkeypatch, tmp_path)
    panel = window.policy_list_window.cases_view

    # Case-name match (case-insensitive substring).
    panel.search_input.setText("baseLINE")
    assert _visible_names(panel) == ["01-POLA - Baseline"]

    # A policy number matches only where it is IN the visible name.
    panel.search_input.setText("pola")
    assert _visible_names(panel) == ["01-POLA - Baseline"]

    # Hidden metadata never matches: not the other cases' policy number...
    panel.search_input.setText("polb")
    assert _visible_names(panel) == []
    # ...not the form number...
    panel.search_input.setText("fpl83")
    assert _visible_names(panel) == []
    # ...and not the Saved-column date.
    panel.search_input.setText("08/02/2026")
    assert _visible_names(panel) == []

    # Clearing the search restores all rows (newest first).
    panel.search_input.setText("")
    assert _visible_names(panel) == [
        "What-if B", "01-POLA - Baseline", "Other Case"]
    window.close()


def test_saved_column_sorts_chronologically_both_ways(monkeypatch, tmp_path):
    # mm/dd/yyyy TEXT would sort month-first (12/31/2025 after 01/05/2026);
    # the Saved column must sort by the real timestamp.
    _save_case(tmp_path, "Old Year", snapshot=_snapshot(),
               saved_at=datetime(2025, 12, 31, 9, 0))
    _save_case(tmp_path, "New Year", snapshot=_snapshot(),
               saved_at=datetime(2026, 1, 5, 9, 0))
    _save_case(tmp_path, "Latest", snapshot=_snapshot(),
               saved_at=datetime(2026, 7, 2, 9, 0))
    window, _ = _make_window(monkeypatch, tmp_path)
    panel = window.policy_list_window.cases_view
    tree = panel.case_tree
    assert tree.isSortingEnabled()

    def _order():
        return [tree.topLevelItem(i).text(1)
                for i in range(tree.topLevelItemCount())]

    # Default: newest first (descending Saved).
    assert _order() == ["Latest", "New Year", "Old Year"]

    tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
    assert _order() == ["Old Year", "New Year", "Latest"]

    tree.sortByColumn(0, Qt.SortOrder.DescendingOrder)
    assert _order() == ["Latest", "New Year", "Old Year"]

    # The chosen order survives a store refresh (rebuild re-sorts).
    tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
    panel.refresh_cases()
    assert _order() == ["Old Year", "New Year", "Latest"]
    window.close()


# ── refresh on save / rename / delete ────────────────────────────────


def test_list_refreshes_on_save_delete_and_rename(monkeypatch, tmp_path):
    window, _ = _make_window(monkeypatch, tmp_path)
    panel = window.policy_list_window.cases_view
    window._on_get_policy("POLA", "CKPR", "01")
    assert panel.case_tree.topLevelItemCount() == 0     # no cases yet

    # Save through the controller (name prompt stubbed) → row appears.
    monkeypatch.setattr(
        "suiteview.illustration.ui.case_controls._name_prompt",
        lambda *a, **kw: "Controller Case")
    window._cases_controller.save_flow()
    item = _case_row(panel, "Controller Case")
    assert item is not None
    assert item.text(1) == "Controller Case"
    assert item.text(0) != ""                            # dated

    # Rename through the panel's context-menu path → row updates.
    monkeypatch.setattr(
        "suiteview.illustration.ui.case_controls._name_prompt",
        lambda *a, **kw: "Renamed Case")
    window._on_case_rename_requested("Controller Case")
    assert _case_row(panel, "Controller Case") is None
    assert _case_row(panel, "Renamed Case") is not None
    assert case_store.load_case("Renamed Case", directory=tmp_path)

    # Delete from the panel's context-menu path → row disappears.
    _RecordingMsgBox.answer = QMessageBox.StandardButton.Yes
    window._on_case_delete_requested("Renamed Case")
    assert panel.case_tree.topLevelItemCount() == 0
    window.close()


# ── context menu ─────────────────────────────────────────────────────


def test_case_context_menu_offers_rename_copy_and_delete(monkeypatch, tmp_path):
    _save_case(tmp_path, "Frozen A", snapshot=_snapshot())
    window, _ = _make_window(monkeypatch, tmp_path)
    panel = window.policy_list_window.cases_view

    # The triggered signals reach the WINDOW's handlers, whose modal
    # surfaces (name-prompt dialogs, delete confirm box) would block a
    # headless test — stub the prompt to "cancel" and answer No.
    monkeypatch.setattr(
        "suiteview.illustration.ui.case_controls._name_prompt",
        lambda *a, **kw: None)
    _RecordingMsgBox.answer = QMessageBox.StandardButton.No

    renames, copies, deletes = [], [], []
    panel.case_rename_requested.connect(renames.append)
    panel.case_copy_requested.connect(copies.append)
    panel.case_delete_requested.connect(deletes.append)

    # _build_case_menu is the construction half of the context menu —
    # _show_context_menu only adds the blocking exec() at the call site.
    menu = panel._build_case_menu("Frozen A")
    labels = [action.text() for action in menu.actions()]
    assert labels == ["Rename Case…", "Copy Case…", "Delete Case…"]
    for action in menu.actions():
        action.trigger()
    assert renames == ["Frozen A"]
    assert copies == ["Frozen A"]
    assert deletes == ["Frozen A"]
    # Cancelled prompts / declined confirm → the case is untouched, alone.
    assert case_store.load_case("Frozen A", directory=tmp_path)
    assert len(case_store.list_cases(directory=tmp_path)) == 1
    window.close()


# ── multi-select batch delete ────────────────────────────────────────


def test_case_tree_uses_extended_selection_mode(monkeypatch, tmp_path):
    # Ctrl/Shift-click must be able to select more than one row.
    window, _ = _make_window(monkeypatch, tmp_path)
    panel = window.policy_list_window.cases_view
    assert (panel.case_tree.selectionMode()
            == QAbstractItemView.SelectionMode.ExtendedSelection)
    window.close()


def test_batch_context_menu_offers_delete_all_selected(monkeypatch, tmp_path):
    _save_case(tmp_path, "A", snapshot=_snapshot())
    _save_case(tmp_path, "B", snapshot=_snapshot())
    window, _ = _make_window(monkeypatch, tmp_path)
    panel = window.policy_list_window.cases_view

    batches = []
    panel.cases_delete_requested.connect(batches.append)

    # _build_batch_menu is the construction half of the multi-select context
    # menu — mirrors _build_case_menu's split for testability.
    menu = panel._build_batch_menu(["A", "B"])
    labels = [action.text() for action in menu.actions()]
    assert labels == ["Delete 2 Cases…"]
    menu.actions()[0].trigger()
    assert batches == [["A", "B"]]
    window.close()


def test_delete_key_deletes_all_selected_cases(monkeypatch, tmp_path):
    _save_case(tmp_path, "A", snapshot=_snapshot())
    _save_case(tmp_path, "B", snapshot=_snapshot())
    _save_case(tmp_path, "C", snapshot=_snapshot())
    window, _ = _make_window(monkeypatch, tmp_path)
    panel = window.policy_list_window.cases_view
    _RecordingMsgBox.reset()
    _RecordingMsgBox.answer = QMessageBox.StandardButton.Yes

    _case_row(panel, "A").setSelected(True)
    _case_row(panel, "C").setSelected(True)

    QTest.keyClick(panel.case_tree, Qt.Key.Key_Delete)

    # One confirmation for the whole batch, naming both selected cases.
    assert len(_RecordingMsgBox.questions) == 1
    prompt = _RecordingMsgBox.questions[0]
    assert "Delete 2 saved cases?" in prompt
    assert "A" in prompt and "C" in prompt

    # Both selected cases gone through the existing store delete function;
    # the untouched one remains — list refreshed, selection cleared.
    remaining = case_store.list_cases(directory=tmp_path)
    assert [c.name for c in remaining] == ["B"]
    assert panel.case_tree.topLevelItemCount() == 1
    assert panel.case_tree.selectedItems() == []
    window.close()


def test_delete_key_with_no_selection_does_nothing(monkeypatch, tmp_path):
    _save_case(tmp_path, "A", snapshot=_snapshot())
    window, _ = _make_window(monkeypatch, tmp_path)
    panel = window.policy_list_window.cases_view
    panel.case_tree.clearSelection()
    _RecordingMsgBox.reset()

    QTest.keyClick(panel.case_tree, Qt.Key.Key_Delete)

    assert _RecordingMsgBox.questions == []
    assert len(case_store.list_cases(directory=tmp_path)) == 1
    window.close()


def test_batch_delete_declined_confirmation_deletes_nothing(monkeypatch, tmp_path):
    _save_case(tmp_path, "A", snapshot=_snapshot())
    _save_case(tmp_path, "B", snapshot=_snapshot())
    window, _ = _make_window(monkeypatch, tmp_path)
    _RecordingMsgBox.reset()
    _RecordingMsgBox.answer = QMessageBox.StandardButton.No

    window._on_cases_delete_requested(["A", "B"])

    assert len(_RecordingMsgBox.questions) == 1
    assert len(case_store.list_cases(directory=tmp_path)) == 2
    window.close()


def test_batch_delete_confirmation_omits_names_beyond_five(monkeypatch, tmp_path):
    names = [f"Case{i}" for i in range(6)]
    for name in names:
        _save_case(tmp_path, name, snapshot=_snapshot())
    window, _ = _make_window(monkeypatch, tmp_path)
    _RecordingMsgBox.reset()
    _RecordingMsgBox.answer = QMessageBox.StandardButton.Yes

    window._on_cases_delete_requested(names)

    assert len(_RecordingMsgBox.questions) == 1
    prompt = _RecordingMsgBox.questions[0]
    assert "Delete 6 saved cases?" in prompt
    assert "Case0" not in prompt          # too many to list — count only
    assert case_store.list_cases(directory=tmp_path) == []
    window.close()


def test_batch_handler_with_single_name_falls_back_to_singular_confirmation(
        monkeypatch, tmp_path):
    _save_case(tmp_path, "A", snapshot=_snapshot())
    window, _ = _make_window(monkeypatch, tmp_path)
    _RecordingMsgBox.reset()
    _RecordingMsgBox.answer = QMessageBox.StandardButton.Yes

    window._on_cases_delete_requested(["A"])

    assert _RecordingMsgBox.questions == ["Delete saved case 'A'?"]
    assert case_store.list_cases(directory=tmp_path) == []
    window.close()


# ── case activation: frozen snapshot restore ─────────────────────────


def test_case_row_restores_frozen_snapshot_without_db2(monkeypatch, tmp_path):
    snapshot = _snapshot("POLA", form="ULFRM19")
    _save_case(tmp_path, "Frozen A", snapshot=snapshot,
               saved_at=datetime(2026, 6, 9, 14, 45))
    window, factory = _make_window(monkeypatch, tmp_path)
    assert window.policy_tab.snapshot_notice() is None

    window._on_case_selected_from_list("Frozen A")

    # No DB2 round trip.
    assert factory.calls == 0
    assert window._snapshot_case is not None
    assert window._snapshot_case.name == "Frozen A"
    assert window._current_key == ("POLA", "CKPR", "01")
    assert window._illustration_data == snapshot
    assert window.run_values_btn.isEnabled()
    assert window.save_case_btn.isEnabled()
    # Case inputs applied through the normal apply path.
    assert window.inputs_tab.unscheduled_premium_table.item(0, 1).text() == "1,000"
    assert window.inputs_tab.exact_days_check.isChecked()
    # Snapshot mode wears its state in the TITLE BAR: case name in the
    # window title, lighter header gradient. The big policy header line is
    # plain (no case suffix).
    assert window.lookup_bar.policy_label.text() == "CKPR - 01 - POLA"
    assert window._title_label.text() == (
        "SuiteView:  Illustration — Case “Frozen A”")
    assert window._header_colors == ILLUSTRATION_SNAPSHOT_HEADER_COLORS
    # As-of detail stays on the inputs strip; the Policy tab is populated from
    # the frozen snapshot (not greyed out) and wears a red 'not retrieved live'
    # statement carrying the same as-of stamp.
    assert window.inputs_tab.snapshot_banner.isVisibleTo(window.inputs_tab)
    assert "as of 6/9/2026 2:45 PM" in window.inputs_tab.snapshot_banner.text()
    assert window.policy_tab.snapshot_notice() is None
    banner = window.policy_tab.snapshot_banner_text()
    assert banner is not None and "was not retrieved live" in banner
    assert "6/9/2026 2:45 PM" in banner
    # Snapshot fields actually rendered into the tab.
    assert window.policy_tab.policy_info.get_value("policy_label") == "POLA"
    assert window.policy_tab.policy_info.get_value("att_age_label") == "56"
    assert "warning" not in window._status_label.text()

    # Getting the policy fresh clears every as-of surface — including the
    # title bar (standard title + standard gradient).
    window._on_get_policy("POLA", "CKPR", "01")
    assert factory.calls == 1
    assert window._snapshot_case is None
    assert window.policy_tab.snapshot_notice() is None
    assert window.policy_tab.snapshot_banner_text() is None
    assert not window.inputs_tab.snapshot_banner.isVisibleTo(window.inputs_tab)
    assert window._title_label.text() == "SuiteView:  Illustration"
    assert window._header_colors == ILLUSTRATION_HEADER_COLORS
    window.close()


def test_snapshot_case_context_bar_shows_frozen_policy_debt(monkeypatch, tmp_path):
    # The inputs context bar's Policy Debt reads the snapshot's six loan
    # buckets (principal + accrued across regular/preferred/variable) — the
    # frozen figure, no DB2.
    snapshot = _snapshot("POLA")
    snapshot.regular_loan_principal = 1_000.0
    snapshot.regular_loan_accrued = 50.0
    snapshot.preferred_loan_principal = 200.0
    snapshot.preferred_loan_accrued = 10.0
    snapshot.variable_loan_principal = 300.0
    snapshot.variable_loan_accrued = 5.75
    assert snapshot.total_loan_balance == 1_565.75
    _save_case(tmp_path, "Debt Case", snapshot=snapshot)
    window, factory = _make_window(monkeypatch, tmp_path)

    window._on_case_selected_from_list("Debt Case")

    assert factory.calls == 0                       # frozen — no live load
    assert window.inputs_tab.banner_policy_debt_label.text() == "1,566"
    window.close()


def test_snapshot_case_context_bar_debt_zero_when_loan_free(monkeypatch, tmp_path):
    # No debt shows as "0" — the field never hides.
    _save_case(tmp_path, "Clean Case", snapshot=_snapshot("POLA"))
    window, _ = _make_window(monkeypatch, tmp_path)

    window._on_case_selected_from_list("Clean Case")

    assert window.inputs_tab.banner_policy_debt_label.text() == "0"
    window.close()


def test_run_values_in_snapshot_mode_projects_frozen_data(monkeypatch, tmp_path):
    snapshot = _snapshot("POLA")
    _save_case(tmp_path, "Frozen A", snapshot=snapshot)
    window, _ = _make_window(monkeypatch, tmp_path)
    window._on_case_selected_from_list("Frozen A")

    def _db2_bomb(*args, **kwargs):
        raise AssertionError(
            "build_illustration_data must not run for a snapshot case")

    captured = {}

    class _StopRun(Exception):
        pass

    def _capture_scenario(policy_data, **kwargs):
        captured["policy"] = policy_data
        raise _StopRun("stop after policy resolution")

    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.build_illustration_data",
        _db2_bomb)
    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.build_illustration_scenario",
        _capture_scenario)
    window._on_run_values()

    assert captured["policy"] == snapshot            # the frozen data ran
    assert captured["policy"] is not snapshot        # on a defensive copy
    window.close()


def test_v1_case_falls_back_to_live_load_with_note(monkeypatch, tmp_path):
    import json
    path = tmp_path / "legacy.case.json"
    path.write_text(json.dumps({
        "kind": case_store.CASE_KIND, "schema_version": 1, "name": "Legacy",
        "policy_number": "POLA", "region": "CKPR", "company_code": "01",
        "saved_at": "2026-06-01T09:30:00", "app_version": "2.1",
        "inputs": _case_inputs("5,000"),
    }), encoding="utf-8")
    window, factory = _make_window(monkeypatch, tmp_path)

    window._on_case_selected_from_list("Legacy")

    # A v1 case has no snapshot → live load happened, inputs applied.
    assert factory.calls == 1
    assert window._snapshot_case is None
    assert window._current_key == ("POLA", "CKPR", "01")
    assert window.inputs_tab.unscheduled_premium_table.item(0, 1).text() == "5,000"
    # The visible note says the case predates snapshots / runs on current data.
    banner = window.inputs_tab.snapshot_banner
    assert banner.isVisibleTo(window.inputs_tab)
    assert "before policy snapshots" in banner.text()
    assert "CURRENT" in banner.text()
    assert "predates snapshots" in window._status_label.text()
    window.close()


def test_clicking_a_case_row_emits_case_selected(monkeypatch, tmp_path):
    _save_case(tmp_path, "Frozen A", snapshot=_snapshot())
    window, _ = _make_window(monkeypatch, tmp_path)
    panel = window.policy_list_window.cases_view
    item = _case_row(panel, "Frozen A")

    received = []
    panel.case_selected.connect(received.append)
    panel._on_tree_item_clicked(item, 0)
    panel._click_timer.stop()               # don't wait 220ms in a test
    panel._emit_pending_activation()
    assert received == ["Frozen A"]

    # Double-click activates too (single emission — the timer is cancelled).
    panel._on_tree_item_clicked(item, 0)
    panel._on_tree_item_double_clicked(item, 0)
    assert received == ["Frozen A", "Frozen A"]
    assert not panel._click_timer.isActive()
    window.close()


# ── Save button (lookup bar, next to Run Values) ─────────────────────


def test_save_button_disabled_until_policy_loads(monkeypatch, tmp_path):
    window, _ = _make_window(monkeypatch, tmp_path)
    assert not window.save_case_btn.isEnabled()
    window._on_get_policy("POLA", "CKPR", "01")
    assert window.save_case_btn.isEnabled()
    window.close()


def test_default_case_name_builds_full_identity_prefix():
    when = date(2026, 7, 19)
    # "CO-POLICY - PLANCODE - mm/dd/yyyy " — no form number, trailing space
    # so the user just types their suffix.
    assert (default_case_name("POLA", "1U1F4M00", "01", when=when)
            == "01-POLA - 1U1F4M00 - 07/19/2026 ")
    # Unknown segments drop out cleanly (no dangling separators).
    assert (default_case_name("POLA", "", "", when=when)
            == "POLA - 07/19/2026 ")
    assert (default_case_name("POLA", "1U144600", when=when)
            == "POLA - 1U144600 - 07/19/2026 ")


def test_save_button_prefills_full_identity_for_live_policy(monkeypatch, tmp_path):
    live_data = _snapshot("POLA", form="ULFRM19")
    live_data.plancode = "1U1F4M00"
    window, _ = _make_window(monkeypatch, tmp_path, illustration_data=live_data)
    window._on_get_policy("POLA", "CKPR", "01")

    prompts = []
    monkeypatch.setattr(
        "suiteview.illustration.ui.case_controls._name_prompt",
        lambda parent, title, initial: prompts.append((title, initial)) or None)
    window.save_case_btn.click()
    # Fresh-save pre-fill carries company, policy, plancode, and today's
    # date (no form number); the user appends whatever else they want.
    expected = default_case_name("POLA", "1U1F4M00", "01")
    assert prompts == [("Save Case", expected)]
    assert prompts[0][1].startswith("01-POLA - 1U1F4M00 - ")
    assert prompts[0][1].endswith(" ")
    # Cancelled prompt → nothing saved.
    assert case_store.list_cases(directory=tmp_path) == []
    window.close()


def test_save_button_saves_named_case_with_snapshot(monkeypatch, tmp_path):
    live_data = _snapshot("POLA", form="LIVEFORM")
    window, _ = _make_window(monkeypatch, tmp_path,
                             illustration_data=live_data)
    window._on_get_policy("POLA", "CKPR", "01")
    monkeypatch.setattr(
        "suiteview.illustration.ui.case_controls._name_prompt",
        lambda *a, **kw: "Button Case")
    window.save_case_btn.click()

    saved = case_store.load_case("Button Case", directory=tmp_path)
    assert saved.policy_number == "POLA"
    assert saved.policy_snapshot == live_data       # frozen at save time
    assert "Saved case 'Button Case'" in window._status_label.text()
    # The Saved Cases panel refreshed.
    assert _case_row(window.policy_list_window.cases_view,
                     "Button Case") is not None
    window.close()


def test_save_button_prefills_loaded_case_and_resaves_without_question(
        monkeypatch, tmp_path):
    _save_case(tmp_path, "Frozen A", snapshot=_snapshot(),
               saved_at=datetime(2026, 6, 9, 14, 45))
    window, _ = _make_window(monkeypatch, tmp_path)
    window._on_case_selected_from_list("Frozen A")

    prompts = []

    def _prompt(parent, title, initial):
        prompts.append(initial)
        return initial                           # one confirm — accept as-is

    monkeypatch.setattr(
        "suiteview.illustration.ui.case_controls._name_prompt", _prompt)
    _RecordingMsgBox.reset()
    window.save_case_btn.click()

    # Pre-filled with the loaded case's name, no second "overwrite?" question.
    assert prompts == ["Frozen A"]
    assert _RecordingMsgBox.questions == []
    resaved = case_store.load_case("Frozen A", directory=tmp_path)
    assert resaved.saved_at > datetime(2026, 6, 9, 14, 45)
    assert "Saved case 'Frozen A'" in window._status_label.text()
    window.close()


def test_save_button_still_questions_before_overwriting_another_case(
        monkeypatch, tmp_path):
    _save_case(tmp_path, "Existing", policy="POLB", snapshot=_snapshot("POLB"))
    window, _ = _make_window(monkeypatch, tmp_path)
    window._on_get_policy("POLA", "CKPR", "01")

    monkeypatch.setattr(
        "suiteview.illustration.ui.case_controls._name_prompt",
        lambda *a, **kw: "Existing")
    _RecordingMsgBox.reset()
    _RecordingMsgBox.answer = QMessageBox.StandardButton.No
    window.save_case_btn.click()
    assert len(_RecordingMsgBox.questions) == 1
    assert "Overwrite" in _RecordingMsgBox.questions[0]
    # Declined → untouched.
    assert case_store.load_case("Existing", directory=tmp_path).policy_number == "POLB"

    _RecordingMsgBox.reset()
    _RecordingMsgBox.answer = QMessageBox.StandardButton.Yes
    window.save_case_btn.click()
    assert case_store.load_case("Existing", directory=tmp_path).policy_number == "POLA"
    window.close()


def test_rename_of_loaded_case_updates_save_prefill_and_header(
        monkeypatch, tmp_path):
    _save_case(tmp_path, "Frozen A", snapshot=_snapshot())
    window, _ = _make_window(monkeypatch, tmp_path)
    window._on_case_selected_from_list("Frozen A")

    monkeypatch.setattr(
        "suiteview.illustration.ui.case_controls._name_prompt",
        lambda *a, **kw: "Frozen A2")
    window._on_case_rename_requested("Frozen A")
    assert window._snapshot_case.name == "Frozen A2"
    # The rename follows through to the window title (where the case name
    # lives in snapshot mode); the policy header line stays plain.
    assert "Frozen A2" in window._title_label.text()
    assert window.lookup_bar.policy_label.text() == "CKPR - 01 - POLA"

    prompts = []
    monkeypatch.setattr(
        "suiteview.illustration.ui.case_controls._name_prompt",
        lambda parent, title, initial: prompts.append(initial) or None)
    window.save_case_btn.click()
    assert prompts == ["Frozen A2"]
    window.close()


# ── Copy Case ────────────────────────────────────────────────────────


def test_copy_case_default_name_restamps_date():
    when = date(2026, 7, 19)
    # A date in the source name is replaced with the current date.
    assert (copy_case_default_name("01-POLA - FPL83 - 06/01/2026 lapse test",
                                   when=when)
            == "01-POLA - FPL83 - 07/19/2026 lapse test")
    # No date → today's date is appended.
    assert copy_case_default_name("Baseline", when=when) == \
        "Baseline - 07/19/2026"
    # Copying a same-day case would collide with its source — disambiguate.
    assert copy_case_default_name("Base 07/19/2026", when=when) == \
        "Base 07/19/2026 (copy)"


def test_copy_flow_duplicates_case_with_fresh_stamp(monkeypatch, tmp_path):
    snapshot = _snapshot("POLA", form="FPL83")
    _save_case(tmp_path, "01-POLA - 06/01/2026 base", snapshot=snapshot,
               saved_at=datetime(2026, 6, 1, 9, 0))
    window, _ = _make_window(monkeypatch, tmp_path)
    panel = window.policy_list_window.cases_view

    prompts = []

    def _prompt(parent, title, initial):
        prompts.append((title, initial))
        return initial + "what-if"               # user appends their suffix

    monkeypatch.setattr(
        "suiteview.illustration.ui.case_controls._name_prompt", _prompt)
    window._on_case_copy_requested("01-POLA - 06/01/2026 base")

    # Prompt pre-filled with the source name re-stamped to today.
    today = copy_case_default_name("01-POLA - 06/01/2026 base")
    assert prompts == [("Copy Case", today)]

    copied = case_store.load_case(today + "what-if", directory=tmp_path)
    original = case_store.load_case("01-POLA - 06/01/2026 base",
                                    directory=tmp_path)
    # Inputs and frozen snapshot ride through; saved_at is fresh.
    assert copied.inputs == original.inputs
    assert copied.policy_snapshot == snapshot
    assert copied.saved_at > original.saved_at
    assert original.saved_at == datetime(2026, 6, 1, 9, 0)   # untouched
    assert "Copied case" in window._status_label.text()
    # Both rows now in the refreshed panel.
    assert panel.case_tree.topLevelItemCount() == 2
    assert _case_row(panel, today + "what-if") is not None
    window.close()


def test_copy_flow_cancelled_prompt_copies_nothing(monkeypatch, tmp_path):
    _save_case(tmp_path, "Frozen A", snapshot=_snapshot())
    window, _ = _make_window(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "suiteview.illustration.ui.case_controls._name_prompt",
        lambda *a, **kw: None)
    window._on_case_copy_requested("Frozen A")
    assert len(case_store.list_cases(directory=tmp_path)) == 1
    window.close()


def test_copy_flow_refuses_source_name_and_questions_overwrite(
        monkeypatch, tmp_path):
    _save_case(tmp_path, "Frozen A", snapshot=_snapshot())
    _save_case(tmp_path, "Frozen B", policy="POLB",
               snapshot=_snapshot("POLB"))
    window, _ = _make_window(monkeypatch, tmp_path)

    # Naming the copy after its source is refused (no self-overwrite).
    monkeypatch.setattr(
        "suiteview.illustration.ui.case_controls._name_prompt",
        lambda *a, **kw: "Frozen A")
    _RecordingMsgBox.reset()
    window._on_case_copy_requested("Frozen A")
    assert any("different from the source" in w
               for w in _RecordingMsgBox.warnings)
    assert len(case_store.list_cases(directory=tmp_path)) == 2

    # Naming it after ANOTHER existing case asks before overwriting.
    monkeypatch.setattr(
        "suiteview.illustration.ui.case_controls._name_prompt",
        lambda *a, **kw: "Frozen B")
    _RecordingMsgBox.reset()
    _RecordingMsgBox.answer = QMessageBox.StandardButton.No
    window._on_case_copy_requested("Frozen A")
    assert len(_RecordingMsgBox.questions) == 1
    assert "Overwrite" in _RecordingMsgBox.questions[0]
    assert case_store.load_case(
        "Frozen B", directory=tmp_path).policy_number == "POLB"

    _RecordingMsgBox.reset()
    _RecordingMsgBox.answer = QMessageBox.StandardButton.Yes
    window._on_case_copy_requested("Frozen A")
    assert case_store.load_case(
        "Frozen B", directory=tmp_path).policy_number == "POLA"
    window.close()
