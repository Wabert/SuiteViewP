"""Whole Life UI regression tests; all parser/database work is isolated."""

from collections import OrderedDict
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox, QVBoxLayout, QWidget

from suiteview.ratemanager.database_loader import TableData, TableSpec
from suiteview.ratemanager.product_chooser import (
    TERM_LINE, UL_LINE, WL_LINE, _ProductCard,
)
from suiteview.ratemanager.ratemanager_window import RateManagerWindow
from suiteview.ratemanager.whole_life import panel as wl

_APP = QApplication.instance() or QApplication([])


def _drain(panel):
    deadline = time.monotonic() + 5
    while panel.is_busy and time.monotonic() < deadline:
        QTest.qWait(10)
    assert not panel.is_busy, "Worker did not finish"
    _APP.processEvents()


@pytest.fixture
def fake_service(monkeypatch):
    monkeypatch.delenv("SUITEVIEW_LIGHT", raising=False)
    calls = []
    failures = {}
    notices = []
    columns = ["UserCode", "Plancode", "Description"]
    spec = TableSpec(
        "WL_RATE_CV", ("UserCode", "SourceKey", "Rate"), ("UserCode", "SourceKey"))
    data = TableData(spec, tuple(("01", f"KEY{i}", i) for i in range(123)))
    second_spec = TableSpec("WL_DIV_HEADER", ("PlanKey",), ("PlanKey",))
    package = SimpleNamespace(
        tables=OrderedDict((
            (spec.name, data),
            (second_spec.name, TableData(second_spec, (("PLAN1",),))),
        )),
        sources=({"path": "cash.txt"},),
        row_counts={spec.name: 123, second_spec.name: 1},
    )
    tables = [
        SimpleNamespace(
            table=spec.name, incoming=123, inserted=120, unchanged=1, changed=2),
        SimpleNamespace(
            table=second_spec.name, incoming=1, inserted=0, unchanged=0, changed=1),
    ]
    analysis = SimpleNamespace(
        package=package, tables=tuple(tables),
        summary_records=lambda: [
            {"Table": table.table, "Incoming": table.incoming,
             "New": table.inserted, "Unchanged": table.unchanged,
             "Changed": table.changed}
            for table in tables
        ],
    )

    def record(operation, *args):
        calls.append((operation, args, threading.get_ident()))
        if operation in failures:
            raise failures[operation]

    class Repository:
        def __init__(self):
            record("open")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            record("close")

        def analyze(self, incoming):
            record("analyze", incoming)
            return analysis

        def apply(self, comparison, replacements):
            record("apply", comparison, replacements)
            return {
                "inserted": {spec.name: 120},
                "updated": {spec.name: 2, second_spec.name: 1},
                "receipt": str(Path(__file__).resolve().parent / "mock_receipt.json"),
            }

        def create_tables(self):
            record("create_tables")
            return (spec.name,)

        def columns(self, table):
            record("columns", table)
            return tuple(columns)

        def browse(self, table, *, filters, limit):
            record("browse", table, filters, limit)
            return [{"UserCode": "01", "Plancode": "PLAN",
                     "Description": "metadata"}]

    def parse(files, code="", *, infer_cvf_negatives=False):
        record("parse", files, code, infer_cvf_negatives)
        return package

    monkeypatch.setattr(wl, "WholeLifeRepository", Repository)
    monkeypatch.setattr(wl, "parse_workup", parse)
    monkeypatch.setattr(
        QMessageBox, "warning",
        lambda parent, title, text: notices.append((title, text)))
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *_args: QMessageBox.StandardButton.Yes)
    return SimpleNamespace(
        calls=calls, failures=failures, notices=notices, package=package,
        analysis=analysis, parse=parse, columns=columns)


@pytest.fixture
def workup(fake_service):
    panel = wl.WholeLifeWorkupPanel()
    yield panel
    _drain(panel)
    panel.close()
    panel.deleteLater()
    _APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    _APP.processEvents()


def _parsed(panel):
    panel.set_paths("CVF", ["cash.txt", "cash2.txt"])
    panel._parse()
    _drain(panel)
    assert panel._package is not None


def _analyzed(panel):
    _parsed(panel)
    panel._analyze()
    _drain(panel)
    assert panel._analysis is not None


def test_three_cards_route_to_separate_pages_without_startup_io(fake_service):
    window = RateManagerWindow()
    try:
        assert window._stack.count() == 8
        assert window._stack.currentWidget() is window.chooser
        cards = window.chooser.findChildren(_ProductCard)
        assert {card._line for card in cards} == {UL_LINE, TERM_LINE, WL_LINE}
        for card in cards:
            window._show_chooser()
            QTest.mouseClick(card, Qt.MouseButton.LeftButton)
            assert window._line == card._line
            expected = {
                UL_LINE: window.workup_panel,
                TERM_LINE: window.term_workup_panel,
                WL_LINE: window.wl_workup_panel,
            }[card._line]
            assert window._stack.currentWidget() is expected
            window._show_database()
            assert window._stack.currentIndex() == window._pages()[1]
            assert window._view_btn.isHidden() == (card._line != UL_LINE)
        assert fake_service.calls == []
    finally:
        window.close()
        window.deleteLater()
        _APP.processEvents()


def test_chooser_cards_fit_minimum_window_width(fake_service):
    window = RateManagerWindow()
    try:
        window.resize(840, 620)
        window.show()
        _APP.processEvents()
        assert window.width() == 840
        cards = window.chooser.findChildren(_ProductCard)
        assert len(cards) == 3
        for card in cards:
            assert card.x() >= 0
            assert card.geometry().right() < window.chooser.width()
            assert card.width() >= card.minimumWidth()
    finally:
        window.close()
        window.deleteLater()
        _APP.processEvents()


def test_parse_previews_first_100_rows_and_reports_full_counts(workup, fake_service):
    _parsed(workup)
    assert workup.preview_tabs.count() == 2
    assert workup.preview_tables["WL_RATE_CV"].table_view.model().rowCount() == 100
    assert workup.preview_tables["WL_DIV_HEADER"].table_view.model().rowCount() == 1
    assert "WL_RATE_CV: 123" in workup.counts_label.text()
    assert workup.analyze_btn.isEnabled()
    assert not workup.load_btn.isEnabled()
    parse_calls = [call for call in fake_service.calls if call[0] == "parse"]
    assert parse_calls[0][1][0]["CVF"] == ["cash.txt", "cash2.txt"]
    assert parse_calls[0][1][2] is False
    assert parse_calls[0][2] != threading.get_ident()
    assert not any(call[0] == "open" for call in fake_service.calls)


def test_cvf_inference_defaults_off_and_requires_cvf_selection(workup, fake_service):
    check = workup.infer_cvf_negatives_check
    assert check.text() == "Infer early negative CVs (assumption)"
    assert not check.isChecked()
    assert not check.isEnabled()
    assert not check.isHidden()
    for rule in (
        "signed negative duration-zero header", "strict initial decline",
        "followed by a rise", "BEFORE the first minimum", "keep the minimum positive",
        "flat or unfinished declines", "never override explicit '+' values",
    ):
        assert rule in check.toolTip()
    workup.set_paths("PUI", ["pui.txt"])
    assert not check.isEnabled()
    workup.set_paths("CVF", ["cash.txt"])
    assert check.isEnabled()
    assert not check.isChecked()
    workup._parse()
    _drain(workup)
    assert fake_service.calls[0][1][2] is False
    assert "CVF inferred rows: 0 (off)" in workup.counts_label.text()


@pytest.mark.parametrize("enabled", [False, True])
def test_cvf_inference_option_is_forwarded_to_parse_worker(workup, fake_service, enabled):
    workup.set_paths("CVF", ["cash.txt"])
    workup.infer_cvf_negatives_check.setChecked(enabled)
    workup._parse()
    _drain(workup)
    parse_call = next(call for call in fake_service.calls if call[0] == "parse")
    assert parse_call[1] == (workup._selected_files(), "", enabled)
    assert parse_call[2] != threading.get_ident()
    assert not any(call[0] == "open" for call in fake_service.calls)


def test_checked_but_disabled_inference_is_ignored_without_cvf(workup, fake_service):
    workup.set_paths("CVF", ["cash.txt"])
    workup.infer_cvf_negatives_check.setChecked(True)
    workup.set_paths("CVF", [])
    workup.set_paths("PUI", ["pui.txt"])
    assert workup.infer_cvf_negatives_check.isChecked()
    assert not workup.infer_cvf_negatives_check.isEnabled()
    workup._parse()
    _drain(workup)
    parse_call = next(call for call in fake_service.calls if call[0] == "parse")
    assert parse_call[1][0]["CVF"] == []
    assert parse_call[1][2] is False
    assert not any(call[0] == "open" for call in fake_service.calls)


@pytest.mark.parametrize("initially_enabled", [False, True])
def test_inference_toggle_invalidates_preview_analysis_and_approvals(
        workup, initially_enabled):
    workup.set_paths("CVF", ["cash.txt"])
    workup.infer_cvf_negatives_check.setChecked(initially_enabled)
    _analyzed(workup)
    for check in workup._approvals.values():
        check.setChecked(True)
    assert workup.load_btn.isEnabled()
    revision = workup._revision
    workup.infer_cvf_negatives_check.setChecked(not initially_enabled)
    assert workup._revision == revision + 1
    assert workup._package is None
    assert workup._analysis is None
    assert not workup._approvals
    assert not workup.preview_tables
    assert workup.preview_tabs.count() == 0
    assert workup.analysis_table.table_view.model().rowCount() == 0
    assert not workup.analyze_btn.isEnabled()
    assert not workup.load_btn.isEnabled()


def _inference_source(path, adjustments):
    return {
        "path": path,
        "cvf_inference": {
            "enabled": True,
            "rule": "negative-header-initial-decline-v1",
            "adjusted_rows": len(adjustments),
            "adjustments": adjustments,
        },
    }


@pytest.mark.parametrize("adjusted_rows", [0, 2, 105])
def test_inference_preview_counts_and_shows_every_exact_adjustment(
        workup, fake_service, adjusted_rows):
    adjustments = [
        {
            "USER_CODE": "06", "RATE_KEY": "CV001", "USER_DEFINED": "  basis  ",
            "ISSUE_AGE": 20 + index, "DURATION": 1, "printed_rate": "12.30",
            "loaded_rate": "0.00", "source_line": 6 + index,
            "minimum_duration": 3, "minimum_rate": "1.20", "header_zero": "-99.50",
        }
        for index in range(adjusted_rows)
    ]
    split = adjusted_rows // 2
    long_path = (
        r"C:\Whole Life rates\Original printouts\Archived source reports"
        r"\Company 06\Verified cash value factor workup inputs\cash.txt"
    )
    fake_service.package.sources = (
        _inference_source(long_path, adjustments[:split]),
        _inference_source("cash2.txt", adjustments[split:]),
    )
    workup.infer_cvf_negatives_check.setChecked(True)
    _parsed(workup)
    assert f"CVF inferred rows: {adjusted_rows:,} (assumption" in workup.counts_label.text()
    assert workup.preview_tabs.count() == (3 if adjusted_rows else 2)
    assert not any(call[0] == "open" for call in fake_service.calls)
    if not adjusted_rows:
        assert "CVF inference" not in workup.preview_tables
        return
    audit = workup.preview_tables["CVF inference"]
    assert isinstance(audit, wl.FilterTableView)
    assert audit.table_view.model().rowCount() == adjusted_rows
    expected = [
        {"Source file": source["path"], **row,
         "Rule": source["cvf_inference"]["rule"]}
        for source in fake_service.package.sources
        for row in source["cvf_inference"]["adjustments"]
    ]
    assert audit.model.get_original_data().to_dict("records") == expected
    columns = list(audit.model.get_original_data().columns)
    assert columns[:8] == [
        "USER_CODE", "RATE_KEY", "ISSUE_AGE", "DURATION", "printed_rate",
        "loaded_rate", "minimum_duration", "minimum_rate",
    ]
    assert columns[8:-2] == ["USER_DEFINED", "source_line", "header_zero"]
    assert columns[-2:] == ["Source file", "Rule"]
    assert audit.model.get_original_data().iloc[0]["Source file"] == long_path
    for field in ("printed_rate", "loaded_rate", "minimum_rate", "header_zero"):
        cell = audit.model.index(0, columns.index(field))
        assert audit.model.data(cell, Qt.ItemDataRole.DisplayRole) == expected[0][field]
    index = workup.preview_tabs.indexOf(audit)
    assert "not limited to 100 rows" in workup.preview_tabs.tabToolTip(index)
    workup.infer_cvf_negatives_check.setChecked(False)
    assert workup.preview_tabs.count() == 0
    assert "CVF inference" not in workup.preview_tables


@pytest.mark.parametrize("enabled", [False, True])
def test_load_confirmation_identifies_cvf_inference_assumption(
        workup, fake_service, monkeypatch, enabled):
    source = _inference_source("cash.txt", [{"loaded_rate": "0.00"}] if enabled else [])
    source["cvf_inference"]["enabled"] = enabled
    fake_service.package.sources = (source,)
    confirmations = []

    def confirm(parent, title, text, *args):
        confirmations.append(text)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", confirm)
    workup.infer_cvf_negatives_check.setChecked(enabled)
    _analyzed(workup)
    for check in workup._approvals.values():
        check.setChecked(True)
    workup._load()
    assert len(confirmations) == 1
    assert ("CVF sign inference is an assumption" in confirmations[0]) == enabled
    if enabled:
        assert "1 inferred row(s) will be loaded as 0.00" in confirmations[0]
        assert "Review the CVF inference audit" in confirmations[0]
    assert not any(call[0] == "apply" for call in fake_service.calls)


def test_inference_is_snapshotted_and_toggle_discards_running_preview(
        workup, fake_service, monkeypatch):
    release = threading.Event()
    received = []

    def blocked_parse(files, code="", *, infer_cvf_negatives=False):
        assert release.wait(5)
        received.append(infer_cvf_negatives)
        return fake_service.package

    monkeypatch.setattr(wl, "parse_workup", blocked_parse)
    try:
        workup.set_paths("CVF", ["cash.txt"])
        workup.infer_cvf_negatives_check.setChecked(True)
        workup._parse()
        assert not workup.infer_cvf_negatives_check.isEnabled()
        workup.infer_cvf_negatives_check.setChecked(False)
    finally:
        release.set()
        _drain(workup)
    assert received == [True]
    assert workup._package is None
    assert workup.preview_tabs.count() == 0
    assert not workup.analyze_btn.isEnabled()
    assert workup.infer_cvf_negatives_check.isEnabled()


def test_inference_control_fits_minimum_workup_window(fake_service):
    window = RateManagerWindow()
    try:
        window.resize(840, 620)
        window._on_line_chosen(WL_LINE)
        window.show()
        _APP.processEvents()
        workup = window.wl_workup_panel
        check = workup.infer_cvf_negatives_check
        assert window.width() == 840
        assert window.height() == 620
        assert check.isVisible()
        assert check.width() >= check.sizeHint().width()
        assert check.geometry().right() < workup.source_controls.width()
        assert check.geometry().right() < workup.user_code_edit.geometry().left()
        assert fake_service.calls == []
    finally:
        window.close()
        window.deleteLater()
        _APP.processEvents()


def test_all_file_types_are_visible_and_parse_as_one_workup(workup, fake_service):
    assert list(workup.source_edits) == [
        "CVF", "IAF", "Dividend", "PUI", "NSP", "Dividend map",
    ]
    for kind in ("CVF", "IAF", "Dividend", "PUI"):
        assert not workup.source_edits[kind].isHidden()
        workup.set_paths(kind, [f"{kind}.txt"])
    workup.user_code_edit.setText("06")
    workup._parse()
    _drain(workup)
    parse_calls = [call for call in fake_service.calls if call[0] == "parse"]
    assert len(parse_calls) == 1
    assert parse_calls[0][1] == ({
        "CVF": ["CVF.txt"], "IAF": ["IAF.txt"], "Dividend": ["Dividend.txt"],
        "PUI": ["PUI.txt"], "NSP": [], "Dividend map": [],
    }, "06", False)
    workup._analyze()
    _drain(workup)
    for check in workup._approvals.values():
        check.setChecked(True)
    workup._load()
    _drain(workup)
    analyses = [call for call in fake_service.calls if call[0] == "analyze"]
    loads = [call for call in fake_service.calls if call[0] == "apply"]
    assert len(analyses) == len(loads) == 1
    assert analyses[0][1][0] is fake_service.package
    assert loads[0][1][0].package is fake_service.package


def test_any_source_can_load_alone_and_only_iaf_needs_company(workup):
    assert not workup.parse_btn.isEnabled()
    assert not workup.user_code_edit.isEnabled()
    workup.set_paths("PUI", ["pui.txt"])
    assert workup.parse_btn.isEnabled()
    workup.set_paths("IAF", ["iaf.txt"])
    assert not workup.parse_btn.isEnabled()
    assert workup.user_code_edit.isEnabled()
    workup.set_paths("IAF", [])
    assert workup.parse_btn.isEnabled()
    assert not workup.user_code_edit.isEnabled()
    assert workup._selected_files()["PUI"] == ["pui.txt"]
    workup.source_edits["PUI"].clear()
    assert not workup.parse_btn.isEnabled()


def test_browsing_one_source_retains_other_file_selections(workup, monkeypatch):
    workup.set_paths("CVF", ["cash.txt"])
    workup.set_paths("Dividend", ["div.txt"])
    monkeypatch.setattr(
        wl.QFileDialog, "getOpenFileNames",
        lambda *args: (["pui.txt", "pui2.txt"], ""),
    )
    QTest.mouseClick(workup.source_buttons["PUI"], Qt.MouseButton.LeftButton)
    assert workup._selected_files()["PUI"] == ["pui.txt", "pui2.txt"]
    assert workup._selected_files()["CVF"] == ["cash.txt"]
    assert workup._selected_files()["Dividend"] == ["div.txt"]
    monkeypatch.setattr(wl.QFileDialog, "getOpenFileNames", lambda *args: ([], ""))
    workup._select_files("CVF")
    assert workup._selected_files()["CVF"] == ["cash.txt"]


def test_path_entry_accepts_quoted_multiple_paths_and_semicolons(workup):
    workup.source_edits["CVF"].setText(
        r' "C:\rates\cash; value.txt" | C:\rates\other.txt | "C:\rates\cash; value.txt" | '
    )
    assert workup._selected_files()["CVF"] == [
        r"C:\rates\cash; value.txt", r"C:\rates\other.txt",
    ]


def test_iaf_requires_explicit_uppercased_company_code(workup, fake_service):
    workup.set_paths("IAF", ["wholelife.iaf"])
    assert workup.user_code_edit.isEnabled()
    assert not workup.parse_btn.isEnabled()
    workup._parse()
    assert not fake_service.calls
    assert fake_service.notices
    workup.user_code_edit.setText("abc")
    assert workup.user_code_edit.text() == "ABC"
    assert workup.parse_btn.isEnabled()
    workup._parse()
    _drain(workup)
    parse_call = next(call for call in fake_service.calls if call[0] == "parse")
    assert parse_call[1] == (workup._selected_files(), "ABC", False)
    assert parse_call[1][0]["IAF"] == ["wholelife.iaf"]


def test_plan_key_map_file_dialog_offers_workbooks(workup, monkeypatch):
    selections = []

    def select_files(parent, title, folder, file_filter):
        selections.append(file_filter)
        return ["map.xlsx", "map2.xlsm"], ""

    monkeypatch.setattr(wl.QFileDialog, "getOpenFileNames", select_files)
    workup._select_files("Dividend map")
    assert "*.xlsx *.xlsm" in selections[0]
    assert workup._selected_files()["Dividend map"] == ["map.xlsx", "map2.xlsm"]


def test_every_changed_table_requires_explicit_approval(workup, fake_service):
    _analyzed(workup)
    assert len(workup._approvals) == 2
    assert not workup.load_btn.isEnabled()
    checks = list(workup._approvals.values())
    checks[0].setChecked(True)
    assert not workup.load_btn.isEnabled()
    checks[1].setChecked(True)
    assert workup.load_btn.isEnabled()
    workup._load()
    assert not workup.source_controls.isEnabled()
    assert not workup.load_btn.isEnabled()
    _drain(workup)
    apply_call = next(call for call in fake_service.calls if call[0] == "apply")
    assert apply_call[1][1] == {"WL_RATE_CV", "WL_DIV_HEADER"}
    assert apply_call[2] != threading.get_ident()
    assert workup._analysis is None
    assert not workup.load_btn.isEnabled()
    assert "120 inserted, 3 updated" in workup.status.text()
    assert "Receipt:" in workup.status.text()
    assert sum(call[0] == "open" for call in fake_service.calls) == 2
    assert sum(call[0] == "close" for call in fake_service.calls) == 2


@pytest.mark.parametrize("has_new_rows", [True, False])
def test_no_changed_rows_need_no_approval_and_unchanged_only_cannot_load(
        workup, fake_service, has_new_rows):
    for table in fake_service.analysis.tables:
        table.changed = 0
        table.inserted = 1 if has_new_rows else 0
    _analyzed(workup)
    assert workup._approvals == {}
    assert workup.load_btn.isEnabled() == has_new_rows
    workup._load()
    _drain(workup)
    assert any(call[0] == "apply" for call in fake_service.calls) == has_new_rows


@pytest.mark.parametrize("change", ["CVF", "IAF", "Dividend", "PUI", "NSP", "Dividend map", "company"])
def test_source_edits_invalidate_package_analysis_and_approvals(
        workup, fake_service, change):
    _analyzed(workup)
    for check in workup._approvals.values():
        check.setChecked(True)
    assert workup.load_btn.isEnabled()
    if change == "company":
        workup.user_code_edit.setText("02")
    else:
        workup.source_edits[change].setText("new.txt")
    assert workup._package is None
    assert workup._analysis is None
    assert not workup._approvals
    assert not workup.load_btn.isEnabled()
    assert not workup.analyze_btn.isEnabled()
    assert workup.preview_tabs.count() == 0


@pytest.mark.parametrize("operation", ["parse", "analyze", "apply"])
def test_errors_are_logged_surfaced_and_block_loading(
        workup, fake_service, caplog, operation):
    _analyzed(workup)
    fake_service.failures[operation] = ValueError(f"bad {operation}")
    if operation == "parse":
        workup._parse()
    elif operation == "analyze":
        workup._analyze()
    else:
        for check in workup._approvals.values():
            check.setChecked(True)
        workup._load()
    _drain(workup)
    assert workup._analysis is None
    assert not workup.load_btn.isEnabled()
    assert f"bad {operation}" in workup.status.text()
    assert f"bad {operation}" in caplog.text
    assert fake_service.notices[-1][1] == f"bad {operation}"
    if operation == "parse":
        assert workup._package is None
    if operation != "parse":
        assert fake_service.calls[-1][0] == "close"


def test_load_and_ddl_require_confirmation(workup, fake_service, monkeypatch):
    _analyzed(workup)
    for check in workup._approvals.values():
        check.setChecked(True)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.No)
    workup._load()
    workup._create_tables()
    assert not workup.is_busy
    assert not any(call[0] in ("apply", "create_tables") for call in fake_service.calls)
    assert workup._analysis is not None


def test_direct_load_without_changed_table_approval_is_blocked(workup, fake_service):
    _analyzed(workup)
    workup._load()
    assert not workup.is_busy
    assert not any(call[0] == "apply" for call in fake_service.calls)
    assert workup._analysis is None
    assert not workup.load_btn.isEnabled()
    assert "Approve changed-row updates" in workup.status.text()


def test_create_tables_only_runs_on_explicit_action(workup, fake_service, monkeypatch):
    confirmations = []

    def confirm(parent, title, text, *args):
        confirmations.append(text)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", confirm)
    assert fake_service.calls == []
    workup._create_tables()
    _drain(workup)
    assert [call[0] for call in fake_service.calls] == [
        "open", "create_tables", "close"]
    assert "Created: WL_RATE_CV" in workup.status.text()
    for table in ("WL_RATE_CV", "WL_RATE_NSP", "WL_RATE_PUI", "WL_RATE_PREM"):
        assert table in confirmations[0]
    assert "plan-key map and CYBERLIFE_PDF are not created or modified" in confirmations[0]


def test_create_table_error_invalidates_previous_comparison(workup, fake_service):
    _analyzed(workup)
    fake_service.failures["create_tables"] = RuntimeError("DDL permission denied")
    workup._create_tables()
    _drain(workup)
    assert workup._analysis is None
    assert not workup.load_btn.isEnabled()
    assert "DDL permission denied" in workup.status.text()
    assert fake_service.calls[-1][0] == "close"


def test_read_only_blocks_write_buttons_and_direct_actions(
        workup, fake_service, monkeypatch):
    monkeypatch.setenv("SUITEVIEW_LIGHT", "1")
    _analyzed(workup)
    for check in workup._approvals.values():
        check.setChecked(True)
    assert workup.analyze_btn.isEnabled()
    assert not workup.load_btn.isEnabled()
    assert not workup.create_btn.isEnabled()
    workup._load()
    workup._create_tables()
    assert not workup.is_busy
    assert not any(call[0] in ("apply", "create_tables") for call in fake_service.calls)
    assert "read-only" in workup.status.text()


def test_running_worker_blocks_parent_close_and_source_controls(
        fake_service, monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def blocked_parse(*args, infer_cvf_negatives=False):
        started.set()
        assert release.wait(5)
        return fake_service.package

    monkeypatch.setattr(wl, "parse_workup", blocked_parse)
    host = QWidget()
    layout = QVBoxLayout(host)
    workup = wl.WholeLifeWorkupPanel()
    layout.addWidget(workup)
    host.show()
    try:
        workup.set_paths("CVF", ["cash.txt"])
        workup._parse()
        assert started.wait(2)
        assert workup.is_busy
        assert not workup.source_controls.isEnabled()
        assert not workup.infer_cvf_negatives_check.isEnabled()
        assert not host.close()
        assert host.isVisible()
        assert not workup.close()
        assert workup._worker is not None
    finally:
        release.set()
        _drain(workup)
        assert workup._worker is None
        assert workup.source_controls.isEnabled()
        assert workup.infer_cvf_negatives_check.isEnabled()
        host.close()
        host.deleteLater()
        _APP.processEvents()


def test_window_navigation_locked_until_worker_teardown(fake_service, monkeypatch):
    release = threading.Event()

    def blocked_parse(*args, infer_cvf_negatives=False):
        assert release.wait(5)
        return fake_service.package

    monkeypatch.setattr(wl, "parse_workup", blocked_parse)
    window = RateManagerWindow()
    workup = window.wl_workup_panel
    try:
        window._on_line_chosen(WL_LINE)
        workup.set_paths("CVF", ["cash.txt"])
        workup._parse()
        assert not window._line_btn.isEnabled()
        assert not window._database_btn.isEnabled()
        window._show_chooser()
        window._show_database()
        assert window._stack.currentWidget() is workup
        assert not window.close()
    finally:
        release.set()
        _drain(workup)
        assert window._line_btn.isEnabled()
        assert window._database_btn.isEnabled()
        window.close()
        window.deleteLater()
        _APP.processEvents()


def test_programmatic_input_change_during_parse_discards_stale_result(
        workup, fake_service, monkeypatch):
    release = threading.Event()

    def blocked_parse(*args, infer_cvf_negatives=False):
        assert release.wait(5)
        return fake_service.package

    monkeypatch.setattr(wl, "parse_workup", blocked_parse)
    try:
        workup.set_paths("CVF", ["cash.txt"])
        workup._parse()
        workup.set_paths("PUI", ["different.txt"])
    finally:
        release.set()
        _drain(workup)
    assert workup._package is None
    assert workup._analysis is None
    assert not workup.load_btn.isEnabled()
    assert workup.preview_tabs.count() == 0


def test_database_pdf_lookup_uses_exact_filters_and_limit(fake_service):
    panel = wl.WholeLifeDatabasePanel()
    try:
        assert fake_service.calls == []
        assert panel.table_combo.findText("CYBERLIFE_PDF") >= 0
        panel.table_combo.setCurrentText("CYBERLIFE_PDF")
        assert fake_service.calls == []
        panel._read_columns()
        _drain(panel)
        panel.filter_fields[0].setCurrentText("UserCode")
        panel.filter_values[0].setText("01")
        panel.filter_fields[1].setCurrentText("Plancode")
        panel.filter_values[1].setText("PLAN' OR 1=1 --")
        panel.limit_spin.setValue(25)
        panel._browse()
        assert not panel.query_controls.isEnabled()
        _drain(panel)
        browse = next(call for call in fake_service.calls if call[0] == "browse")
        assert browse[1] == (
            "CYBERLIFE_PDF", {"UserCode": "01", "Plancode": "PLAN' OR 1=1 --"}, 25)
        assert browse[2] != threading.get_ident()
        assert panel.results.table_view.model().rowCount() == 1
        assert "CYBERLIFE_PDF: 1 row(s)" in panel.status.text()
        panel.filter_values[0].setText("02")
        assert panel.results.table_view.model().rowCount() == 0
        call_count = len(fake_service.calls)
        panel.table_combo.setCurrentIndex(0)
        assert all(not value.text() for value in panel.filter_values)
        assert all(not field.currentData() for field in panel.filter_fields)
        assert len(fake_service.calls) == call_count
        assert not any(call[0] in ("apply", "create_tables") for call in fake_service.calls)
    finally:
        _drain(panel)
        panel.close()
        panel.deleteLater()
        _APP.processEvents()


def test_database_query_errors_clear_old_results(fake_service, caplog):
    panel = wl.WholeLifeDatabasePanel()
    try:
        panel._browse()
        _drain(panel)
        assert panel.results.table_view.model().rowCount() == 1
        fake_service.failures["browse"] = RuntimeError("database unavailable")
        panel._browse()
        _drain(panel)
        assert panel.results.table_view.model().rowCount() == 0
        assert "database unavailable" in panel.status.text()
        assert "database unavailable" in caplog.text
        assert fake_service.calls[-1][0] == "close"
    finally:
        _drain(panel)
        panel.close()
        panel.deleteLater()
        _APP.processEvents()


@pytest.mark.parametrize("column", [
    "UserID", "UserCode", "USER_CODE", "Plancode", "PLANCODE",
    "Sex", "SEX", "Rateclass", "RATECLASS",
    "CV_KEY", "NSP_KEY", "PUI_KEY", "DIV_KEY", "SOURCE_KEY",
])
def test_database_identifier_filters_uppercase_entry_and_normalize_lookup(
        fake_service, column):
    fake_service.columns[:] = [column, "FieldValue"]
    panel = wl.WholeLifeDatabasePanel()
    try:
        panel._set_columns(fake_service.columns)
        value = panel.filter_values[0]
        value.setText("prefilled")
        panel.filter_fields[0].setCurrentText(column)
        assert isinstance(value.validator(), wl.UpperCaseValidator)
        assert value.text() == "PREFILLED"
        value.clear()
        QTest.keyClicks(value, "mixed")
        assert value.text() == "MIXED"
        value.setText("  mixed  ")
        assert value.text() == "  MIXED  "
        panel._browse()
        _drain(panel)
        browse = next(call for call in fake_service.calls if call[0] == "browse")
        assert browse[1][1] == {column: "MIXED"}
    finally:
        _drain(panel)
        panel.close()
        panel.deleteLater()
        _APP.processEvents()


@pytest.mark.parametrize("column", [
    "FieldValue", "Description", "SOURCE_FILE", "USER_DEFINED", "RateBasis", "Units",
])
def test_database_switch_to_nonidentifier_removes_validator_and_preserves_text(
        fake_service, column):
    fake_service.columns[:] = ["UserID", column]
    panel = wl.WholeLifeDatabasePanel()
    try:
        panel._set_columns(fake_service.columns)
        field = panel.filter_fields[0]
        value = panel.filter_values[0]
        field.setCurrentText("UserID")
        assert isinstance(value.validator(), wl.UpperCaseValidator)
        field.setCurrentText(column)
        assert value.validator() is None
        value.setText("  Mixed case value  ")
        panel._browse()
        _drain(panel)
        browse = next(call for call in fake_service.calls if call[0] == "browse")
        assert browse[1][1] == {column: "  Mixed case value  "}
        assert value.text() == "  Mixed case value  "
        panel._table_changed()
        assert value.validator() is None
    finally:
        _drain(panel)
        panel.close()
        panel.deleteLater()
        _APP.processEvents()


def test_database_identifier_read_site_normalizes_even_without_validator(fake_service):
    fake_service.columns[:] = ["UserID"]
    panel = wl.WholeLifeDatabasePanel()
    try:
        panel._set_columns(fake_service.columns)
        panel.filter_fields[0].setCurrentText("UserID")
        value = panel.filter_values[0]
        value.setValidator(None)
        value.setText("  ab  ")
        panel._browse()
        _drain(panel)
        browse = next(call for call in fake_service.calls if call[0] == "browse")
        assert browse[1][1] == {"UserID": "AB"}
    finally:
        _drain(panel)
        panel.close()
        panel.deleteLater()
        _APP.processEvents()
