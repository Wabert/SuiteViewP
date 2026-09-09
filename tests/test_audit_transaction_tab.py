import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.audit.cyberlife_query import _conversion_sc_cte, build_cyberlife_sql
from suiteview.audit.tabs.adv_tab import AdvTab
from suiteview.audit.tabs.benefits_tab import BenefitsTab
from suiteview.audit.tabs.coverages_tab import CoveragesTab
from suiteview.audit.tabs.display_tab import DisplayTab
from suiteview.audit.tabs.plancode_tab import PlancodeTab
from suiteview.audit.tabs.policy2_tab import Policy2Tab
from suiteview.audit.tabs.policy_tab import PolicyTab
from suiteview.audit.tabs.transaction_tab import TransactionTab

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def test_transaction_types_support_multiple_selections():
    _app()
    tab = TransactionTab()

    tab.transaction_types.setText("SI, SF")

    assert set(tab.transaction_types.selected_values()) == {"SI", "SF"}
    assert set(tab.get_state()["transaction_types"].split(", ")) == {"SI", "SF"}


def test_transaction_types_restore_saved_selection():
    _app()
    tab = TransactionTab()

    tab.set_state({"transaction_types": "TD, TM"})

    assert set(tab.transaction_types.selected_values()) == {"TD", "TM"}


def test_termination_display_includes_effective_date_and_transaction_types():
    _app()
    display_tab = DisplayTab()
    display_tab.chk_termination_date.setChecked(True)

    sql = build_cyberlife_sql(
        "DB2TAB",
        "",
        "25",
        policy_tab=PolicyTab(),
        display_tab=display_tab,
        policy2_tab=Policy2Tab(),
        adv_tab=AdvTab(),
        coverages_tab=CoveragesTab(),
        plancode_tab=PlancodeTab(),
        benefits_tab=BenefitsTab(),
        transaction_tab=TransactionTab(),
    )

    assert "VARCHAR_FORMAT(TD.TERM_ENTRY_DT, 'MM/DD/YYYY') TERM_ENTRY_DT" in sql
    assert "VARCHAR_FORMAT(TD.TERM_EFFECTIVE_DT, 'MM/DD/YYYY') TERM_EFFECTIVE_DT" in sql
    assert "TD.TERM_TRANS_TYPES" in sql
    assert "LISTAGG" not in sql
    assert "MAX(CASE WHEN TRANS = 'TD' THEN 1 ELSE 0 END) AS HAS_TD" in sql
    assert "SUBSTR(" in sql


def test_plancode_list_defaults_to_all_coverages_match():
    _app()
    plancode_tab = PlancodeTab()
    plancode_tab.list_plancodes.addItem("ABC123")

    sql = build_cyberlife_sql(
        "DB2TAB",
        "",
        "25",
        policy_tab=PolicyTab(),
        display_tab=DisplayTab(),
        policy2_tab=Policy2Tab(),
        adv_tab=AdvTab(),
        coverages_tab=CoveragesTab(),
        plancode_tab=plancode_tab,
        benefits_tab=BenefitsTab(),
        transaction_tab=TransactionTab(),
    )

    assert "COVSALL.PLN_DES_SER_CD IN ('ABC123')" in sql


def test_plancode_list_can_force_cov1_only_match():
    _app()
    plancode_tab = PlancodeTab()
    plancode_tab.list_plancodes.addItem("ABC123")
    plancode_tab.chk_cov1_plancode_match_only.setChecked(True)

    sql = build_cyberlife_sql(
        "DB2TAB",
        "",
        "25",
        policy_tab=PolicyTab(),
        display_tab=DisplayTab(),
        policy2_tab=Policy2Tab(),
        adv_tab=AdvTab(),
        coverages_tab=CoveragesTab(),
        plancode_tab=plancode_tab,
        benefits_tab=BenefitsTab(),
        transaction_tab=TransactionTab(),
    )

    assert "COVERAGE1.PLN_DES_SER_CD IN ('ABC123')" in sql
    assert "COVSALL.PLN_DES_SER_CD IN ('ABC123')" not in sql


def test_plancode_tab_state_persists_cov1_only_flag():
    _app()
    plancode_tab = PlancodeTab()
    plancode_tab.chk_cov1_plancode_match_only.setChecked(True)

    state = plancode_tab.get_state()
    restored = PlancodeTab()
    restored.set_state(state)

    assert restored.chk_cov1_plancode_match_only.isChecked()


def test_conversion_display_is_optional_and_preserves_other_policies():
    _app()
    display_tab = DisplayTab()
    kwargs = dict(
        policy_tab=PolicyTab(), display_tab=display_tab, policy2_tab=Policy2Tab(),
        adv_tab=AdvTab(), coverages_tab=CoveragesTab(), plancode_tab=PlancodeTab(),
        benefits_tab=BenefitsTab(), transaction_tab=TransactionTab(),
    )
    assert "CONVERSION_SC" not in build_cyberlife_sql("UNIT", "", "25", **kwargs)
    display_tab.chk_conversion_dates.setChecked(True)
    display_tab.chk_termination_date.setChecked(True)
    kwargs["transaction_tab"].transaction_types.setText("SI")
    sql = build_cyberlife_sql("UNIT", "", "25", **kwargs)
    assert _conversion_sc_cte("UNIT") in sql
    assert "VARCHAR_FORMAT(SC.CONV_SC_ENTRY_DT, 'MM/DD/YYYY') CONV_SC_ENTRY_DT" in sql
    assert "VARCHAR_FORMAT(SC.CONV_SC_EFFECTIVE_DT, 'MM/DD/YYYY') CONV_SC_EFFECTIVE_DT" in sql
    assert "LEFT OUTER JOIN CONVERSION_SC SC" in sql
    for key in ("CK_SYS_CD", "CK_CMP_CD", "TCH_POL_ID"):
        assert f"POLICY1.{key} = SC.{key}" in sql
    assert "AND SC.SC_ROW = 1" in sql
    outer_where = sql.partition("\nWHERE ")[2]
    assert "SC." not in outer_where
    assert "LST_ETR_CD = 'O'" not in outer_where
    assert "TERMINATION_DATES AS TD" in sql
    assert "FH_FIXED TR1" in sql
    restored = DisplayTab()
    restored.set_state(display_tab.get_state())
    assert restored.chk_conversion_dates.isChecked()
    restored.set_state({})
    assert not restored.chk_conversion_dates.isChecked()


def test_latest_sc_row_excludes_reversals_and_keeps_dates_paired():
    """Execute the production CTE on synthetic rows (no local policy database)."""
    db = sqlite3.connect(":memory:")
    try:
        db.execute("""CREATE TABLE LH_BAS_POL
            (CK_SYS_CD TEXT, CK_CMP_CD TEXT, TCH_POL_ID TEXT, LST_ETR_CD TEXT)""")
        db.execute("""CREATE TABLE FH_FIXED
            (CK_CMP_CD TEXT, TCH_POL_ID TEXT, TRANS TEXT, ENTRY_DT TEXT,
             ASOF_DT TEXT, FCB0_REV_IND TEXT, FCB2_REV_APPL_IND TEXT,
             ENTRY_TIME TEXT, SEQ_NO INTEGER)""")
        policies = [
            ("I", "01", "PAIR", "O"), ("I", "01", "TIE", "O"),
            ("I", "01", "REVERSED", "O"), ("I", "01", "MISSING", "O"),
            ("I", "01", "ACTIVE", "B"), ("I", "01", "RPU", "R"),
            ("I", "04", "PAIR", "O"), ("M", "01", "MODEL", "O"),
        ]
        db.executemany("INSERT INTO LH_BAS_POL VALUES (?, ?, ?, ?)", policies)
        db.executemany("INSERT INTO FH_FIXED VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [
            ("01", "PAIR", "SC", "2026-01-01", "2026-06-01", "0", "0", "12:00:00", 1),
            ("01", "PAIR", "SC", "2026-02-01", "2026-01-15", "0", "0", "12:00:00", 2),
            ("01", "PAIR", "SC", "2026-03-01", "2026-03-01", "1", "0", "12:00:00", 3),
            ("01", "PAIR", "SC", "2026-04-01", "2026-04-01", "0", "1", "12:00:00", 4),
            ("01", "PAIR", "SI", "2026-05-01", "2026-05-01", "0", "0", "12:00:00", 5),
            ("01", "TIE", "SC", "2026-01-01", "2025-12-15", "0", "0", "12:00:00", 1),
            ("01", "TIE", "SC", "2026-01-01", "2025-12-01", "0", "0", "12:00:00", 2),
            ("01", "TIE", "SC", "2026-01-01", "2025-12-20", "0", "0", "08:00:00", 3),
            ("01", "TIE", "SC", None, "2025-12-25", "0", "0", "12:00:00", 4),
            ("01", "TIE", "SC", "2026-01-01", "2025-12-30", "0", "0", None, 5),
            ("01", "REVERSED", "SC", "2026-01-01", "2026-01-01", "0", "1", "12:00:00", 1),
            ("01", "ACTIVE", "SC", "2026-01-01", "2026-01-01", "0", "0", "12:00:00", 1),
            ("01", "RPU", "SC", "2026-01-01", "2026-01-01", "0", "0", "12:00:00", 1),
            ("04", "PAIR", "SC", "2026-07-01", "2026-06-01", "0", "0", "12:00:00", 1),
            ("01", "MODEL", "SC", "2026-08-01", "2026-07-01", "0", "0", "12:00:00", 1),
        ])
        rows = db.execute(
            "WITH " + _conversion_sc_cte("main") + """
            SELECT P.CK_SYS_CD, P.CK_CMP_CD, P.TCH_POL_ID,
                   SC.CONV_SC_ENTRY_DT, SC.CONV_SC_EFFECTIVE_DT
            FROM LH_BAS_POL P LEFT OUTER JOIN CONVERSION_SC SC
              ON P.CK_SYS_CD = SC.CK_SYS_CD AND P.CK_CMP_CD = SC.CK_CMP_CD
             AND P.TCH_POL_ID = SC.TCH_POL_ID AND SC.SC_ROW = 1"""
        ).fetchall()
        assert len(rows) == len(policies)
        dates = {row[:3]: row[3:] for row in rows}
        assert dates[("I", "01", "PAIR")] == ("2026-02-01", "2026-01-15")
        assert dates[("I", "01", "TIE")] == ("2026-01-01", "2025-12-01")
        assert dates[("I", "04", "PAIR")] == ("2026-07-01", "2026-06-01")
        assert dates[("M", "01", "MODEL")] == ("2026-08-01", "2026-07-01")
        for policy in ("REVERSED", "MISSING", "ACTIVE", "RPU"):
            assert dates[("I", "01", policy)] == (None, None)
    finally:
        db.close()