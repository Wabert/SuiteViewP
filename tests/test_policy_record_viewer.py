"""Policy-backed tab availability and native terminal-value copying."""

import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QTextBrowser

from suiteview.polview.config.policy_records import POLICY_RECORD_TABLES
from suiteview.polview.ui import policy_record_viewer as viewer
from suiteview.polview.models import policy_record_builder as builder


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


class Policy:
    policy_number = "TEST123"
    region = "CKPR"
    company_name = "ANICO"
    exists = True
    last_error = ""

    def __init__(self, tables=None, errors=None):
        self.tables = tables or {}
        self.errors = errors or {}
        self.identity = self

    def fetch_table(self, table):
        return self.tables.get(table, [])

    def table_error(self, table):
        return self.errors.get(table, "")


@pytest.mark.parametrize("segment", viewer._SEGMENTS)
def test_absent_segments_never_render_samples(segment):
    assert viewer.build_screen(segment, Policy()) is None
    assert viewer.build_screen(segment, None) is None


@pytest.mark.parametrize("segment,table", [
    ("56", "LH_GEN_FND_RLE"), ("56", "LH_MKT_VAL_ADJ_RLE"),
    ("03", "LH_SST_XTR_CRG"), ("75", "LH_POL_MVRY_VAL"),
])
def test_present_but_unbuilt_records_are_omitted(segment, table, monkeypatch):
    monkeypatch.setattr(builder, "build_segment_lines", lambda *args: None)
    assert viewer.build_screen(segment, Policy({table: [{"value": 0}]})) is None


def test_secondary_only_segment56_is_omitted_not_a_sample():
    assert viewer.build_screen("56", Policy({"LH_MKT_VAL_ADJ_RLE": [{"value": 0}]})) is None


def test_segments_without_a_screen_do_not_query_unimplemented_tables():
    class UnimplementedPolicy(Policy):
        def fetch_table(self, table):
            pytest.fail(f"Unimplemented screen queried {table}")

    assert viewer.build_screen("03", UnimplementedPolicy()) is None


@pytest.mark.parametrize("has_rows", [False, True])
def test_db_error_is_not_assumed_absent_or_replaced_with_sample(has_rows):
    rows = {"LH_GEN_FND_RLE": [{"value": 0}]} if has_rows else {}
    screen = viewer.build_screen(
        "56", Policy(rows, {"LH_MKT_VAL_ADJ_RLE": "SELECT denied"}),
    )
    assert "SELECT denied" in screen["live_error"]
    assert not screen.get("live")
    assert screen["lines"] == []


def test_builder_errors_have_no_reference_contents(monkeypatch):
    def fail(*args):
        raise ValueError("Unverified fund variant")

    monkeypatch.setattr(builder, "build_segment_lines", fail)
    screen = viewer.build_screen("56", Policy({"LH_GEN_FND_RLE": [{"value": 0}]}))
    assert "Unverified fund variant" in screen["live_error"]
    assert screen["lines"] == []
    assert screen["layout_html"] == ""


def test_supported_live_screen_keeps_layout_and_does_not_mutate_template(monkeypatch):
    base = {"title": "56", "lines": [[{"text": "SAMPLE", "field": "Value"}]],
            "fields": {"Value": ["DB2: VERIFIED"]}, "layout_html": "<p>Layout</p>"}
    original = deepcopy(base)
    monkeypatch.setattr(viewer, "load_screen", lambda segment: base)
    monkeypatch.setattr(builder, "build_segment_lines",
                        lambda *args: [[{"text": "0", "field": "Value"}]])
    screen = viewer.build_screen("56", Policy({"LH_GEN_FND_RLE": [{"value": 0}]}))
    assert screen["live"]
    assert screen["lines"][0][0]["text"] == "0"
    assert screen["layout_html"] == base["layout_html"]
    assert base == original


def test_window_omits_populated_unsupported_segments(app, monkeypatch):
    pi = Policy({"LH_SST_XTR_CRG": [{"value": 0}], "LH_POL_MVRY_VAL": [{"value": 0}]})
    monkeypatch.setattr(viewer.PolicyRecordViewerWindow, "_load_policy", lambda self: pi)
    window = viewer.PolicyRecordViewerWindow(policy_number=pi.identity.policy_number)
    try:
        assert window.tabs.count() == 0
        assert not window.findChildren(viewer._MainframeToken)
        assert not window.findChildren(QTextBrowser)
        assert any("No supported policy record screens" in label.text()
                   for label in window.findChildren(QLabel))
    finally:
        window.close()


def test_window_retains_supported_error_tabs(app, monkeypatch):
    pi = Policy(errors={"LH_MKT_VAL_ADJ_RLE": "SELECT denied"})
    monkeypatch.setattr(viewer.PolicyRecordViewerWindow, "_load_policy", lambda self: pi)
    window = viewer.PolicyRecordViewerWindow(policy_number=pi.identity.policy_number)
    try:
        assert [window.tabs.tabText(index) for index in range(window.tabs.count())] == ["56"]
        tab = window.tabs.widget(0)
        assert not tab.findChildren(viewer._MainframeToken)
        assert not tab.findChildren(QTextBrowser)
        assert any("LIVE DATA ERROR" in label.text() and "SELECT denied" in label.text()
                   for label in tab.findChildren(QLabel))
    finally:
        window.close()


@pytest.mark.parametrize("lookup", ["none", "missing", "error"])
def test_no_loaded_policy_has_no_tabs_or_samples(app, monkeypatch, lookup):
    from suiteview.polview.services import policy_service

    def get_policy(*args):
        if lookup == "error":
            raise RuntimeError("DB2 unavailable")
        return None

    monkeypatch.setattr(policy_service, "get_policy_info", get_policy)
    window = viewer.PolicyRecordViewerWindow(policy_number="" if lookup == "none" else "UNKNOWN")
    try:
        assert window.tabs.count() == 0
        assert not window.findChildren(viewer._MainframeToken)
        if lookup == "error":
            assert "DB2 unavailable" in window._policy_error
        elif lookup == "missing":
            assert "not found" in window._policy_error
    finally:
        window.close()


def test_registered_segments_follow_the_shared_policy_record_mapping():
    assert viewer._SEGMENTS == sorted(
        record.removeprefix("Policy Record ") for record in POLICY_RECORD_TABLES
    )


@pytest.mark.parametrize("value,field,options", [
    ("0", "Value", {}), ("00002194914D", "Value", {}),
    (" ANICO1983  ", "Value", {}), (" ", "Value", {}),
    ("<live>&", "Value", {}), (".000", "Value", {"dim": True}),
    ("00000", "Value", {"example": True}), ("CKPR-ANICO", None, {}),
])
def test_right_click_copy_keeps_exact_plain_value(app, monkeypatch, value, field, options):
    def copy_action(menu, position):
        assert [action.text() for action in menu.actions()] == ["Copy"]
        return menu.actions()[0]

    monkeypatch.setattr(QMenu, "exec", copy_action)
    token = viewer._MainframeToken(value, field, {"Value": ["DB2: SOURCE"]}, **options)
    try:
        app.clipboard().setText("before")
        token.customContextMenuRequested.emit(QPoint(1, 1))
        assert app.clipboard().text() == value
        if field:
            assert "DB2: SOURCE" in token.toolTip()
    finally:
        token.close()


def test_cancelled_copy_preserves_clipboard(app, monkeypatch):
    monkeypatch.setattr(QMenu, "exec", lambda *args: None)
    token = viewer._MainframeToken("123", "Value", {})
    app.clipboard().setText("unchanged")
    token.customContextMenuRequested.emit(QPoint(1, 1))
    assert app.clipboard().text() == "unchanged"
    token.close()


def test_separately_colored_flag_bits_copy_as_a_whole_value(app, monkeypatch):
    monkeypatch.setattr(QMenu, "exec", lambda menu, position: menu.actions()[0])
    terminal = viewer._TerminalScreen({"lines": [[
        {"text": "1", "field": "Flag A"}, {"text": "0", "field": "Flag A"},
        {"text": "000000", "field": "Flag A", "example": True},
        {"text": " ", "field": None}, {"text": "42", "field": "Value"},
    ]]})
    tokens = terminal.findChildren(viewer._MainframeToken)
    for token in tokens[:3]:
        token.customContextMenuRequested.emit(QPoint(1, 1))
        assert app.clipboard().text() == "10000000"
    tokens[-1].customContextMenuRequested.emit(QPoint(1, 1))
    assert app.clipboard().text() == "42"
    terminal.close()
