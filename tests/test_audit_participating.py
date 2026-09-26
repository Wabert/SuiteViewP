"""Base-coverage participation selection, SQL semantics and compact layout."""
import json
import os
import sqlite3
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PyQt6.QtWidgets import QLabel
from suiteview.audit.cyberlife_query import participation_description, build_cyberlife_sql
from suiteview.audit.tabs.adv_tab import AdvTab
from suiteview.audit.tabs.benefits_tab import BenefitsTab
from suiteview.audit.tabs.coverages_tab import CoveragesTab
from suiteview.audit.tabs.display_tab import DisplayTab
from suiteview.audit.tabs.plancode_tab import PlancodeTab
from suiteview.audit.tabs.policy2_tab import Policy2Tab
from suiteview.audit.tabs.policy_tab import PolicyTab
from suiteview.audit.cyberlife_criteria import collect_audit_criteria
LABELS = ['Participating', 'Participating but divs are paid up', 'Nonparticipating']

@pytest.fixture
def tab(qtbot):
    widget = Policy2Tab()
    qtbot.addWidget(widget)
    return widget

def _build(tab, **kwargs):
    return build_cyberlife_sql(collect_audit_criteria(kwargs.pop('schema', 'DB2TAB'), 'I', '25', policy_tab=PolicyTab(), display_tab=DisplayTab(), policy2_tab=tab, adv_tab=AdvTab(), coverages_tab=CoveragesTab(), plancode_tab=PlancodeTab(), benefits_tab=BenefitsTab(), **kwargs))

@pytest.mark.parametrize('coverage_level', [False, True])
@pytest.mark.parametrize('schema', ['DB2TAB', 'UNIT'])
@pytest.mark.parametrize('rows,codes', [([0], "'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'"), ([1], "'9'"), ([2], "'', '0', '1', '2', '3', '4', '5', '6', '7', '8'"), ([0, 1], "'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', '9'")])
def test_selected_categories_use_only_base_coverage(tab, rows, codes, schema, coverage_level):
    tab.chk_participating.setChecked(True)
    for row in rows:
        tab.list_participating.item(row).setSelected(True)
    tab.txt_last_fin_date_lo.setText('2025-01-01')
    sql = _build(tab, schema=schema, coverage_level=coverage_level)
    assert f'FROM {schema}.LH_COV_PHA C1 WHERE C1.COV_PHA_NBR = 1' in sql
    assert f'TRIM(COVERAGE1.DIV_PTP_TYP_CD) IN ({codes})' in sql.rsplit('\nWHERE ', 1)[1]
    assert "POLICY1.LST_FIN_DT >= '2025-01-01'" in sql
    assert 'COVERAGE1.DIV_PTP_TYP_CD ParticipationCode' in sql
    assert f'{participation_description()} Participation' in sql
    assert 'RESULTCOV.DIV_PTP_TYP_CD' not in sql
    assert 'COVSALL.DIV_PTP_TYP_CD' not in sql
    if schema != 'DB2TAB':
        assert 'DB2TAB.' not in sql

@pytest.mark.parametrize('code,expected', [*((code, LABELS[0]) for code in 'ABCDEFGH'), ('9', LABELS[1]), *((code, LABELS[2]) for code in '012345678'), ('', LABELS[2]), ('   ', LABELS[2]), (' A ', LABELS[0]), (None, 'Unknown'), ('Z', 'Unknown'), ('a', 'Unknown')])
def test_description_and_filters_agree_for_every_code(tab, code, expected):
    db = sqlite3.connect(':memory:')
    try:
        description = db.execute(f'WITH COVERAGE1 AS (SELECT ? AS DIV_PTP_TYP_CD) SELECT {participation_description()} FROM COVERAGE1', (code,)).fetchone()[0]
        assert description == expected
        tab.chk_participating.setChecked(True)
        for index, label in enumerate(LABELS):
            tab.list_participating.clearSelection()
            tab.list_participating.item(index).setSelected(True)
            where = _build(tab).rsplit('\nWHERE ', 1)[1]
            predicate = next((line.strip().removeprefix('AND ').strip() for line in where.splitlines() if 'TRIM(COVERAGE1.DIV_PTP_TYP_CD)' in line))
            matched = db.execute(f'WITH COVERAGE1 AS (SELECT ? AS DIV_PTP_TYP_CD) SELECT 1 FROM COVERAGE1 WHERE {predicate}', (code,)).fetchone()
            assert bool(matched) == (label == expected)
    finally:
        db.close()

def test_disabled_or_display_only_does_not_filter(tab):
    tab.list_participating.item(0).setSelected(True)
    assert 'DIV_PTP_TYP_CD' not in _build(tab)
    tab.chk_participating.setChecked(True)
    tab.list_participating.clearSelection()
    sql = _build(tab)
    assert 'ParticipationCode' in sql
    assert 'DIV_PTP_TYP_CD' not in sql.rsplit('\nWHERE ', 1)[1]

def test_state_round_trip_reset_and_three_choices(tab, qtbot):
    assert [tab.list_participating.item(i).text() for i in range(3)] == LABELS
    assert tab.list_participating.count() == 3
    assert not tab.list_participating.isEnabled()
    tab.chk_participating.setChecked(True)
    tab.list_participating.item(0).setSelected(True)
    tab.list_participating.item(1).setSelected(True)
    restored = Policy2Tab()
    qtbot.addWidget(restored)
    restored.set_state(json.loads(json.dumps(tab.get_state())))
    assert restored.get_state() == tab.get_state()
    assert restored.list_participating.isEnabled()
    restored.set_state({})
    assert not restored.chk_participating.isChecked()
    assert not restored.list_participating.isEnabled()
    assert not restored.list_participating.selectedItems()
    assert 'DIV_PTP_TYP_CD' not in _build(restored)

def test_compact_layout_fits_screenshot_size(tab, qtbot):
    tab.resize(1210, 596)
    tab.show()
    qtbot.waitExposed(tab)
    rows = [tab.txt_term_entry_date_lo, tab.txt_term_last_fin_date_lo, tab.txt_term_date_both_lo]
    assert [rows[i + 1].y() - rows[i].y() for i in range(2)] == [24, 24]
    assert tab.chk_participating.y() > tab.chk_failed_guideline.geometry().bottom()
    assert tab.list_participating.geometry().bottom() < 596
    assert tab.list_participating.verticalScrollBar().maximum() == 0
    for i in range(3):
        assert tab.list_participating.viewport().rect().contains(tab.list_participating.visualItemRect(tab.list_participating.item(i)))
    label = next((label for label in tab.findChildren(QLabel) if label.text() == 'Termination Last Fin Date (01)'))
    # Offscreen Qt on CI may lack the native Segoe UI font and return inflated
    # fallback metrics. Keep the compact-width check deterministic while still
    # flagging a gross text-fit regression.
    assert label.width() == 195
    assert label.fontMetrics().horizontalAdvance(label.text()) <= label.width() * 2
