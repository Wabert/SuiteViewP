"""Merged List side panel — Policies view + single header "List" toggle.

One dockable side window with a Policies | Saved Cases toggle at its top.
This file covers the panel shell (header "List" button show/hide, view
switching with per-view state preserved) and the Policies view: a flat
session history of "REGION | CO | POLICY" rows that grow a trailing
"| <form number>" segment once the policy's data is loaded, with the
region/company/policy inputs + Add on top. The Saved Cases view is covered
in tests/test_illustration_saved_cases_panel.py.
"""
import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from suiteview.illustration.models import case_store
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
)
from suiteview.illustration.ui.main_window import IllustrationWindow

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
    # All store reads/writes land in the tmp folder — never the user's real
    # ~/.suiteview/illustration_cases.
    monkeypatch.setattr(case_store, "default_cases_dir", lambda: tmp_path)
    factory = _CountingPolicyFactory()
    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.PolicyInformation", factory)
    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.DB2Connection", _StubDB)
    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.QMessageBox", _RecordingMsgBox)
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


def _policy_item(panel, policy):
    for i in range(panel.history_tree.topLevelItemCount()):
        item = panel.history_tree.topLevelItem(i)
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data[2] == policy:
            return item
    return None


# ── merged panel shell: header toggle + view switching ───────────────


def test_single_list_button_toggles_merged_panel(monkeypatch, tmp_path):
    window, _ = _make_window(monkeypatch, tmp_path)
    panel = window.policy_list_window
    assert window.list_toggle_btn.text() == "List"
    assert not hasattr(window, "saved_cases_window")   # one panel, not two
    assert panel.isHidden()

    window.list_toggle_btn.click()
    assert window._list_panel_visible
    assert window.list_toggle_btn.isChecked()
    assert not panel.isHidden()

    window.list_toggle_btn.click()
    assert not window._list_panel_visible
    assert not window.list_toggle_btn.isChecked()
    assert panel.isHidden()

    # The panel's own close button unchecks the header toggle.
    window.list_toggle_btn.click()
    panel.on_closed()
    assert not window._list_panel_visible
    assert not window.list_toggle_btn.isChecked()
    assert panel.isHidden()
    window.close()


def test_view_toggle_switches_and_preserves_state(monkeypatch, tmp_path):
    case_store.save_case(
        "Baseline", policy_number="POLA", region="CKPR", company_code="01",
        inputs={"grids": {}, "controls": {}, "dynamic": {}},
        policy_snapshot=_snapshot(), overwrite=True, directory=tmp_path)
    window, _ = _make_window(monkeypatch, tmp_path)
    panel = window.policy_list_window

    # Policies view fronted by default. The toggle buttons live in the
    # panel's HEADER bar (no title label — the checked button is the title).
    assert panel.current_view() == "policies"
    assert panel.policies_view_btn.isChecked()
    assert not panel.cases_view_btn.isChecked()
    assert not hasattr(panel, "_title_label")
    header = panel._header_widget
    assert panel.policies_view_btn in header.findChildren(type(panel.policies_view_btn))
    assert panel.cases_view_btn in header.findChildren(type(panel.cases_view_btn))
    panel.add_policy("CKPR", "01", "POLX")

    # Switch to Saved Cases (header button click drives show_view) — the
    # tree from the store is there.
    panel.cases_view_btn.click()
    assert panel.current_view() == "cases"
    assert panel.cases_view_btn.isChecked()
    assert not panel.policies_view_btn.isChecked()
    assert panel.cases_view.case_tree.topLevelItemCount() == 1

    # Type a search, flip away and back: the search text (and the policy
    # entries) survive the toggle — each view keeps its own live state.
    panel.cases_view.search_input.setText("Base")
    panel.policies_view_btn.click()
    assert panel.current_view() == "policies"
    assert _policy_item(panel, "POLX") is not None
    panel.cases_view_btn.click()
    assert panel.cases_view.search_input.text() == "Base"

    # The last active view sticks across hide/show for the session.
    window.list_toggle_btn.click()
    window.list_toggle_btn.click()
    window.list_toggle_btn.click()
    assert panel.current_view() == "cases"
    window.close()


# ── policies only ────────────────────────────────────────────────────


def test_policy_list_is_policies_only(monkeypatch, tmp_path):
    """Saved cases never appear here — no children, no case-only policies."""
    case_store.save_case(
        "Baseline", policy_number="POLA", region="CKPR", company_code="01",
        inputs={"grids": {}, "controls": {}, "dynamic": {}},
        policy_snapshot=_snapshot(), overwrite=True, directory=tmp_path)

    window, _ = _make_window(monkeypatch, tmp_path)
    panel = window.policy_list_window

    # A policy that only exists as a saved case is NOT in the Policy List
    # (it is browsable in the Saved Cases panel instead).
    assert _policy_item(panel, "POLA") is None

    # A loaded policy appears — with zero case children.
    window._on_get_policy("POLA", "CKPR", "01")
    item = _policy_item(panel, "POLA")
    assert item is not None
    assert item.childCount() == 0
    window.close()


def test_policy_label_gains_form_number_segment(monkeypatch, tmp_path):
    window, _ = _make_window(monkeypatch, tmp_path)
    panel = window.policy_list_window

    # Typed in before any load: no form yet → no trailing pipe segment.
    panel.add_policy("CKPR", "01", "POLX")
    assert _policy_item(panel, "POLX").text(0) == "CKPR | 01 | POLX"

    # Backfilled once the form is known.
    panel.set_policy_form("POLX", "ULFRM19")
    assert _policy_item(panel, "POLX").text(0) == "CKPR | 01 | POLX | ULFRM19"
    window.close()


def test_live_load_backfills_form_number(monkeypatch, tmp_path):
    live_data = _snapshot("POLA", form="LIVEFORM")
    window, _ = _make_window(monkeypatch, tmp_path,
                             illustration_data=live_data)
    window._on_get_policy("POLA", "CKPR", "01")
    item = _policy_item(window.policy_list_window, "POLA")
    assert item.text(0) == "CKPR | 01 | POLA | LIVEFORM"
    window.close()


# ── activation / removal ─────────────────────────────────────────────


def test_click_and_double_click_emit_policy_signals(monkeypatch, tmp_path):
    window, _ = _make_window(monkeypatch, tmp_path)
    panel = window.policy_list_window
    panel.add_policy("CKPR", "01", "POLX")
    item = _policy_item(panel, "POLX")

    selected, opened = [], []
    panel.policy_selected.connect(lambda *a: selected.append(a))
    panel.policy_open_requested.connect(lambda *a: opened.append(a))

    panel._on_tree_item_clicked(item, 0)
    panel._click_timer.stop()               # don't wait 220ms in a test
    panel._emit_pending_policy_selection()
    assert selected == [("CKPR", "01", "POLX")]

    # Double-click cancels the pending single-click and opens.
    panel._on_tree_item_clicked(item, 0)
    panel._on_tree_item_double_clicked(item, 0)
    assert opened == [("CKPR", "01", "POLX")]
    assert selected == [("CKPR", "01", "POLX")]
    assert not panel._click_timer.isActive()
    window.close()


def test_remove_and_clear_evict_history(monkeypatch, tmp_path):
    window, _ = _make_window(monkeypatch, tmp_path)
    panel = window.policy_list_window
    panel.add_policy("CKPR", "01", "POLX")
    panel.add_policy("CKPR", "01", "POLY")

    removed = []
    panel.policy_removed.connect(lambda *a: removed.append(a))
    panel._delete_policy_item(_policy_item(panel, "POLX"))
    assert removed == [("POLX", "CKPR")]
    assert _policy_item(panel, "POLX") is None
    assert _policy_item(panel, "POLY") is not None

    panel._clear_all()
    assert panel.history_tree.topLevelItemCount() == 0
    window.close()
