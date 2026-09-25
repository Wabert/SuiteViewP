"""Whole Life criteria: standard controls, Par preset and base-only SQL."""
import json
import os
import sqlite3
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QGroupBox
from suiteview.audit.constants import PARTICIPATION_TYPE_DESCRIPTIONS
from suiteview.audit.cyberlife_query import participation_predicate, build_cyberlife_sql
from suiteview.audit.tabs.adv_tab import AdvTab
from suiteview.audit.tabs.benefits_tab import BenefitsTab
from suiteview.audit.tabs.coverages_tab import CoveragesTab
from suiteview.audit.tabs.display_tab import DisplayTab
from suiteview.audit.tabs.plancode_tab import PlancodeTab
from suiteview.audit.tabs.policy2_tab import Policy2Tab
from suiteview.audit.tabs.policy_tab import PolicyTab
from suiteview.audit.tabs.wl_tab import WlTab
from suiteview.audit.cyberlife_criteria import collect_audit_criteria

@pytest.fixture
def tab(qtbot):
    widget = WlTab()
    qtbot.addWidget(widget)
    return widget

def _build(tab, policy2=None, **kwargs):
    return build_cyberlife_sql(collect_audit_criteria(kwargs.pop('schema', 'DB2TAB'), 'I', '25', policy_tab=PolicyTab(), display_tab=DisplayTab(), policy2_tab=policy2 or Policy2Tab(), adv_tab=AdvTab(), coverages_tab=CoveragesTab(), plancode_tab=PlancodeTab(), benefits_tab=BenefitsTab(), wl_tab=tab, **kwargs))

def test_par_button_replaces_selection_with_exactly_a_to_h(tab, qtbot):
    tab.chk_participation_type.setChecked(True)
    tab.list_participation_type.selectAll()
    qtbot.mouseClick(tab.btn_par, Qt.MouseButton.LeftButton)
    assert tab.chk_participation_type.isChecked()
    assert tab.list_participation_type.isEnabled()
    assert tab.selected_participation_codes() == list('ABCDEFGH')
    tab.chk_participation_type.setChecked(False)
    assert not tab.selected_participation_codes()
    assert not tab.list_participation_type.isEnabled()
    qtbot.mouseClick(tab.btn_par, Qt.MouseButton.LeftButton)
    assert tab.selected_participation_codes() == list('ABCDEFGH')

@pytest.mark.parametrize('code', ['', *'0123456789ABCDEFGH'])
def test_each_code_filters_individually_without_including_null(tab, code):
    tab.chk_participation_type.setChecked(True)
    item = tab.list_participation_type.item(list(PARTICIPATION_TYPE_DESCRIPTIONS).index(code))
    item.setSelected(True)
    sql = _build(tab)
    predicate = participation_predicate([code])
    assert predicate in sql.rsplit('\nWHERE ', 1)[1]
    db = sqlite3.connect(':memory:')
    try:
        for candidate in ['', *'0123456789ABCDEFGH', None, 'Z', '  ']:
            match = db.execute(f'WITH COVERAGE1 AS (SELECT ? AS DIV_PTP_TYP_CD) SELECT 1 FROM COVERAGE1 WHERE {predicate}', (candidate,)).fetchone()
            assert bool(match) == (candidate is not None and candidate.strip() == code)
    finally:
        db.close()

@pytest.mark.parametrize('coverage_level', [False, True])
def test_base_scope_and_policy2_composition(tab, qtbot, coverage_level):
    policy2 = Policy2Tab()
    qtbot.addWidget(policy2)
    policy2.chk_participating.setChecked(True)
    policy2.list_participating.item(1).setSelected(True)
    tab._select_par()
    sql = _build(tab, policy2, schema='UNIT', coverage_level=coverage_level)
    where = sql.rsplit('\nWHERE ', 1)[1]
    assert participation_predicate(list('ABCDEFGH')) in where
    assert participation_predicate(['9']) in where
    assert where.count('TRIM(COVERAGE1.DIV_PTP_TYP_CD)') == 2
    assert 'RESULTCOV.DIV_PTP_TYP_CD' not in sql
    assert 'FROM UNIT.LH_COV_PHA C1 WHERE C1.COV_PHA_NBR = 1' in sql
    assert sql.count(' ParticipationCode') == 1
    assert sql.count(' END) Participation\n') == 1
    assert ' END) ParticipationType' in sql

def test_existing_controls_generate_filters_and_clear(tab):
    baseline = _build(tab)
    for checkbox, listbox in ((tab.chk_pri_div, tab.list_pri_div), (tab.chk_sec_div, tab.list_sec_div), (tab.chk_nfo, tab.list_nfo)):
        checkbox.setChecked(True)
        listbox.item(1).setSelected(True)
        listbox.item(2).setSelected(True)
    tab.chk_cv_rate.setChecked(True)
    sql = _build(tab)
    for column in ('PRI_DIV_OPT_CD', 'DIV_2ND_OPT_CD', 'NFO_OPT_TYP_CD'):
        assert f"POLICY1.{column} IN ('1', '2')" in sql
    assert '(COVERAGE1.LOW_DUR_1_CSV_AMT > 0 OR COVERAGE1.LOW_DUR_2_CSV_AMT > 0)' in sql
    tab.set_state({})
    assert _build(tab) == baseline

def test_state_round_trip_and_standard_checkboxes(tab, qtbot):
    tab._select_par()
    tab.chk_pri_div.setChecked(True)
    tab.list_pri_div.item(4).setSelected(True)
    tab.chk_sec_div.setChecked(True)
    tab.list_sec_div.item(3).setSelected(True)
    tab.chk_nfo.setChecked(True)
    tab.list_nfo.item(2).setSelected(True)
    tab.chk_cv_rate.setChecked(True)
    restored = WlTab()
    qtbot.addWidget(restored)
    restored.set_state(json.loads(json.dumps(tab.get_state())))
    assert restored.get_state() == tab.get_state()
    assert _build(restored) == _build(tab)
    assert not tab.findChildren(QGroupBox)
    for checkbox in tab.findChildren(QCheckBox):
        assert 'QCheckBox::indicator:checked' in checkbox.styleSheet()
    restored.set_state({})
    assert not restored.selected_participation_codes()
    assert all((not cb.isChecked() for cb in restored.findChildren(QCheckBox)))

def test_native_layout_fits_all_rows_and_descriptions(tab, qtbot):
    tab.resize(1210, 596)
    tab.show()
    qtbot.waitExposed(tab)
    assert list(PARTICIPATION_TYPE_DESCRIPTIONS) == ['', *'0123456789ABCDEFGH']
    assert tab.list_participation_type.count() == 19
    headers = (tab.chk_pri_div, tab.chk_sec_div, tab.chk_participation_type)
    assert len({header.mapTo(tab, header.rect().topLeft()).y() for header in headers}) == 1
    for checkbox, listbox in ((tab.chk_pri_div, tab.list_pri_div), (tab.chk_sec_div, tab.list_sec_div), (tab.chk_nfo, tab.list_nfo), (tab.chk_participation_type, tab.list_participation_type)):
        assert listbox.y() - (checkbox.y() + checkbox.height()) == 2
    for listbox in (tab.list_pri_div, tab.list_sec_div, tab.list_nfo, tab.list_participation_type):
        assert listbox.horizontalScrollBar().maximum() == 0
        assert listbox.verticalScrollBar().maximum() == 0
        for row in range(listbox.count()):
            item = listbox.item(row)
            assert listbox.viewport().rect().contains(listbox.visualItemRect(item))
            assert listbox.fontMetrics().horizontalAdvance(item.text()) + 4 <= listbox.viewport().width()
        top_left = listbox.mapTo(tab, listbox.rect().topLeft())
        bottom_right = listbox.mapTo(tab, listbox.rect().bottomRight())
        assert tab.rect().contains(top_left)
        assert tab.rect().contains(bottom_right)

def test_checked_without_selection_displays_but_does_not_filter(tab):
    tab.chk_participation_type.setChecked(True)
    sql = _build(tab)
    assert 'ParticipationType' in sql
    assert 'DIV_PTP_TYP_CD' not in sql.rsplit('\nWHERE ', 1)[1]
    tab.chk_participation_type.setChecked(False)
    assert 'DIV_PTP_TYP_CD' not in _build(tab)
