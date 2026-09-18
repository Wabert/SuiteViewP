"""Regression tests for the Advanced Product Monthliversary Values table."""


def test_monthliversary_values_include_total_monthly_deduction(monkeypatch):
    """MD is the displayed total of COI, other, and expense charges."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    from PyQt6.QtWidgets import QApplication

    from suiteview.polview.ui.tabs.adv_prod_tab import AdvProdValuesTab

    class Policy:
        def fetch_table(self, table_name):
            assert table_name == "LH_POL_MVRY_VAL"
            return [{
                "MVRY_DT": "2026-09-08",
                "POL_DUR_NBR": 17,
                "CINS_AMT": "57.39",
                "OTH_PRM_AMT": "174.91",
                "EXP_CRG_AMT": "5.00",
            }]

        def cov_issue_date(self, _coverage_phase):
            return None

    application = QApplication.instance() or QApplication([])
    tab = AdvProdValuesTab()
    tab._load_monthliversary_from_policy(Policy())

    table = tab.mv_values.table._data_table
    assert table.horizontalHeaderItem(9).text() == "MD"
    assert table.item(0, 9).text() == "237.30"

    tab.deleteLater()
    application.processEvents()
