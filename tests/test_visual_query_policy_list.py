"""Pasted lists, join suggestions, canvas plan badges and Table View (no database)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import re
from unittest.mock import patch

import pandas as pd
import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QMessageBox

from suiteview.audit.dataforge.join_canvas_view import SuggestionLineItem
from suiteview.audit.dialogs.pasted_list_dialog import PastedListDialog
from suiteview.audit.dynamic_group import BAS_POL_TABLE, DynamicQuery
from suiteview.audit.federated_query import execute_federated_plan
from suiteview.audit.join_suggestions import (
    KIND_DATABASE, KIND_FILE, KIND_LIST, suggest_canvas_joins, suggest_join_keys,
)
from suiteview.audit.policy_list import (
    build_policy_list, guess_columns, identify_columns, list_column_names, list_rows,
    looks_like_header, parse_clipboard_text, safe_table_name,
)
from suiteview.audit.tabs.visual_joins_tab import VisualJoinsTab

COV = "DB2TAB.LH_COV_PHA"
POL_COLS = ["CK_SYS_CD", "CK_CMP_CD", "TCH_POL_ID", "CK_POLICY_NBR", "POL_PRM_AMT"]
COV_COLS = ["CK_SYS_CD", "CK_CMP_CD", "TCH_POL_ID", "COV_PHA_NBR", "PLN_DES_SER_CD"]
EXCEL = "Policy\tCompany\tNote\nU0532652\t1\tcheck\nE0213651\t26\t\nu0532652\t01\tdup\n"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# ── Parsing ──────────────────────────────────────────────────────────────

def test_excel_paste_is_normalized_with_header_and_company_codes():
    grid = parse_clipboard_text(EXCEL)
    assert grid[0] == ["Policy", "Company", "Note"]
    assert looks_like_header(grid)
    assert guess_columns(grid, True) == (0, 1)
    result = build_policy_list(grid, has_header=True, policy_col=0, company_col=1)
    assert result.columns == ["PolicyNumber", "CompanyCode", "SystemCode", "Note"]
    assert result.rows == [["U0532652", "01", "I", "check"], ["E0213651", "26", "I", ""]]
    assert result.duplicates_removed == 1
    assert result.summary() == "2 policies, 1 duplicates removed"
    assert result.warnings() == []


def test_headerless_policy_and_company_columns_are_guessed():
    grid = parse_clipboard_text("26 000226237\n8 1234567\n")
    assert not looks_like_header(grid)
    assert guess_columns(grid, False) == (1, 0)
    result = build_policy_list(grid, has_header=False, policy_col=1, company_col=0)
    assert [row[:2] for row in result.rows] == [["000226237", "26"], ["1234567", "08"]]
    # Different lengths of all-digit policies: Excel may have eaten leading zeros.
    assert result.numeric_lengths == (7, 9)
    assert "leading zeros" in result.warnings()[0]
    padded = build_policy_list(grid, has_header=False, policy_col=1, company_col=0,
                               pad_numeric_to=9)
    assert padded.rows[1][0] == "001234567" and padded.numeric_lengths is None


def test_single_column_and_problem_values_are_reported():
    result = build_policy_list(parse_clipboard_text("U1\nU2\n\n"), has_header=False,
                               policy_col=0, company_col=None, system_code="")
    assert result.columns == ["PolicyNumber"] and len(result.rows) == 2
    assert any("No company code column" in w for w in result.warnings())

    grid = parse_clipboard_text("P1,99\nP2,\n,01\n")
    result = build_policy_list(grid, has_header=False, policy_col=0, company_col=1)
    assert result.unknown_companies == ["99"]
    assert result.blank_companies == 1 and result.blank_policies == 1
    assert safe_table_name("Policy List", {"POLICY_LIST"}) == "Policy_List_2"


# ── Suggestions ──────────────────────────────────────────────────────────

def test_cyberlife_tables_get_the_full_policy_key():
    keys = suggest_join_keys(POL_COLS, KIND_DATABASE, COV_COLS, KIND_DATABASE)
    assert keys == [("CK_SYS_CD", "CK_SYS_CD"), ("CK_CMP_CD", "CK_CMP_CD"),
                    ("TCH_POL_ID", "TCH_POL_ID")]
    both_cov = suggest_join_keys(COV_COLS, KIND_DATABASE, COV_COLS, KIND_DATABASE)
    assert ("COV_PHA_NBR", "COV_PHA_NBR") in both_cov


def test_business_names_match_policy_keys():
    keys = suggest_join_keys(["PolicyNumber", "CompanyCode", "SystemCode"], KIND_LIST,
                             POL_COLS, KIND_DATABASE)
    assert keys == [("PolicyNumber", "CK_POLICY_NBR"), ("CompanyCode", "CK_CMP_CD"),
                    ("SystemCode", "CK_SYS_CD")]
    assert suggest_join_keys(["SLR Output[PolicyId]", "Amount"], KIND_FILE,
                             POL_COLS, KIND_DATABASE) == [
        ("SLR Output[PolicyId]", "CK_POLICY_NBR")]
    # A company code alone would match whole companies — never suggested.
    assert suggest_join_keys(["Company"], KIND_FILE, POL_COLS, KIND_DATABASE) == []
    assert suggest_join_keys(["Amount"], KIND_FILE, ["Amount"], KIND_FILE) == []
    assert suggest_join_keys(["ClaimID"], KIND_FILE, ["claim_id"], KIND_FILE) == [
        ("ClaimID", "claim_id")]


def test_each_unjoined_table_gets_one_partner_preferring_the_join_graph():
    tables = ["L", BAS_POL_TABLE, COV]
    cols = {"L": ["PolicyNumber"], BAS_POL_TABLE: POL_COLS, COV: COV_COLS}
    kinds = {"L": KIND_LIST, BAS_POL_TABLE: KIND_DATABASE, COV: KIND_DATABASE}
    joined = {frozenset(("L", BAS_POL_TABLE))}
    [(left, right, keys)] = suggest_canvas_joins(tables, cols, kinds, joined, set())
    assert (left, right) == (BAS_POL_TABLE, COV) and len(keys) == 3
    assert suggest_canvas_joins(tables, cols, kinds, joined,
                                {frozenset((BAS_POL_TABLE, COV))}) == []


def test_canvas_draws_accepts_and_dismisses_suggestions(app):
    canvas = VisualJoinsTab(tables=[BAS_POL_TABLE, COV])
    try:
        canvas.set_table_columns(BAS_POL_TABLE, POL_COLS)
        canvas.set_table_columns(COV, COV_COLS)
        canvas.ensure_on_canvas(BAS_POL_TABLE)
        canvas.ensure_on_canvas(COV)
        lines = [i for i in canvas.scene.items() if isinstance(i, SuggestionLineItem)]
        assert len(lines) == 3
        assert not canvas.suggestion_banner.isHidden()
        assert "TCH_POL_ID = " in canvas.lbl_suggestion.text()

        canvas.dismiss_suggestions()
        assert canvas.suggestion_banner.isHidden()
        assert canvas.get_state()["dismissed_suggestions"] == [sorted([BAS_POL_TABLE, COV])]
        canvas.suggest_joins()  # "Suggest Joins" looks again
        assert len(canvas.scene.suggestion_items) == 3

        canvas.scene.suggestion_accepted.emit(BAS_POL_TABLE, COV)
        [info] = canvas.get_join_infos()
        assert len(info["on_pairs"]) == 3
        assert canvas.scene.suggestion_items == []
        assert canvas.suggestion_banner.isHidden()
    finally:
        canvas.close()


def test_ctrl_v_on_canvas_requests_policy_paste(app):
    canvas = VisualJoinsTab()
    requested = []
    canvas.paste_policy_list_requested.connect(lambda: requested.append(True))
    try:
        canvas.view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V,
                                            Qt.KeyboardModifier.ControlModifier))
        assert requested == [True]
    finally:
        canvas.close()


# ── Dialog + query ───────────────────────────────────────────────────────

def test_generic_paste_only_names_clear_policy_and_company_columns():
    grid = parse_clipboard_text(EXCEL)
    assert identify_columns(grid, True) == (0, 1)
    assert list_column_names(grid, True, 0, 1) == ["PolicyNumber", "CompanyCode", "Note"]
    # Every pasted row stays: no de-duplication, no system code.
    assert list_rows(grid, True, 0, 1) == [
        ["U0532652", "01", "check"], ["E0213651", "26", ""], ["U0532652", "01", "dup"]]

    plancodes = parse_clipboard_text("B11SP500\nB11SP400\n1A130E29\n")
    assert identify_columns(plancodes, False) == (None, None)
    assert list_column_names(plancodes, False, None, None) == ["C1"]

    headerless = parse_clipboard_text("26 000226237\n8 1234567\n")
    assert identify_columns(headerless, False) == (1, 0)
    assert list_rows(headerless, False, 1, 0) == [["26", "000226237"], ["08", "1234567"]]

    numbers = parse_clipboard_text("1\t2.5\n4\t3.1\n")
    assert identify_columns(numbers, False) == (None, None)
    assert list_column_names(numbers, False, None, None) == ["C1", "C2"]
    assert list_rows(numbers, False, None, None) == [["1", "2.5"], ["4", "3.1"]]


def test_dialog_shows_the_pasted_data_and_renames_columns(app):
    dialog = PastedListDialog(taken_names=set(), text=EXCEL)
    try:
        assert dialog.chk_header.isChecked()
        assert dialog.txt_name.text() == "PastedList"
        assert dialog.column_names() == ["PolicyNumber", "CompanyCode", "Note"]
        assert dialog.table.rowCount() == 3 and dialog.lbl_count.text() == "3 rows"
        assert dialog.table.item(0, 1).text() == "01"
        assert dialog.rename_column(2, "  Agent   note ")
        assert dialog.table.horizontalHeaderItem(2).text() == "Agent note"
        with patch("suiteview.audit.dialogs.pasted_list_dialog.QMessageBox.warning") as warn:
            assert not dialog.rename_column(0, "companycode")
        assert warn.called
        assert dialog.result_data() == {
            "columns": ["PolicyNumber", "CompanyCode", "Agent note"],
            "rows": [["U0532652", "01", "check"], ["E0213651", "26", ""],
                     ["U0532652", "01", "dup"]],
        }
        dialog.chk_header.setChecked(False)
        assert dialog.column_names() == ["C1", "C2", "C3"]
        assert dialog.table.rowCount() == 4
        dialog.set_text("")
        assert not dialog.btn_add.isEnabled() and dialog.result_data() is None
    finally:
        dialog.close()

    existing = {"columns": ["PolicyNumber", "C2"], "rows": [["U1", "x"]]}
    edit = PastedListDialog(taken_names=set(), existing=existing, name="L",
                            locked_columns={"C2"})
    try:
        assert edit.txt_name.isReadOnly() and edit.chk_header.isHidden()
        assert edit.btn_add.text() == "Save"
        with patch("suiteview.audit.dialogs.pasted_list_dialog.QMessageBox.information"):
            assert not edit.rename_column(1, "Other")
        assert edit.rename_column(0, "Policy")
        assert edit.column_names() == ["Policy", "C2"]
    finally:
        edit.close()


def _pasted_query():
    group = DynamicQuery("\u25b8 Policies", "NEON_DSN", [])
    grid = parse_clipboard_text(EXCEL)
    name = group.add_policy_list(
        "PolicyList", build_policy_list(grid, has_header=True, policy_col=0, company_col=1),
        join_to_bas_pol=True)
    group.joins_tab.set_table_columns(BAS_POL_TABLE, POL_COLS)
    return group, name


class _FakeSession:
    def __init__(self, frame):
        self.frame, self.sql = frame, []

    def column_types(self, dsn, table):
        return {c: "CHAR" for c in self.frame.columns}

    def fetch(self, dsn, sql):
        self.sql.append(sql)
        found = re.search(r'"CK_POLICY_NBR" IN \((.*?)\)', sql, re.S)
        wanted = {v.strip().strip("'") for v in found.group(1).split(",")}
        return self.frame[self.frame["CK_POLICY_NBR"].isin(wanted)].reset_index(drop=True)

    def close(self):
        pass


def test_pasted_list_joins_bas_pol_and_runs_with_pushdown(app):
    group, name = _pasted_query()
    try:
        assert group.table_sources == {name: "list:PolicyList"}
        assert group.joins_tab.canvas_tables() == [name, BAS_POL_TABLE]
        [info] = group.joins_tab.get_join_infos()
        assert info["join_type"] == "LEFT OUTER JOIN"
        assert info["on_pairs"] == [("PolicyNumber", "CK_POLICY_NBR"),
                                    ("CompanyCode", "CK_CMP_CD"), ("SystemCode", "CK_SYS_CD")]
        assert group.joins_tab.scene.box_items[name].tag == "LIST"
        assert group.tab_widget.currentWidget() is group.joins_tab

        prepared = group._prepare_query()
        assert prepared.plan is not None
        assert "[pasted list] PolicyList  (2 rows)" in prepared.sql
        db2 = pd.DataFrame({"CK_SYS_CD": ["I"], "CK_CMP_CD": ["01"],
                            "TCH_POL_ID": ["U0532652  QA"], "CK_POLICY_NBR": ["U0532652"]})
        session = _FakeSession(db2)
        df = execute_federated_plan(prepared.plan, session=session)
        assert "IN ('U0532652', 'E0213651')" in session.sql[0]
        rows = dict(zip(df["PolicyNumber"], df["TCH_POL_ID"]))
        assert rows["U0532652"] == "U0532652  QA"
        assert pd.isna(rows["E0213651"])  # not found, still listed

        group.refresh_plan_badges()
        status = group.joins_tab.box_status()
        assert status[name] == ("info", "2 pasted rows")
        assert status[BAS_POL_TABLE][0] == "ok"
        assert status[BAS_POL_TABLE][1] == "\u2713 Only rows matching PolicyList"
        assert "CK_POLICY_NBR values found in PolicyList.PolicyNumber" in status[BAS_POL_TABLE][2]
    finally:
        group.close()


def test_pasted_list_round_trips_and_warns_about_whole_table_downloads(app):
    group, name = _pasted_query()
    try:
        config = group.get_config()
        assert config["inline_tables"][name]["rows"][0] == ["U0532652", "01", "I", "check"]
        restored = DynamicQuery("\u25b8 Policies 2", config["dsn"], config["tables"])
        try:
            restored.set_config(config)
            assert restored.inline_tables == group.inline_tables
            assert restored.joins_tab.canvas_tables() == [name, BAS_POL_TABLE]
            assert restored._prepare_query().plan is not None
        finally:
            restored.close()

        # Flip to "all rows from LH_BAS_POL": the policy list can no longer narrow it.
        group.joins_tab.model.set_how(name, BAS_POL_TABLE, "right")
        group.joins_tab.set_table_columns(COV, COV_COLS)
        group.joins_tab.ensure_on_canvas(COV)
        group.refresh_plan_badges()
        status = group.joins_tab.box_status()
        assert status[BAS_POL_TABLE][0] == "warn"
        assert status[COV][:2] == ("muted", "Not used — no fields or joins")

        # Removing the list from SQL Assist drops its data too.
        group.set_table_sources({})
        assert group.inline_tables == {}
    finally:
        group.close()


def test_accepted_suggestion_extends_an_outer_chain_and_ambiguity_is_refused(app):
    group, name = _pasted_query()
    try:
        group.joins_tab.set_table_columns(COV, COV_COLS)
        group.set_pinned_tables([*group.pinned_tables, COV])
        group.joins_tab.ensure_on_canvas(COV)
        group.joins_tab.accept_all_suggestions()
        infos = {frozenset((i["left_table"], i["right_table"])): i
                 for i in group.joins_tab.get_join_infos()}
        cov_join = infos[frozenset((BAS_POL_TABLE, COV))]
        # LH_BAS_POL is optional (left-joined from the list): keep its rows.
        keep = cov_join["left_table"] if cov_join["join_type"].startswith("LEFT") \
            else cov_join["right_table"]
        assert keep == BAS_POL_TABLE
        assert group._prepare_query() is not None

        group.joins_tab.model.set_how(BAS_POL_TABLE, COV, "inner")
        with patch("suiteview.audit.dynamic_group.QMessageBox.warning") as warn:
            assert group._prepare_query() is None
        assert warn.call_args[0][1] == "Ambiguous Outer Join"
        group.refresh_plan_badges()
        assert group.joins_tab.box_status()[BAS_POL_TABLE][1] == "\u26A0 Ambiguous outer join"
    finally:
        group.close()


def test_paste_list_uses_dialog_result_without_assuming_policies(app):
    group = DynamicQuery("\u25b8 P", "NEON_DSN", [])
    try:
        with patch("suiteview.audit.dialogs.pasted_list_dialog.PastedListDialog.exec",
                   return_value=1):
            name = group.paste_policy_list(EXCEL)
        assert name == "PastedList"
        assert BAS_POL_TABLE not in group.pinned_tables
        assert group.joins_tab.canvas_tables() == [name]
        assert group.joins_tab.get_join_infos() == []
        assert group.inline_tables[name]["columns"] == ["PolicyNumber", "CompanyCode", "Note"]
        with patch("suiteview.audit.dialogs.pasted_list_dialog.PastedListDialog.exec",
                   return_value=1):
            assert group.paste_policy_list(EXCEL) == "PastedList_2"
    finally:
        group.close()


def test_list_box_double_click_edit_rename_and_delete(app):
    group, name = _pasted_query()
    canvas = group.joins_tab
    try:
        edits, views = [], []
        canvas.list_edit_requested.connect(edits.append)
        canvas.table_view_requested.connect(views.append)
        with patch("suiteview.audit.dialogs.pasted_list_dialog.PastedListDialog.exec",
                   return_value=0) as exec_:
            canvas.scene.box_double_clicked.emit(name)
            canvas.scene.box_double_clicked.emit(BAS_POL_TABLE)
        assert edits == [name] and exec_.call_count == 1

        from suiteview.audit.dialogs import tables_dialog
        from suiteview.audit.query_builder_menu import query_builder_menu
        menu = query_builder_menu(canvas.view)
        canvas._extend_source_menu(menu, name)
        labels = [a.text() for a in menu.actions() if a.text()]
        assert labels == ["Open Table View\u2026", "Edit Pasted List\u2026"]
        next(a for a in menu.actions() if a.text().startswith("Open")).trigger()
        assert views == [name]
        for window in list(tables_dialog._OPEN_TABLE_VIEWS):
            window.close()

        # Renamed columns follow into the joins; columns on Display are locked.
        group.select_tab.add_field(f"{name}.Note", "Note")
        assert group._list_columns_in_use(name) == {"Note"}
        assert group.rename_list_columns(name, ["Policy", "CompanyCode", "SystemCode", "Note"])
        assert group.inline_tables[name]["columns"][0] == "Policy"
        [info] = canvas.get_join_infos()
        assert info["on_pairs"][0] == ("Policy", "CK_POLICY_NBR")
        assert "Policy" in canvas.model.get_source(name).field_names()

        # Selecting the list box and pressing Delete removes the list from the query.
        canvas.scene.box_items[name].setSelected(True)
        with patch("suiteview.audit.dynamic_group.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Yes):
            canvas.view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete,
                                                Qt.KeyboardModifier.NoModifier))
        assert name not in group.inline_tables and name not in group.table_sources
        assert name not in group.tables and name not in group.pinned_tables
        assert canvas.canvas_tables() == [BAS_POL_TABLE]

        # A database box is only taken off the canvas.
        canvas.scene.box_items[BAS_POL_TABLE].setSelected(True)
        canvas.view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete,
                                            Qt.KeyboardModifier.NoModifier))
        assert canvas.canvas_tables() == [] and BAS_POL_TABLE in group.tables
    finally:
        group.close()


def test_table_view_window_shows_a_pasted_list_with_adjustable_rows(app):
    from suiteview.audit.dialogs import tables_dialog

    group, name = _pasted_query()
    try:
        view = group.open_table_view(name)
        try:
            assert view.isWindow() and view.parent() is None
            assert view in tables_dialog._OPEN_TABLE_VIEWS
            assert view.row_limit() == 1000
            assert len(view.table.df) == 2
            view.spn_rows.setValue(1)
            view._reload_if_changed()
            assert len(view.table.df) == 1
            assert view.lbl_status.text().startswith("1 rows")
        finally:
            view.close()
    finally:
        group.close()
    assert tables_dialog._table_view_sql("DB2TAB.LH_BAS_POL", "DB2", 250) == (
        'SELECT * FROM "DB2TAB"."LH_BAS_POL" FETCH FIRST 250 ROWS ONLY')
    assert tables_dialog._table_view_sql("dbo.T", "SQLSERVER", 5) == (
        "SELECT TOP 5 * FROM [dbo].[T]")
