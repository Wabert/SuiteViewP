"""Tables panel search: find tables, fields and values in the loaded Policy Record tables."""

from decimal import Decimal

import pytest

from suiteview.polview.services.table_search import (
    MATCH_FIELD, MATCH_TABLE, MATCH_VALUE, SCOPE_ALL, SCOPE_FIELD, SCOPE_VALUE,
    search_policy_tables,
)


class CachedPolicy:
    """Only cached rows are searchable; anything else must never hit DB2."""

    def __init__(self, tables):
        self._tables = tables

    def cached_table(self, table):
        return self._tables.get(table)


TABLES = {
    "LH_COV_PHA": (
        ["TCH_POL_ID", "COV_PHA_NBR", "PLN_DES_SER_CD", "COV_UNT_QTY"],
        [("00493109  448D", 1, "1U143900  ", Decimal("100.00")),
         ("00493109  448D", 2, "1U143900  ", Decimal("25.50"))],
    ),
    "LH_BAS_POL": (
        ["TCH_POL_ID", "PRM_PAY_STA_REA_CD", "POL_PRM_AMT"],
        [("00493109  448D", "41", Decimal("1234.56"))],
    ),
}
ORDER = [("Policy Record 02", "LH_COV_PHA"), ("Policy Record 01", "LH_BAS_POL")]


def search(term, tables=TABLES, order=ORDER, **kw):
    return search_policy_tables(CachedPolicy(tables), order, term, **kw)


def test_value_hits_list_every_row_and_stripped_value():
    result = search("1u1439")
    assert [(h.match, h.table, h.field, h.row, h.value) for h in result.hits] == [
        (MATCH_VALUE, "LH_COV_PHA", "PLN_DES_SER_CD", 1, "1U143900"),
        (MATCH_VALUE, "LH_COV_PHA", "PLN_DES_SER_CD", 2, "1U143900"),
    ]
    assert result.hits[0].record == "Policy Record 02"
    assert result.tables_searched == 2 and not result.truncated


def test_field_name_hit_is_listed_once_with_its_values():
    result = search("cov_unt")
    assert len(result.hits) == 1
    hit = result.hits[0]
    assert (hit.match, hit.field, hit.row, hit.value) == (MATCH_FIELD, "COV_UNT_QTY", 0, "100.00, 25.50")
    single = search("prm_pay_sta").hits[0]
    assert (single.row, single.value) == (1, "41")


def test_table_name_hit_reports_row_count_and_searches_numbers():
    table_hits = [h for h in search("cov_pha").hits if h.match == MATCH_TABLE]
    assert [(h.table, h.value) for h in table_hits] == [("LH_COV_PHA", "2 rows")]
    assert [(h.table, h.field) for h in search("1234.5").hits] == [("LH_BAS_POL", "POL_PRM_AMT")]


def test_blank_term_finds_nothing_and_uncached_tables_are_reported():
    assert search("   ").hits == []
    result = search("1u", order=ORDER + [("Policy Record 90", "LH_POL_TOTALS")])
    assert result.not_searched == ["LH_POL_TOTALS"]
    assert result.tables_searched == 2


def test_results_are_capped_and_marked_truncated():
    result = search("0", limit=3)
    assert len(result.hits) == 3 and result.truncated


def test_value_scope_matches_only_values_even_in_matching_fields():
    result = search("cov", scope=SCOPE_VALUE)
    assert result.hits == [] and result.scope == SCOPE_VALUE
    hits = search("41", scope=SCOPE_VALUE).hits
    assert [(h.match, h.field, h.row, h.value) for h in hits] == [
        (MATCH_VALUE, "PRM_PAY_STA_REA_CD", 1, "41"),
    ]
    # A column whose name matches is still searched value-by-value.
    tables = {"T": (["CODE_41"], [("41",), ("x",)])}
    hits = search("41", tables=tables, order=[("R", "T")], scope=SCOPE_VALUE).hits
    assert [(h.match, h.row) for h in hits] == [(MATCH_VALUE, 1)]


def test_field_scope_matches_only_field_names():
    hits = search("cov", scope=SCOPE_FIELD).hits
    assert {h.match for h in hits} == {MATCH_FIELD}
    assert [h.field for h in hits] == ["COV_PHA_NBR", "COV_UNT_QTY"]
    assert search("1u1439", scope=SCOPE_FIELD).hits == []


def test_unknown_scope_is_rejected():
    with pytest.raises(ValueError):
        search("cov", scope="Tables")


def test_policy_data_cached_table_never_queries():
    from suiteview.polview.models.policy_data import PolicyData

    data = object.__new__(PolicyData)
    data._table_cache = {"LH_BAS_POL": {"columns": ["A"], "rows": [("x",)]}}
    data._table_errors = {"FH_FIXED": "SQL0204N"}
    assert data.cached_table("LH_BAS_POL") == (["A"], [("x",)])
    assert data.cached_table("FH_FIXED") is None
    assert data.cached_table("LH_COV_PHA") is None


# ── UI ───────────────────────────────────────────────────────────────────────

def test_panel_search_box_is_tables_only_and_debounced(qtbot):
    from PyQt6.QtCore import Qt

    from suiteview.polview.ui.tree_panel import PolicyRecordTreePanel

    panel = PolicyRecordTreePanel()
    qtbot.addWidget(panel)
    panel.show()
    box = panel.search_box
    assert not box.isEnabled()
    panel.set_table_presence({"LH_COV_PHA": True, "LH_BAS_POL": True, "LH_POL_TOTALS": False})
    assert box.isEnabled()
    assert panel.tables_with_data()[:1] == [("Policy Record 01", "LH_BAS_POL")]
    assert ("Policy Record 02", "LH_COV_PHA") in panel.tables_with_data()
    assert all(table != "LH_POL_TOTALS" for _, table in panel.tables_with_data())

    with qtbot.waitSignal(panel.search_requested, timeout=2000) as blocker:
        box.setText("  pln_des ")
    assert blocker.args == ["pln_des"]

    scope_btn = panel._scope_btn
    assert scope_btn.isEnabled() and panel.search_scope() == SCOPE_ALL
    for expected in (SCOPE_VALUE, SCOPE_FIELD, SCOPE_ALL):
        with qtbot.waitSignal(panel.search_requested, timeout=2000):
            qtbot.mouseClick(scope_btn, Qt.MouseButton.LeftButton)
        assert panel.search_scope() == expected
    panel.set_search_scope(SCOPE_FIELD)

    panel._policy = object()
    panel._rates_btn.setEnabled(True)
    panel._tree.build_rates_tree = lambda policy: None
    panel._tree.switch_to_rates_mode = lambda policy: setattr(panel._tree, "_mode", "rates")
    panel._on_tab_clicked("rates")
    assert panel._search_bar.isHidden()
    panel._on_tab_clicked("tables")
    assert not panel._search_bar.isHidden()

    panel.reset_for_new_policy()
    assert box.text() == "" and not box.isEnabled()
    assert not scope_btn.isEnabled()
    assert panel.search_scope() == SCOPE_FIELD  # user's choice survives a new policy


def test_raw_table_lists_matches_and_opens_a_hit(qtbot):
    from suiteview.polview.ui.tabs.raw_table_tab import RawTableTab

    tab = RawTableTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.show_search_results(search("1u1439"))
    assert tab.showing_search_results
    assert not tab.transpose_btn.isEnabled()
    assert "2 matches in 1 of 2 tables" in tab.table_label.text()
    frame = tab.search_hits_frame()
    assert list(frame.columns) == ["Match", "Record", "Table", "Field", "Row", "Value"]
    assert frame["Row"].tolist() == [1, 2]

    with qtbot.waitSignal(tab.search_hit_activated) as blocker:
        tab.activate_search_hit(1)
    assert blocker.args == ["Policy Record 02", "LH_COV_PHA", "PLN_DES_SER_CD", 2]

    columns, rows = TABLES["LH_COV_PHA"]
    tab.set_data(columns, rows, table_name="Table: LH_COV_PHA", transposed=True)
    assert not tab.showing_search_results and tab.transpose_btn.isEnabled()
    tab.focus_field("PLN_DES_SER_CD", 2)
    view = tab._transposed_grid.table_view
    selected = {(i.row(), i.column()) for i in view.selectionModel().selectedIndexes()}
    assert selected == {(2, 0), (2, 2)}
    assert (view.currentIndex().row(), view.currentIndex().column()) == (2, 2)
    tab.focus_field("COV_UNT_QTY")  # field hit: the whole field row
    selected = {(i.row(), i.column()) for i in view.selectionModel().selectedIndexes()}
    assert selected == {(3, 0), (3, 1), (3, 2)}

    tab.show_search_results(search("nothing-matches-this"))
    assert "No table, field or value" in str(tab.search_hits_frame().iloc[0, 0])
    tab.activate_search_hit(0)  # placeholder row is not a hit
    tab.show_search_results(search("nothing-matches-this", scope=SCOPE_VALUE))
    assert str(tab.search_hits_frame().iloc[0, 0]).startswith("No value contains")
    assert tab.table_label.text().startswith("Search (Values):")
