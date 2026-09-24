import json
import os
import sqlite3
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from suiteview.audit.cyberlife_query import _post_conversion_cte, build_cyberlife_sql
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
    assert "POST_CONVERSION" not in sql
    assert "POST_CONV_POLICY" not in sql


@pytest.mark.parametrize("schema", ["DB2TAB", "UNIT", "CYBERTEK", "CKSR"])
@pytest.mark.parametrize("coverage_level", [False, True])
@pytest.mark.parametrize("display,has_converted", [
    (False, False), (True, False), (False, True), (True, True),
])
def test_conversion_source_company_for_either_checkbox(
    tabs, schema, coverage_level, display, has_converted,
):
    tabs.display_tab.chk_converted_pol.setChecked(display)
    tabs.policy2_tab.chk_has_converted.setChecked(has_converted)
    sql = sql_for(tabs, schema, coverage_level=coverage_level)
    assert sql.count(", USERGEN.SOURCE_CMP_CODE SOURCE_CMP_CODE") == int(
        display or has_converted
    )
    assert ("USERGEN.EXCH_POL_NUMBER IS NOT NULL" in sql) == has_converted
    assert ("USERGEN.EXCH_POL_NUMBER EXCHANGE_POL" in sql) == display
    assert sql.count(f"JOIN {schema}.TH_USER_GENERIC USERGEN") == 1
    for key in ("CK_SYS_CD", "CK_CMP_CD", "TCH_POL_ID"):
        assert f"POLICY1.{key} = USERGEN.{key}" in sql
    assert "USERGEN.SOURCE_CMP_CODE" not in sql.partition("\nWHERE ")[2]


@pytest.mark.parametrize("schema", ["DB2TAB", "UNIT", "CYBERTEK", "CKSR"])
@pytest.mark.parametrize("coverage_level", [False, True])
def test_post_conversion_is_optional_display_with_source_key_left_join(
    tabs, schema, coverage_level,
):
    tabs.display_tab.chk_post_conversion.setChecked(True)
    sql = sql_for(tabs, schema, coverage_level=coverage_level)
    assert _post_conversion_cte(schema) in sql
    assert sql.count("  , PC.POST_CONV_POLICY") == 1
    assert sql.count("  , PC.POST_CONV_COMPANY") == 1
    assert """  LEFT OUTER JOIN POST_CONVERSION PC
    ON POLICY1.CK_SYS_CD = PC.CK_SYS_CD
    AND POLICY1.CK_CMP_CD = PC.SOURCE_CMP_CODE
    AND POLICY1.CK_POLICY_NBR = PC.SOURCE_POLICY_NBR
    AND POLICY1.LST_ETR_CD = 'O'""" in sql
    outer_where = sql.partition("\nWHERE ")[2]
    assert "PC." not in outer_where
    assert "LST_ETR_CD = 'O'" not in outer_where
    assert "USERGEN.EXCH_POL_NUMBER IS NOT NULL" not in sql
    assert "FETCH FIRST 25 ROWS ONLY" in sql


def test_post_conversion_links_execute_with_duplicates_missing_and_cross_company(tabs):
    """Run the production CTE and join on synthetic in-memory data, never local policies."""
    tabs.display_tab.chk_post_conversion.setChecked(True)
    sql = sql_for(tabs, "main")
    join_start = sql.index("  LEFT OUTER JOIN POST_CONVERSION PC")
    join = "\n".join(sql[join_start:].splitlines()[:5])
    db = sqlite3.connect(":memory:")
    try:
        db.execute("""CREATE TABLE LH_BAS_POL
            (CK_SYS_CD TEXT, CK_CMP_CD TEXT, TCH_POL_ID TEXT,
             CK_POLICY_NBR TEXT, LST_ETR_CD TEXT)""")
        db.execute("""CREATE TABLE TH_USER_GENERIC
            (CK_SYS_CD TEXT, CK_CMP_CD TEXT, TCH_POL_ID TEXT,
             SOURCE_CMP_CODE TEXT, EXCH_POL_NUMBER TEXT)""")
        db.executemany("INSERT INTO LH_BAS_POL VALUES (?, ?, ?, ?, ?)", [
            ("I", "01", "OLD ID", "000TERM", "O"),
            ("I", "04", "OTHER OLD ID", "000TERM", "O"),
            ("M", "01", "MODEL OLD ID", "000TERM", "O"),
            ("I", "01", "ACTIVE ID", "ACTIVE", "B"),
            ("I", "01", "MISSING ID", "MISSING", "O"),
            ("I", "01", "ZERO ID", "0TERM", "O"),
            ("I", "01", "UL ID", "UL00001", "B"),
            ("I", "26", "UL2 ID", "UL00002", "O"),
            ("I", "04", "OTHER UL ID", "UL00003", "B"),
            ("M", "01", "MODEL UL ID", "UL00004", "B"),
            ("I", "01", "CHAIN ID", "UL00005", "B"),
            ("I", "01", "ACTIVE DEST ID", "UL00006", "B"),
            ("I", "04", "UL ID", "WRONGCO", "B"),
            ("M", "01", "UL ID", "WRONGSYS", "B"),
        ])
        db.executemany("INSERT INTO TH_USER_GENERIC VALUES (?, ?, ?, ?, ?)", [
            ("I", "01", "UL ID", "01", "000TERM"),
            ("I", "01", "UL ID", "01 ", " 000TERM "),
            ("I", "26", "UL2 ID", "01", "000TERM"),
            ("I", "04", "OTHER UL ID", "04", "000TERM"),
            ("M", "01", "MODEL UL ID", "01", "000TERM"),
            ("I", "01", "CHAIN ID", "26", "UL00002"),
            ("I", "01", "ACTIVE DEST ID", "01", "ACTIVE"),
            ("I", "01", "ORPHAN ID", "01", "MISSING"),
            ("I", "01", "UL ID", None, "MISSING"),
            ("I", "01", "UL ID", " ", "MISSING"),
            ("I", "01", "UL ID", "01", None),
            ("I", "01", "UL ID", "01", " "),
        ])
        rows = db.execute(
            "WITH " + _post_conversion_cte("main") + """
            SELECT POLICY1.CK_SYS_CD, POLICY1.CK_CMP_CD, POLICY1.CK_POLICY_NBR,
                   PC.POST_CONV_COMPANY, PC.POST_CONV_POLICY
            FROM main.LH_BAS_POL POLICY1
            """ + join
        ).fetchall()
        assert len(rows) == 15  # All 14 policies remain; only one has two destinations.
        linked = {}
        for system, company, policy, target_company, target_policy in rows:
            linked.setdefault((system, company, policy), set()).add(
                (target_company, target_policy))
        assert linked[("I", "01", "000TERM")] == {
            ("01", "UL00001"), ("26", "UL00002"),
        }
        assert linked[("I", "04", "000TERM")] == {("04", "UL00003")}
        assert linked[("M", "01", "000TERM")] == {("01", "UL00004")}
        assert linked[("I", "26", "UL00002")] == {("01", "UL00005")}
        for policy in ("ACTIVE", "MISSING", "0TERM", "UL00001"):
            assert linked[("I", "01", policy)] == {(None, None)}
    finally:
        db.close()


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
        win.display_tab.chk_post_conversion.setChecked(True)
        saved = json.loads(json.dumps(win._cyberlife_query_object_state()))
        assert saved["tabs"]["segment52"] == win.segment52_tab.get_state()
        assert saved["tabs"]["display"]["chk_conversion_dates"] is True
        assert saved["tabs"]["display"]["chk_post_conversion"] is True
        expected_sql = win._build_sql()
        assert ", USERGEN.CONV_FACE_AMT CONV_FACE_AMT" in expected_sql
        assert "USERGEN.CONV_FACE_AMT >= 1000" in expected_sql
        win._on_clear_cyberlife()
        assert "USERGEN.CONV_FACE_AMT" not in win._build_sql()
        assert not win.display_tab.chk_conversion_dates.isChecked()
        assert not win.display_tab.chk_post_conversion.isChecked()
        assert "POST_CONVERSION" not in win._build_sql()
        for key, tab in win._cyberlife_criteria_tabs():
            tab.set_state(saved["tabs"].get(key, {}))
        assert win._build_sql() == expected_sql
    finally:
        win.close()
        win.deleteLater()
