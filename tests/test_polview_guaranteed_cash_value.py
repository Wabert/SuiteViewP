from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from suiteview.polview.models.policy_information import PolicyInformation
from suiteview.polview.ui.tabs.policy_tab import PolicyTab
from suiteview.polview.ui.tabs.targets_tab import AccumulatorsWidget

_BLANK_CV = {"LOW_DUR_CSV_AMT": None, "LOW_DUR_1_CSV_AMT": None,
             "LOW_DUR_2_CSV_AMT": None, "LOW_DUR_3_CSV_AMT": None}
_ZERO_NSP = {"LOW_DUR_NSP_AMT": "0.00", "LOW_DUR_1_NSP_AMT": "0.00",
             "LOW_DUR_2_NSP_AMT": "0.000000"}


def _policy(row, status="22", issue=date(1994, 7, 6), next_mv=date(2026, 10, 6), active=True):
    policy = object.__new__(PolicyInformation)
    bas = {"PRM_PAY_STA_REA_CD": status, "NXT_MVRY_PRC_DT": next_mv.isoformat(),
           "NON_TRD_POL_IND": "1"}
    row = {"COV_PHA_NBR": 1, **row}

    def data_item(table, field, index=0):
        if table == "LH_COV_PHA":
            return row.get(field)
        if table == "LH_BAS_POL":
            return bas.get(field)
        return None

    policy.data_item = data_item
    policy.data_item_count = lambda table: 1 if table == "LH_COV_PHA" else 0
    policy.get_coverages = lambda: [SimpleNamespace(cov_pha_nbr=1, issue_date=issue)]
    policy._coverage_is_active = lambda cov, as_of=None: active
    return policy


def _cv_row():
    return {"LOW_DUR_PER": 31, "LOW_DUR_CSV_AMT": "333.00", "LOW_DUR_1_CSV_AMT": "351.00",
            "LOW_DUR_2_CSV_AMT": "369.00", "LOW_DUR_3_CSV_AMT": "388.00",
            "COV_UNT_QTY": "25.000", "COV_VPU_AMT": "1000.00", **_ZERO_NSP}


def _nsp_row():
    return {"LOW_DUR_PER": 32, **_BLANK_CV, "LOW_DUR_NSP_AMT": "423.32",
            "LOW_DUR_1_NSP_AMT": "437.58", "LOW_DUR_2_NSP_AMT": "452.038452",
            "COV_UNT_QTY": "6.950", "COV_VPU_AMT": "1000.00"}


def test_cv_rates_are_keyed_from_low_duration():
    info = _policy(_cv_row()).cov_cash_value_rates(1)

    assert info["basis"] == "CV"
    assert info["rates"] == {31: Decimal("333.00"), 32: Decimal("351.00"),
                             33: Decimal("369.00"), 34: Decimal("388.00")}


def test_iswl_gcv_interpolates_by_months_since_anniversary():
    result = _policy(_cv_row()).guaranteed_cash_value(date(2026, 9, 6))

    # 25 x (351 x 10 + 369 x 2) / 12
    assert result["value"] == Decimal("8850.00")
    assert result["details"][0]["duration"] == 32
    assert result["details"][0]["months"] == 2


def test_default_date_is_last_processed_monthliversary(monkeypatch):
    policy = _policy(_cv_row())
    monkeypatch.setattr(PolicyInformation, "valuation_date",
                        property(lambda self: date(2003, 9, 11)))

    assert policy.guaranteed_cash_value()["as_of"] == date(2026, 9, 6)


def test_nonforfeiture_uses_nsp_rates():
    policy = _policy(_nsp_row(), status="45", issue=date(1994, 6, 11))
    info = policy.cov_cash_value_rates(1)
    result = policy.guaranteed_cash_value(date(2026, 9, 11))

    assert (info["basis"], info["nonforfeiture"]) == ("NSP", "RPU")
    assert result["value"] == Decimal("2966.85")


def test_duration_outside_stored_window_is_not_calculated():
    row = {**_cv_row(), "LOW_DUR_PER": 12}
    result = _policy(row).guaranteed_cash_value(date(2026, 9, 6))

    assert result["value"] is None
    assert "12-15" in result["reason"]


def test_no_rates_reports_reason():
    row = {"LOW_DUR_PER": 0, **_BLANK_CV, **_ZERO_NSP, "COV_UNT_QTY": "1"}
    result = _policy(row).guaranteed_cash_value(date(2026, 9, 6))

    assert result["value"] is None
    assert result["reason"] == "No stored cash value or NSP rates"


def test_inactive_coverage_is_excluded_with_reason():
    row = {**_cv_row(), "LOW_DUR_PER": 12}
    result = _policy(row, status="41", active=False).guaranteed_cash_value(date(2026, 9, 6))

    assert result["value"] is None
    assert result["reason"] == "Cov 1: coverage not active"


def test_negative_nsp_rate_is_used_not_dropped():
    row = {**_nsp_row(), "LOW_DUR_1_NSP_AMT": "-3.81"}
    info = _policy(row, status="44").cov_cash_value_rates(1)

    assert info["basis"] == "NSP"
    assert info["rates"][33] == Decimal("-3.81")


def test_month_end_issue_counts_clamped_monthliversaries():
    row = {**_cv_row(), "LOW_DUR_PER": 31}
    policy = _policy(row, issue=date(1994, 1, 31))

    # Anniversary 2026-01-31; the Feb 28 monthliversary completes month one.
    result = policy.guaranteed_cash_value(date(2026, 2, 28))

    assert result["details"][0]["months"] == 1


def test_unmatched_coverage_record_blocks_value():
    policy = _policy(_cv_row())
    policy.get_coverages = lambda: []

    result = policy.guaranteed_cash_value(date(2026, 9, 6))

    assert result["value"] is None
    assert "coverage record unavailable" in result["reason"]


def test_accumulators_label_nsp_basis(qtbot):
    widget = AccumulatorsWidget()
    qtbot.addWidget(widget)
    gcv = _policy(_nsp_row(), status="45", issue=date(1994, 6, 11)).guaranteed_cash_value(
        date(2026, 9, 11))

    widget.load_data({"gcv": gcv})

    assert widget.get_value("gcv_label") == "2,966.85 (NSP)"
    assert "not reconciled" in widget._fields["gcv_label"].toolTip()


class _RatesPolicy:
    coverage_count = 1

    def __init__(self, info):
        self._info = info

    def cov_cash_value_rates(self, _index):
        return self._info


def test_policy_tab_shows_rates_in_play(qtbot):
    tab = PolicyTab()
    qtbot.addWidget(tab)
    tab.show()
    info = _policy(_nsp_row(), status="44").cov_cash_value_rates(1)

    tab._populate_cash_value_rates(_RatesPolicy(info))

    c = tab.col2
    assert c.get_value("cv_rate_basis") == "NSP - ETI per 1,000"
    assert c._labels["cv_rate_0"].text() == "Dur 32 NSP:"
    assert c.get_value("cv_rate_2") == "452.04"
    assert not c._fields["cv_rate_3"].isVisible()


def test_policy_tab_without_rates(qtbot):
    tab = PolicyTab()
    qtbot.addWidget(tab)
    tab.show()

    tab._populate_cash_value_rates(_RatesPolicy({"basis": None}))

    assert tab.col2.get_value("cv_rate_basis") == "None stored"
    assert not tab.col2._fields["cv_rate_0"].isVisible()


@pytest.mark.parametrize(("gcv", "text"), [
    ({"value": Decimal("8850.00"), "details": [], "reason": ""}, "8,850.00"),
    ({"value": None, "details": [], "reason": "No stored cash value or NSP rates"}, "N/A"),
])
def test_accumulators_show_guaranteed_cash_value(qtbot, gcv, text):
    widget = AccumulatorsWidget()
    qtbot.addWidget(widget)

    widget.load_data({"gcv": gcv})

    assert widget.get_value("gcv_label") == text
