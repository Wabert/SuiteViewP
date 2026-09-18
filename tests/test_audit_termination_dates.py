import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QLabel

from suiteview.audit.constants import TERMINATION_LAST_ENTRY_CODES
from suiteview.audit.cyberlife_query import build_cyberlife_sql
from suiteview.audit.tabs.adv_tab import AdvTab
from suiteview.audit.tabs.benefits_tab import BenefitsTab
from suiteview.audit.tabs.coverages_tab import CoveragesTab
from suiteview.audit.tabs.display_tab import DisplayTab
from suiteview.audit.tabs.plancode_tab import PlancodeTab
from suiteview.audit.tabs.policy2_tab import Policy2Tab
from suiteview.audit.tabs.policy_tab import PolicyTab
from suiteview.audit.tabs.transaction_tab import TransactionTab

_QT_APP = None


@pytest.fixture
def policy2():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return Policy2Tab()


def _build(policy2, display=None, schema="DB2TAB", **options):
    return build_cyberlife_sql(
        schema, "I", "25",
        policy_tab=PolicyTab(), display_tab=display or DisplayTab(),
        policy2_tab=policy2, adv_tab=AdvTab(), coverages_tab=CoveragesTab(),
        plancode_tab=PlancodeTab(), benefits_tab=BenefitsTab(),
        transaction_tab=TransactionTab(), **options,
    )


def test_blank_ranges_do_not_add_filters_or_transaction_lookup(policy2):
    sql = _build(policy2)
    assert "TERMINATION_TRANS AS" not in sql
    assert "TERM_DATE_BOTH" not in sql
    assert "TERM_LAST_FIN_DT" not in sql
    assert "PRM_PAY_STA_REA_CD >= '97'" not in sql


def test_financial_range_gates_status_and_exact_picker_codes(policy2):
    policy2.txt_term_last_fin_date_lo.setText("1/1/2025")
    policy2.txt_term_last_fin_date_hi.setText("12/31/2025")
    sql = _build(policy2)
    assert TERMINATION_LAST_ENTRY_CODES == ("J", "L", "M", "N", "O", "P", "Q", "R", "X")
    assert "POLICY1.PRM_PAY_STA_REA_CD >= '97'" in sql
    assert "POLICY1.LST_ETR_CD IN ('J', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'X')" in sql
    assert "NULLIF(POLICY1.LST_FIN_DT, DATE('9999-12-31')) END) >= '2025-01-01'" in sql
    assert "END) <= '2025-12-31'" in sql
    assert "TERM_LAST_FIN_DT" in sql
    assert "POLICY1.PRM_PAY_STA_REA_CD StatusCode" in sql
    assert "POLICY1.LST_ETR_CD LastEntryCode" in sql
    assert "TERMINATION_TRANS AS" not in sql


@pytest.mark.parametrize("side,operator", [("lo", ">="), ("hi", "<=")])
@pytest.mark.parametrize("field", ["term_last_fin_date", "term_date_both"])
def test_open_ended_ranges(policy2, field, side, operator):
    getattr(policy2, f"txt_{field}_{side}").setText("2025-03-04")
    sql = _build(policy2)
    assert f"{operator} '2025-03-04'" in sql
    other = "<=" if operator == ">=" else ">="
    assert f"{other} '2025-03-04'" not in sql


def test_both_range_uses_unfiltered_transaction_dates_before_guarded_fallback(policy2):
    policy2.txt_term_date_both_lo.setText("2025-01-01")
    policy2.txt_term_date_both_hi.setText("2025-12-31")
    sql = _build(policy2)
    cte = sql.split(", TERMINATION_BOTH_DATES AS", 1)[1].split("\nSELECT", 1)[0]
    assert "MAX(ENTRY_DT) AS TERM_ENTRY_DT" in cte
    assert "WHERE ENTRY_DT < DATE('9999-12-31')" in cte
    assert "2025-" not in cte
    assert "FH.FCB0_REV_IND = '0'" in sql
    assert "FH.FCB2_REV_APPL_IND = '0'" in sql
    assert "FH.TRANS IN ('SC', 'SI', 'SF', 'TD', 'TM', 'TN', 'TL', 'TO')" in sql
    assert "LEFT OUTER JOIN TERMINATION_BOTH_DATES AS TDB" in sql
    assert "POLICY1.CK_CMP_CD = TDB.CK_CMP_CD" in sql
    assert "POLICY1.TCH_POL_ID = TDB.TCH_POL_ID" in sql
    assert "TDB.CK_SYS_CD" not in sql
    assert "COALESCE(TDB.TERM_ENTRY_DT, (CASE WHEN POLICY1.PRM_PAY_STA_REA_CD >= '97'" in sql
    assert "END)) >= '2025-01-01'" in sql
    assert "END)) <= '2025-12-31'" in sql
    assert "TERM_DATE_BOTH" in sql and "TERM_DATE_SOURCE" in sql
    assert "JOIN TERMINATION_DATES AS TD" not in sql


def test_old_term_range_cannot_make_both_fall_back(policy2):
    policy2.txt_term_entry_date_lo.setText("2024-01-01")
    policy2.txt_term_date_both_lo.setText("2025-01-01")
    sql = _build(policy2)
    assert "INNER JOIN TERMINATION_DATES AS TD" in sql
    assert "LEFT OUTER JOIN TERMINATION_BOTH_DATES AS TDB" in sql
    assert "FROM TERMINATION_TRANS\n   WHERE ENTRY_DT <" in sql
    assert sql.count(", TERMINATION_TRANS AS\n") == 1


def test_old_financial_range_remains_unqualified(policy2):
    policy2.txt_last_fin_date_lo.setText("2025-01-01")
    sql = _build(policy2)
    assert "POLICY1.LST_FIN_DT >= '2025-01-01'" in sql
    assert "PRM_PAY_STA_REA_CD >= '97'" not in sql


def test_display_deduplication_and_existing_termination_display(policy2):
    policy2.txt_term_date_both_lo.setText("2025-01-01")
    display = DisplayTab()
    display.chk_termination_date.setChecked(True)
    display.chk_last_entry_code.setChecked(True)
    sql = _build(policy2, display)
    assert sql.count("POLICY1.LST_ETR_CD LastEntryCode") == 1
    assert "LEFT OUTER JOIN TERMINATION_DATES AS TD" in sql
    assert "VARCHAR_FORMAT(TD.TERM_ENTRY_DT, 'MM/DD/YYYY') TERM_ENTRY_DT" in sql


@pytest.mark.parametrize("field", ["term_last_fin_date", "term_date_both"])
@pytest.mark.parametrize("lo,hi", [
    ("not-a-date", ""), ("", "2025-02-30"), ("2026-01-01", "2025-01-01"),
    ("2025-01-01' OR 1=1", ""),
])
def test_invalid_dates_raise_instead_of_dropping_filters(policy2, field, lo, hi):
    getattr(policy2, f"txt_{field}_lo").setText(lo)
    getattr(policy2, f"txt_{field}_hi").setText(hi)
    with pytest.raises(ValueError, match="Termination"):
        _build(policy2)


def test_ranges_round_trip_reset_and_layout(policy2):
    fields = ["txt_term_last_fin_date_lo", "txt_term_last_fin_date_hi",
              "txt_term_date_both_lo", "txt_term_date_both_hi"]
    for name, value in zip(fields, ["1/1/2025", "12/31/2025", "1/1/2024", "12/31/2024"]):
        getattr(policy2, name).setText(value)
    restored = Policy2Tab()
    restored.set_state(policy2.get_state())
    for name in fields:
        assert getattr(restored, name).text() == getattr(policy2, name).text()
    restored.set_state({})
    assert all(getattr(restored, name).text() == "" for name in fields)
    policy2.resize(1210, 596)
    policy2.show()
    QApplication.processEvents()
    assert policy2.txt_term_last_fin_date_lo.y() == policy2.txt_term_entry_date_lo.y() + 24
    assert policy2.txt_term_date_both_lo.y() == policy2.txt_term_last_fin_date_lo.y() + 24
    assert policy2.txt_last_fin_date_lo.y() > policy2.txt_term_date_both_lo.y()
    labels = {label.text(): label for label in policy2.findChildren(QLabel)}
    assert not labels["Termination Last Fin Date (01)"].wordWrap()
    assert "Termination Date (both)" in labels
    assert policy2.chk_failed_guideline.geometry().bottom() < policy2.height()
    policy2.close()


def test_both_filters_compose_and_use_selected_schema(policy2):
    policy2.txt_term_last_fin_date_lo.setText("2025-01-01")
    policy2.txt_term_date_both_hi.setText("2025-12-31")
    sql = _build(policy2, schema="UNIT", coverage_level=True)
    assert "FROM UNIT.FH_FIXED AS FH" in sql
    assert "DB2TAB." not in sql
    assert "END) >= '2025-01-01'" in sql
    assert "END)) <= '2025-12-31'" in sql


@pytest.mark.parametrize("mode,alias,join_type", [
    ("both", "TDB", "LEFT OUTER JOIN TERMINATION_BOTH_DATES"),
    ("entry", "TD", "INNER JOIN TERMINATION_DATES"),
    ("display", "TD", "LEFT OUTER JOIN TERMINATION_DATES"),
])
@pytest.mark.parametrize("coverage_level", [False, True])
def test_termination_transactions_require_current_policy_termination(
    policy2, mode, alias, join_type, coverage_level,
):
    display = DisplayTab()
    if mode == "both":
        policy2.txt_term_date_both_lo.setText("2025-01-01")
        policy2.txt_term_date_both_hi.setText("2025-12-31")
    elif mode == "entry":
        policy2.txt_term_entry_date_lo.setText("2025-01-01")
    else:
        display.chk_termination_date.setChecked(True)
    sql = _build(policy2, display, coverage_level=coverage_level)
    gate = (
        "POLICY1.PRM_PAY_STA_REA_CD >= '97' AND POLICY1.LST_ETR_CD "
        "IN ('J', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'X')"
    )
    assert (
        f"{join_type} AS {alias}\n"
        f"    ON POLICY1.CK_CMP_CD = {alias}.CK_CMP_CD\n"
        f"    AND POLICY1.TCH_POL_ID = {alias}.TCH_POL_ID\n"
        f"    AND {gate}"
    ) in sql
    if mode == "display":
        # Display-only must blank termination dates, not remove active policies.
        assert gate not in sql.split("\nWHERE ", 1)[1]
