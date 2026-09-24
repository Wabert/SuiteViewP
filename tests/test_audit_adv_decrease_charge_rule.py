import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from suiteview.audit.tabs.adv_tab import AdvTab
from tests.test_audit_adv_cirf_search import _build

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _select(adv, rows):
    adv.chk_decr_chrg_rule.setChecked(True)
    for row in rows:
        adv.list_decr_chrg_rule.item(row).setSelected(True)


def _where(sql):
    return sql.rsplit("\nWHERE ", 1)[1]


def test_decrease_charge_rule_lists_every_live_value_and_is_gated():
    _app()
    adv = AdvTab()
    items = [adv.list_decr_chrg_rule.item(i).text()
             for i in range(adv.list_decr_chrg_rule.count())]

    assert items == ["0 - No charge on decrease", "1 - Charge on decrease", "Blank - Not set"]
    assert not adv.chk_decr_chrg_rule.isChecked()
    assert not adv.list_decr_chrg_rule.isEnabled()
    adv.chk_decr_chrg_rule.setChecked(True)
    assert adv.list_decr_chrg_rule.isEnabled()


def test_unchecked_or_empty_selection_adds_no_filter():
    _app()
    adv = AdvTab()
    assert "DECRCHG" not in _build(adv)
    adv.chk_decr_chrg_rule.setChecked(True)
    assert "DECRCHG" not in _build(adv)


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([0], "DECRCHG.DECR_CHRG_ALLOW IN ('0')"),
        ([0, 1], "DECRCHG.DECR_CHRG_ALLOW IN ('0', '1')"),
        ([2], "(DECRCHG.DECR_CHRG_ALLOW IS NULL OR DECRCHG.DECR_CHRG_ALLOW NOT IN ('0', '1'))"),
    ],
)
def test_selected_codes_filter_th_non_trd_pol_with_full_key(rows, expected):
    _app()
    adv = AdvTab()
    _select(adv, rows)

    where = _where(_build(adv))

    assert "EXISTS (SELECT 1 FROM DB2TAB.TH_NON_TRD_POL DECRCHG" in where
    assert "DECRCHG.CK_SYS_CD = POLICY1.CK_SYS_CD" in where
    assert "DECRCHG.CK_CMP_CD = POLICY1.CK_CMP_CD" in where
    assert "DECRCHG.TCH_POL_ID = POLICY1.TCH_POL_ID" in where
    assert expected in where


def test_known_and_blank_selections_are_ored():
    _app()
    adv = AdvTab()
    _select(adv, [1, 2])

    where = _where(_build(adv))

    assert ("(DECRCHG.DECR_CHRG_ALLOW IN ('1') OR (DECRCHG.DECR_CHRG_ALLOW IS NULL"
            " OR DECRCHG.DECR_CHRG_ALLOW NOT IN ('0', '1')))") in where


def test_decrease_charge_rule_state_round_trips_and_resets():
    _app()
    adv = AdvTab()
    _select(adv, [0, 2])

    restored = AdvTab()
    restored.set_state(adv.get_state())
    assert restored.chk_decr_chrg_rule.isChecked()
    assert [item.text() for item in restored.list_decr_chrg_rule.selectedItems()] == [
        "0 - No charge on decrease", "Blank - Not set"]

    restored.set_state({})
    assert not restored.chk_decr_chrg_rule.isChecked()
    assert not restored.list_decr_chrg_rule.selectedItems()


def test_adv_code_lists_show_every_row_without_scrolling():
    _app()
    adv = AdvTab()
    adv.resize(1100, 560)
    adv.show()
    _app().processEvents()
    for listbox in (adv.list_grace_rule, adv.list_db_option, adv.list_decr_chrg_rule,
                    adv.list_orig_entry, adv.list_prem_alloc):
        assert listbox.verticalScrollBar().maximum() == 0
        assert listbox.mapTo(adv, listbox.rect().bottomLeft()).y() < adv.height()
    adv.close()
