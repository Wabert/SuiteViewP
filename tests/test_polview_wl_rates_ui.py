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
        company_code="08",
        product=SimpleNamespace(is_advanced_product=False, product_type="WL"),
        status=SimpleNamespace(premium_pay_status_code="22"),
        coverages=SimpleNamespace(cov_issue_age=lambda index: 59),
        rates=SimpleNamespace(
            cyberlife_rate_user_code="08",
            cov_cash_value_key=lambda index: "1WL511",
            build_coverage_rate_matrix=Mock(),
        ),
    )
    raw.set_data(["Old rate"], [(999,)], table_name="Previous coverage")
    return SimpleNamespace(_policy=policy, tabs=tabs, raw_table_tab=raw, _show_status=Mock())


def test_wl_rates_show_in_existing_filter_grid(display):
    display._policy.rates.build_coverage_rate_matrix.return_value = [
        ["Duration", "CV"], [0, 0], [1, 18.25],
    ]
    GetPolicyWindow._on_rate_selected(display, "Coverages", "Cov 01", 1)
    assert display.raw_table_tab._current_cols == ["Duration", "CV"]
    assert display.raw_table_tab._current_rows == [(0, 0), (1, 18.25)]
    assert display.raw_table_tab.table_label.text() == "Whole Life Cash Value Rates - Coverage 1"
    assert not display.raw_table_tab._is_transposed
    assert "2 rows" in display._show_status.call_args.args[0]


@pytest.mark.parametrize("status", ["44", "45", " 44 ", " 45 "])
@pytest.mark.parametrize("transposed", [False, True])
def test_eti_rpu_shows_unavailable_without_looking_up_cash_values(display, status, transposed):
    display._policy.status.premium_pay_status_code = status
    display._policy.rates.cov_cash_value_key = Mock()
    display._policy.coverages.cov_issue_age = Mock()
    display.raw_table_tab._is_transposed = transposed

    GetPolicyWindow._on_rate_selected(display, "Coverages", "Cov 01", 1)

    message = "Cash value file is not available for policies on ETI or RPU."
    raw = display.raw_table_tab
    assert display.tabs.currentWidget() is raw
    assert raw.table_label.text() == "Whole Life Cash Value Rates - Coverage 1"
    assert raw._current_cols == []
    assert raw._current_rows == []
    assert raw._df_normal is None
    assert raw._df_transposed is None
    for grid in (raw._normal_grid, raw._transposed_grid):
        assert grid.model.rowCount() == 1
        assert grid.model.data(grid.model.index(0, 0), Qt.ItemDataRole.DisplayRole) == message
        assert grid.table_view.columnWidth(0) >= grid.table_view.fontMetrics().horizontalAdvance(message)
    display._show_status.assert_called_with(message)
    display._policy.rates.build_coverage_rate_matrix.assert_not_called()
    display._policy.rates.cov_cash_value_key.assert_not_called()
    display._policy.coverages.cov_issue_age.assert_not_called()


@pytest.mark.parametrize("status", ["21", "22", "41", "42", "43", "46", "47"])
def test_other_wl_statuses_still_load_cash_values_after_unavailable_message(display, status):
    display._policy.status.premium_pay_status_code = "45"
    GetPolicyWindow._on_rate_selected(display, "Coverages", "Cov 01", 1)
    display._policy.status.premium_pay_status_code = status
    display._policy.rates.build_coverage_rate_matrix.return_value = [["Duration", "CV"], [0, 18.25]]

    GetPolicyWindow._on_rate_selected(display, "Coverages", "Cov 01", 1)

    display._policy.rates.build_coverage_rate_matrix.assert_called_once_with(1)
    assert display.raw_table_tab._current_rows == [(0, 18.25)]


@pytest.mark.parametrize("product,advanced", [("UL", True), ("ISWL", True), ("TERM", False)])
@pytest.mark.parametrize("status", ["44", "45"])
def test_eti_rpu_message_does_not_block_other_product_rates(display, product, advanced, status):
    display._policy.product.product_type = product
    display._policy.product.is_advanced_product = advanced
    display._policy.status.premium_pay_status_code = status
    display._policy.rates.build_coverage_rate_matrix.return_value = [["Year", "COI"], [1, 1.25]]

    GetPolicyWindow._on_rate_selected(display, "Coverages", "Cov 01", 1)

    display._policy.rates.build_coverage_rate_matrix.assert_called_once_with(1)
    assert display.raw_table_tab._current_rows == [(1, 1.25)]


@pytest.mark.parametrize("category,builder", [
    ("Benefits", "build_benefit_rate_matrix"), ("Policy", "build_policy_rate_matrix"),
])
def test_eti_message_does_not_block_other_rate_categories(display, category, builder):
    display._policy.status.premium_pay_status_code = "44"
    build = Mock(return_value=[["Year", "Rate"], [1, 1.25]])
    setattr(display._policy.rates, builder, build)

    GetPolicyWindow._on_rate_selected(display, category, category, 1)

    build.assert_called_once()
    assert display.raw_table_tab._current_rows == [(1, 1.25)]


def test_wl_missing_schedule_clears_old_rates_and_explains_exact_key(display):
    display._policy.rates.build_coverage_rate_matrix.return_value = None
    GetPolicyWindow._on_rate_selected(display, "Coverages", "Cov 01", 1)
    assert display.raw_table_tab._current_rows == []
    message = display._show_status.call_args.args[0]
    assert all(text in message for text in ("WL_RATE_CV", "08", "1WL511", "59", "user_defined=blank"))
    assert "band" not in message


def test_rate_database_error_is_visible_and_does_not_leave_stale_data(display, caplog):
    display._policy.rates.build_coverage_rate_matrix.side_effect = RatesError("ODBC unavailable")
    GetPolicyWindow._on_rate_selected(display, "Coverages", "Cov 01", 1)
    assert display.raw_table_tab._current_rows == []
    assert "Error loading rates: ODBC unavailable" in display._show_status.call_args.args[0]
    assert "Rate display failed" in caplog.text


@pytest.mark.parametrize("product,advanced", [("WL", False), ("UL", True), ("TERM", False)])
def test_rates_tree_retains_selection_and_wl_tooltip_across_tab_switch(qtbot, product, advanced):
    policy = SimpleNamespace(
        product=SimpleNamespace(is_advanced_product=advanced, product_type=product),
        rates=SimpleNamespace(has_fixed_premium_rates=product == "WL"),
        coverages=SimpleNamespace(coverage_count=1, cov_plancode=lambda index: "201WL500"),
        benefits=SimpleNamespace(benefit_count=0, get_benefits=lambda: []),
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
