"""Rates tree and display routing with native table widgets, without live data."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTabWidget

from suiteview.core.rates import RatesError
from suiteview.polview.ui.main_window import GetPolicyWindow
from suiteview.polview.ui.tabs.raw_table_tab import RawTableTab
from suiteview.polview.ui.tree_panel import PolicyRecordTreeWidget


@pytest.fixture
def display(qtbot):
    tabs = QTabWidget()
    raw = RawTableTab()
    tabs.addTab(raw, "Data")
    qtbot.addWidget(tabs)
    policy = SimpleNamespace(
        is_advanced_product=False, product_type="WL", company_code="08",
        cov_cash_value_key=lambda index: "1WL511", cov_issue_age=lambda index: 59,
        build_coverage_rate_matrix=Mock(),
    )
    raw.set_data(["Old rate"], [(999,)], table_name="Previous coverage")
    return SimpleNamespace(_policy=policy, tabs=tabs, raw_table_tab=raw, _show_status=Mock())


def test_wl_rates_show_in_existing_filter_grid(display):
    display._policy.build_coverage_rate_matrix.return_value = [
        ["Duration", "CV"], [0, 0], [1, 18.25],
    ]
    GetPolicyWindow._on_rate_selected(display, "Coverages", "Cov 01", 1)
    assert display.raw_table_tab._current_cols == ["Duration", "CV"]
    assert display.raw_table_tab._current_rows == [(0, 0), (1, 18.25)]
    assert display.raw_table_tab.table_label.text() == "Whole Life Cash Value Rates - Coverage 1"
    assert not display.raw_table_tab._is_transposed
    assert "2 rows" in display._show_status.call_args.args[0]


def test_wl_missing_schedule_clears_old_rates_and_explains_exact_key(display):
    display._policy.build_coverage_rate_matrix.return_value = None
    GetPolicyWindow._on_rate_selected(display, "Coverages", "Cov 01", 1)
    assert display.raw_table_tab._current_rows == []
    message = display._show_status.call_args.args[0]
    assert all(text in message for text in ("WL_RATE_CV", "08", "1WL511", "59", "user_defined=blank"))
    assert "band" not in message


def test_rate_database_error_is_visible_and_does_not_leave_stale_data(display, caplog):
    display._policy.build_coverage_rate_matrix.side_effect = RatesError("ODBC unavailable")
    GetPolicyWindow._on_rate_selected(display, "Coverages", "Cov 01", 1)
    assert display.raw_table_tab._current_rows == []
    assert "Error loading rates: ODBC unavailable" in display._show_status.call_args.args[0]
    assert "Rate display failed" in caplog.text


@pytest.mark.parametrize("product,advanced", [("WL", False), ("UL", True), ("TERM", False)])
def test_rates_tree_retains_selection_and_wl_tooltip_across_tab_switch(qtbot, product, advanced):
    policy = SimpleNamespace(
        is_advanced_product=advanced, product_type=product,
        coverage_count=1, benefit_count=0, cov_plancode=lambda index: "201WL500",
        get_benefits=lambda: [],
    )
    tree = PolicyRecordTreeWidget()
    qtbot.addWidget(tree)
    tree.build_rates_tree(policy)
    item = tree.topLevelItem(0).child(0)
    assert ("WL_RATE_CV" in item.toolTip(0)) == (product == "WL")
    assert item.data(0, Qt.ItemDataRole.UserRole)["index"] == 1
    with qtbot.waitSignal(tree.rate_selected) as signal:
        tree._on_item_clicked(item, 0)
    assert signal.args == ["Coverages", "Cov 01 (201WL500)", 1]
    tooltip = item.toolTip(0)
    tree.switch_to_tables_mode()
    tree.switch_to_rates_mode(policy)
    assert tree.topLevelItem(0).child(0).toolTip(0) == tooltip
