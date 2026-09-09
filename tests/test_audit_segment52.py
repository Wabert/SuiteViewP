import json
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from suiteview.audit.cyberlife_query import build_cyberlife_sql
from suiteview.audit.segment52_fields import SEGMENT52_FIELDS
from suiteview.audit.tabs.adv_tab import AdvTab
from suiteview.audit.tabs.benefits_tab import BenefitsTab
from suiteview.audit.tabs.coverages_tab import CoveragesTab
from suiteview.audit.tabs.display_tab import DisplayTab
from suiteview.audit.tabs.plancode_tab import PlancodeTab
from suiteview.audit.tabs.policy2_tab import Policy2Tab
from suiteview.audit.tabs.policy_tab import PolicyTab
from suiteview.audit.tabs.segment52_tab import Segment52Tab
from suiteview.audit.tabs.transaction_tab import TransactionTab


@pytest.fixture
def tabs():
    app = QApplication.instance() or QApplication([])
    widgets = dict(
        policy_tab=PolicyTab(), display_tab=DisplayTab(), policy2_tab=Policy2Tab(),
        adv_tab=AdvTab(), coverages_tab=CoveragesTab(), plancode_tab=PlancodeTab(),
        benefits_tab=BenefitsTab(), transaction_tab=TransactionTab(),
        segment52_tab=Segment52Tab(),
    )
    yield SimpleNamespace(**widgets)
    for widget in widgets.values():
        widget.close()
        widget.deleteLater()
    app.processEvents()


def sql_for(tabs, schema="DB2TAB", **kwargs):
    return build_cyberlife_sql(schema, "", "25", **vars(tabs), **kwargs)


def test_no_new_columns_or_69_scan_by_default(tabs):
    sql = sql_for(tabs)
    for field in SEGMENT52_FIELDS:
        assert f"USERGEN.{field.name}" not in sql
    assert "CONVERSION_SC" not in sql
    assert "FH_FIXED" not in sql


@pytest.mark.parametrize("schema", ["DB2TAB", "UNIT", "CYBERTEK", "CKSR"])
def test_display_all_52_fields_reuses_full_key_left_join(tabs, schema):
    tabs.display_tab.chk_segment52.setChecked(True)
    sql = sql_for(tabs, schema)
    assert len(SEGMENT52_FIELDS) == 11
    for field in SEGMENT52_FIELDS:
        assert f", USERGEN.{field.name} {field.name}" in sql
    assert sql.count(f"JOIN {schema}.TH_USER_GENERIC ") == 1
    assert f"LEFT OUTER JOIN {schema}.TH_USER_GENERIC USERGEN" in sql
    for key in ("CK_SYS_CD", "CK_CMP_CD", "TCH_POL_ID"):
        assert f"POLICY1.{key} = USERGEN.{key}" in sql
    assert "USERGEN." not in sql.partition("\nWHERE ")[2]


@pytest.mark.parametrize("field", SEGMENT52_FIELDS, ids=lambda field: field.name)
def test_each_52_criterion_filters_and_automatically_displays(tabs, field):
    page = tabs.segment52_tab
    if field.kind == "text":
        page.text_inputs[field.name].setText("ab")
        expected = [f"UPPER(TRIM(USERGEN.{field.name})) = 'AB'"]
    else:
        lo, hi = page.ranges[field.name]
        if field.kind == "date":
            lo.setText("1/2/2025")
            hi.setText("2026-06-30")
            expected = [
                f"USERGEN.{field.name} >= '2025-01-02'",
                f"USERGEN.{field.name} <= '2026-06-30'",
            ]
        else:
            lo.setText("0")
            hi.setText("123.45" if field.kind == "decimal" else "12")
            expected = [
                f"USERGEN.{field.name} >= 0",
                f"USERGEN.{field.name} <= {hi.text()}",
            ]
    sql = sql_for(tabs)
    for predicate in expected:
        assert predicate in sql
    assert f", USERGEN.{field.name} {field.name}" in sql


def test_52_partial_range_and_text_escaping(tabs):
    page = tabs.segment52_tab
    page.ranges["CONV_CREDIT_AMT"][1].setText("999999999.99")
    page.text_inputs["SOURCE_PLAN_CODE"].setText(" a'b ")
    page.match_types["SOURCE_PLAN_CODE"].setCurrentText("Begins with")
    sql = sql_for(tabs)
    assert "USERGEN.CONV_CREDIT_AMT <= 999999999.99" in sql
    assert "USERGEN.CONV_CREDIT_AMT >=" not in sql
    assert "UPPER(TRIM(USERGEN.SOURCE_PLAN_CODE)) LIKE 'A''B%'" in sql
    assert page.text_inputs["SOURCE_PLAN_CODE"].text() == " A'B "


@pytest.mark.parametrize("field,lo,hi", [
    ("APP_RECEIVED_DATE", "not-a-date", ""),
    ("SOURCE_ISSUE_DATE", "", "2/30/2026"),
    ("SOURCE_PLAN_EFF_DATE", "2026-06-01", "2025-01-01"),
    ("CONV_CREDIT_AMT", "abc", ""),
    ("SOURCE_FACE_AMT", "NaN", ""),
    ("CONV_FACE_AMT", "", "Infinity"),
    ("CONV_CREDIT_PERIOD", "1.5", ""),
    ("CONV_TO_TRM_PERIOD", "12", "6"),
])
def test_bad_52_range_is_reported_not_silently_ignored(tabs, field, lo, hi):
    page = tabs.segment52_tab
    page.ranges[field][0].setText(lo)
    page.ranges[field][1].setText(hi)
    with pytest.raises(ValueError, match=f"52 Segment / {field}"):
        sql_for(tabs)


def test_52_individual_display_and_clear(tabs):
    page = tabs.segment52_tab
    page.display_fields["APP_RECEIVED_DATE"].setChecked(True)
    sql = sql_for(tabs)
    assert ", USERGEN.APP_RECEIVED_DATE APP_RECEIVED_DATE" in sql
    assert "USERGEN.SOURCE_PLAN_CODE" not in sql
    assert "USERGEN." not in sql.partition("\nWHERE ")[2]
    page._display_all()
    assert all(cb.isChecked() for cb in page.display_fields.values())
    page.set_state({})
    assert not any(cb.isChecked() for cb in page.display_fields.values())


def test_52_state_json_roundtrip(tabs):
    page = tabs.segment52_tab
    page._display_all()
    page.ranges["APP_RECEIVED_DATE"][0].setText("1/1/2026")
    page.ranges["CONV_FACE_AMT"][1].setText("150000.25")
    page.text_inputs["SOURCE_PLAN_CODE"].setText("abc")
    page.match_types["SOURCE_PLAN_CODE"].setCurrentText("Contains")
    state = json.loads(json.dumps(page.get_state()))
    expected_sql = sql_for(tabs)
    page.set_state({})
    page.set_state(state)
    assert page.get_state() == state
    assert sql_for(tabs) == expected_sql


def test_52_coverage_level_and_old_conversion_displays_coexist(tabs):
    tabs.segment52_tab._display_all()
    tabs.display_tab.chk_segment52.setChecked(True)
    tabs.display_tab.chk_converted_pol.setChecked(True)
    tabs.display_tab.chk_conv_credit.setChecked(True)
    sql = sql_for(tabs, coverage_level=True, coverage_scope="Covs 2+ only")
    for field in SEGMENT52_FIELDS:
        assert sql.count(f", USERGEN.{field.name} {field.name}") == 1
    assert "USERGEN.SOURCE_ISSUE_DATE CONV_ISSDT" in sql
    assert "UPDF.CONV_CREDIT_PERIOD CN_CRED_PERIOD" in sql
    assert "RESULTCOV.COV_PHA_NBR" in sql


def test_builder_registers_persists_and_clears_segment_page(tabs, monkeypatch):
    from suiteview.audit import audit_window

    monkeypatch.setattr(audit_window, "load_ui_settings", lambda: {})
    monkeypatch.setattr(audit_window, "save_ui_settings", lambda settings: None)
    win = audit_window.AuditWindow()
    try:
        assert win.tabs.tabText(win.tabs.indexOf(win.segment52_tab)) == "52 Segment"
        win.segment52_tab._display_all()
        win.segment52_tab.ranges["CONV_FACE_AMT"][0].setText("1000")
        win.display_tab.chk_conversion_dates.setChecked(True)
        saved = json.loads(json.dumps(win._cyberlife_query_object_state()))
        assert saved["tabs"]["segment52"] == win.segment52_tab.get_state()
        assert saved["tabs"]["display"]["chk_conversion_dates"] is True
        expected_sql = win._build_sql()
        assert ", USERGEN.CONV_FACE_AMT CONV_FACE_AMT" in expected_sql
        assert "USERGEN.CONV_FACE_AMT >= 1000" in expected_sql
        win._on_clear_cyberlife()
        assert "USERGEN.CONV_FACE_AMT" not in win._build_sql()
        assert not win.display_tab.chk_conversion_dates.isChecked()
        for key, tab in win._cyberlife_criteria_tabs():
            tab.set_state(saved["tabs"].get(key, {}))
        assert win._build_sql() == expected_sql
    finally:
        win.close()
        win.deleteLater()
