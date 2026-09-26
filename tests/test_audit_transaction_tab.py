import os
import sqlite3
import pytest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
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
from suiteview.audit.transaction_filters import TransactionDateComparison
from suiteview.audit.cyberlife_criteria import collect_audit_criteria
_QT_APP = None

def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP

def test_transaction_types_support_multiple_selections():
    _app()
    tab = TransactionTab()
    tab.transaction1.transaction_types.setText('SI, SF')
    assert set(tab.transaction1.transaction_types.selected_values()) == {'SI', 'SF'}
    assert set(tab.get_state()['transaction_types'].split(', ')) == {'SI', 'SF'}

def test_transaction_types_restore_saved_selection():
    _app()
    tab = TransactionTab()
    tab.set_state({'transaction_types': 'TD, TM'})
    assert set(tab.transaction1.transaction_types.selected_values()) == {'TD', 'TM'}
    assert not tab.transaction2.transaction_types.selected_values()

def _build_transactions(tab, coverage_level=False, schema='DB2TAB'):
    return build_cyberlife_sql(collect_audit_criteria(schema, '', '25', policy_tab=PolicyTab(), display_tab=DisplayTab(), policy2_tab=Policy2Tab(), adv_tab=AdvTab(), coverages_tab=CoveragesTab(), plancode_tab=PlancodeTab(), benefits_tab=BenefitsTab(), transaction_tab=tab, coverage_level=coverage_level))

@pytest.mark.parametrize('coverage_level', [False, True])
@pytest.mark.parametrize('first,second', [(False, False), (True, False), (False, True), (True, True)])
def test_transaction_sections_generate_independent_existence_filters(first, second, coverage_level):
    _app()
    tab = TransactionTab()
    if first:
        tab.transaction1.transaction_types.setText('PR')
    if second:
        tab.transaction2.transaction_types.setText('CD')
    sql = _build_transactions(tab, coverage_level, 'UNIT')
    assert ('EXISTS (SELECT 1 FROM UNIT.FH_FIXED TR1' in sql) == first
    assert ('EXISTS (SELECT 1 FROM UNIT.FH_FIXED TR2' in sql) == second
    assert 'JOIN UNIT.FH_FIXED TR' not in sql
    where = sql.partition('\nWHERE ')[2]
    if first:
        assert "TR1.TRANS IN ('PR')" in where
    if second:
        assert "TR2.TRANS IN ('CD')" in where
    if first and second:
        assert 'AND EXISTS (SELECT 1 FROM UNIT.FH_FIXED TR2' in where

def test_both_sections_round_trip_every_field_and_clear():
    _app()
    tab = TransactionTab()
    for number, panel in enumerate((tab.transaction1, tab.transaction2), 1):
        panel.transaction_types.setText('PR, CD' if number == 1 else 'SI, SF')
        for name, (lo, hi) in panel.ranges.items():
            if name in ('entry', 'eff'):
                lo.setText(f'0{number}/01/2026')
                hi.setText(f'0{number}/28/2026')
            else:
                lo.setText(str(number))
                hi.setText(str(number + 1))
        panel.chk_eff_month.setChecked(number == 1)
        panel.chk_eff_day.setChecked(number == 2)
        panel.chk_exclude.setChecked(number == 2)
        for checkbox, choices in panel.reversal_filters.values():
            checkbox.setChecked(True)
            choices.item(number - 1).setSelected(True)
        panel.txt_origin.setText(str(number))
        panel.txt_fund_id.setText(f'F{number}, G{number}')
    tab.transaction2.date_comparisons['entry'].setCurrentText('After Trans1 Eff Date')
    tab.transaction2.date_comparisons['eff'].setCurrentText('Equal Trans1 Entry Date')
    saved = tab.get_state()
    restored = TransactionTab()
    restored.set_state(saved)
    assert restored.get_state() == saved
    assert restored.criteria() == tab.criteria()
    assert _build_transactions(restored) == _build_transactions(tab)
    restored.set_state({})
    assert restored.get_state() == TransactionTab().get_state()
    assert 'FH_FIXED TR' not in _build_transactions(restored)

def test_reloading_first_only_state_clears_second_section():
    _app()
    tab = TransactionTab()
    tab.transaction2.transaction_types.setText('CD')
    tab.transaction2.chk_eff_day.setChecked(True)
    tab.transaction2.date_comparisons['entry'].setCurrentText('After Trans1 Entry Date')
    tab.set_state({'transaction_types': 'PR', 'txt_gross_lo': '100'})
    assert tab.transaction1.ranges['gross'][0].text() == '100'
    assert 'FH_FIXED TR2' not in _build_transactions(tab)

def test_date_comparison_dropdowns_exist_only_on_second_section_with_requested_options():
    _app()
    tab = TransactionTab()
    assert not tab.transaction1.date_comparisons
    assert set(tab.transaction2.date_comparisons) == {'entry', 'eff'}
    for combo in tab.transaction2.date_comparisons.values():
        assert not combo.isEditable()
        assert combo.isEnabled()
        assert combo.currentText() == 'none'
        assert [combo.itemText(i) for i in range(combo.count())] == ['none', 'After Trans1 Entry Date', 'Before Trans1 Entry Date', 'Equal Trans1 Entry Date', 'After Trans1 Eff Date', 'Before Trans1 Eff Date', 'Equal Trans1 Eff Date']

@pytest.mark.parametrize('name,field', [('entry', 'entry_comparison'), ('eff', 'effective_comparison')])
@pytest.mark.parametrize('comparison', list(TransactionDateComparison))
def test_all_date_choices_survive_saved_query_round_trip(name, field, comparison):
    _app()
    tab = TransactionTab()
    tab.transaction2.date_comparisons[name].setCurrentText(comparison.value)
    restored = TransactionTab()
    restored.set_state(tab.get_state())
    assert getattr(restored.criteria()[1], field) == comparison
    assert restored.get_state() == tab.get_state()
    restored.set_state({})
    assert all((combo.currentText() == 'none' for combo in restored.transaction2.date_comparisons.values()))

@pytest.mark.parametrize('coverage_level', [False, True])
@pytest.mark.parametrize('schema', ['DB2TAB', 'UNIT', 'CYBERTEK', 'CKSR'])
def test_linked_dates_reach_the_query_builder_with_existing_ranges_and_flags(coverage_level, schema):
    _app()
    tab = TransactionTab()
    tab.transaction1.transaction_types.setText('PR')
    second = tab.transaction2
    second.transaction_types.setText('CD')
    second.date_comparisons['entry'].setCurrentText('After Trans1 Eff Date')
    second.date_comparisons['eff'].setCurrentText('Equal Trans1 Entry Date')
    second.ranges['entry'][0].setText('01/01/2026')
    checkbox, choices = second.reversal_filters['is_reversal']
    checkbox.setChecked(True)
    choices.item(0).setSelected(True)
    sql = _build_transactions(tab, coverage_level, schema)
    assert sql.count(f'FROM {schema}.FH_FIXED TR1') == 1
    assert sql.count(f'FROM {schema}.FH_FIXED TR2') == 1
    assert 'TR2.ENTRY_DT > TR1.ASOF_DT' in sql
    assert 'TR2.ASOF_DT = TR1.ENTRY_DT' in sql
    assert "TR2.ENTRY_DT >= '2026-01-01'" in sql
    assert "TR2.FCB0_REV_IND IN ('0')" in sql
    assert f'JOIN {schema}.FH_FIXED TR' not in sql

def test_first_exclude_clears_and_disables_date_comparisons_without_affecting_ranges():
    _app()
    tab = TransactionTab()
    second = tab.transaction2
    second.ranges['entry'][0].setText('01/01/2026')
    for combo in second.date_comparisons.values():
        combo.setCurrentText('After Trans1 Entry Date')
    second.chk_exclude.setChecked(True)
    assert all((combo.isEnabled() for combo in second.date_comparisons.values()))
    tab.transaction1.chk_exclude.setChecked(True)
    assert all((not combo.isEnabled() and combo.currentText() == 'none' for combo in second.date_comparisons.values()))
    assert second.ranges['entry'][0].text() == '01/01/2026'
    assert 'TR2.ENTRY_DT > TR1.ENTRY_DT' not in _build_transactions(tab)
    restored = TransactionTab()
    restored.set_state(tab.get_state())
    assert all((not combo.isEnabled() for combo in restored.transaction2.date_comparisons.values()))
    tab.transaction1.chk_exclude.setChecked(False)
    assert all((combo.isEnabled() and combo.currentText() == 'none' for combo in second.date_comparisons.values()))
    restored.set_state({})
    assert all((combo.isEnabled() for combo in restored.transaction2.date_comparisons.values()))

@pytest.mark.parametrize('name', ['entry', 'eff'])
def test_invalid_saved_comparison_reports_an_error(name):
    _app()
    tab = TransactionTab()
    with pytest.raises(ValueError, match='Transaction 2.*select a listed'):
        tab.set_state({'transaction2': {f'{name}_comparison': 'unrecognized'}})
    with pytest.raises(ValueError, match='Transaction 2.*Transaction 1 Exclude'):
        tab.set_state({'chk_exclude': True, 'transaction2': {f'{name}_comparison': 'After Trans1 Entry Date'}})
    assert not tab.transaction1.chk_exclude.isChecked()

@pytest.mark.parametrize('section', ['transaction1', 'transaction2'])
@pytest.mark.parametrize('name,column', [('is_reversal', 'FCB0_REV_IND'), ('reversed', 'FCB2_REV_APPL_IND')])
def test_reversal_checkbox_controls_list_and_filter(section, name, column):
    _app()
    tab = TransactionTab()
    panel = getattr(tab, section)
    checkbox, choices = panel.reversal_filters[name]
    assert not checkbox.isChecked()
    assert not choices.isEnabled()
    assert [choices.item(i).text() for i in range(choices.count())] == ['0', '1']
    checkbox.setChecked(True)
    assert choices.isEnabled()
    assert 'FH_FIXED TR' not in _build_transactions(tab)
    choices.item(0).setSelected(True)
    assert f"TR{section[-1]}.{column} IN ('0')" in _build_transactions(tab)
    panel.chk_exclude.setChecked(True)
    assert f'NOT EXISTS (SELECT 1 FROM DB2TAB.FH_FIXED TR{section[-1]}' in _build_transactions(tab)
    checkbox.setChecked(False)
    assert not choices.isEnabled()
    assert not choices.selectedItems()
    assert 'FH_FIXED TR' not in _build_transactions(tab)

def test_exclude_and_flag_defaults_do_not_change_existing_saved_queries():
    _app()
    tab = TransactionTab()
    tab.set_state({'transaction_types': 'PR', 'transaction2': {'transaction_types': 'CD'}})
    for panel in (tab.transaction1, tab.transaction2):
        assert not panel.chk_exclude.isChecked()
        assert all((not chk.isChecked() and (not choices.isEnabled()) for chk, choices in panel.reversal_filters.values()))
    sql = _build_transactions(tab)
    assert 'NOT EXISTS' not in sql
    assert 'FCB0_REV_IND' not in sql
    assert 'FCB2_REV_APPL_IND' not in sql

def test_disabled_reversal_state_cannot_apply_hidden_selection():
    _app()
    tab = TransactionTab()
    tab.set_state({'list_is_reversal': ['1'], 'transaction2': {'list_reversed': ['0']}})
    assert 'FH_FIXED TR' not in _build_transactions(tab)
    assert not tab.transaction1.reversal_filters['is_reversal'][1].selectedItems()
    assert not tab.transaction2.reversal_filters['reversed'][1].selectedItems()

@pytest.mark.parametrize('size', [(1090, 580), (1208, 595)])
def test_sections_have_uniform_compact_rows(size):
    app = _app()
    tab = TransactionTab()
    tab.resize(*size)
    tab.show()
    app.processEvents()
    first, second = (tab.transaction1, tab.transaction2)
    assert first.geometry().bottom() < second.y()
    assert first.x() == second.x()
    for panel in (first, second):
        row_names = ('entry', 'eff', 'eff_month', 'eff_day', 'gross')
        inputs = [panel.ranges[name][0] for name in row_names]
        assert len({edit.x() for edit in inputs}) == 1
        assert all((lower.y() - upper.y() == 24 for upper, lower in zip(inputs, inputs[1:])))
        for name, (lo, hi) in panel.ranges.items():
            assert lo.y() == hi.y()
            assert lo.height() == hi.height() == 22
            assert lo.width() == hi.width() == (40 if name in ('eff_month', 'eff_day') else 90)
            assert lo.geometry() == second.ranges[name][0].geometry()
            assert hi.geometry() == second.ranges[name][1].geometry()
            assert panel.rect().contains(lo.geometry())
            assert panel.rect().contains(hi.geometry())
        for name, checkbox in (('eff_month', panel.chk_eff_month), ('eff_day', panel.chk_eff_day)):
            hi = panel.ranges[name][1]
            assert checkbox.geometry().center().y() == hi.geometry().center().y()
            assert checkbox.x() == hi.x() + hi.width() + 6
            assert checkbox.width() >= checkbox.sizeHint().width()
        gross = panel.ranges['gross'][0]
        assert panel.txt_origin.y() == panel.txt_fund_id.y() > gross.geometry().bottom()
        for checkbox, choices in panel.reversal_filters.values():
            assert checkbox.y() > gross.geometry().bottom()
            assert choices.geometry().right() < panel.txt_origin.x()
            assert checkbox.y() <= panel.txt_origin.y() <= choices.geometry().bottom()
        assert panel.txt_origin.geometry().right() < panel.txt_fund_id.x()
        assert panel.rect().contains(panel.txt_fund_id.geometry())
        for name, combo in panel.date_comparisons.items():
            hi = panel.ranges[name][1]
            assert combo.y() == hi.y()
            assert combo.height() == hi.height()
            assert combo.x() == hi.x() + hi.width() + 6
            assert panel.rect().contains(combo.geometry())
            if app.platformName() == 'windows':
                assert max((combo.fontMetrics().horizontalAdvance(combo.itemText(i)) for i in range(combo.count()))) + 30 <= combo.width()
    if app.platformName() == 'windows':
        assert tab.size().width() == size[0]
    assert tab.size().height() == size[1]
    assert tab.rect().contains(second.geometry())
    tab.close()

def test_termination_display_includes_effective_date_and_transaction_types():
    _app()
    display_tab = DisplayTab()
    display_tab.chk_termination_date.setChecked(True)
    sql = build_cyberlife_sql(collect_audit_criteria('DB2TAB', '', '25', policy_tab=PolicyTab(), display_tab=display_tab, policy2_tab=Policy2Tab(), adv_tab=AdvTab(), coverages_tab=CoveragesTab(), plancode_tab=PlancodeTab(), benefits_tab=BenefitsTab(), transaction_tab=TransactionTab()))
    assert "VARCHAR_FORMAT(TD.TERM_ENTRY_DT, 'MM/DD/YYYY') TERM_ENTRY_DT" in sql
    assert "VARCHAR_FORMAT(TD.TERM_EFFECTIVE_DT, 'MM/DD/YYYY') TERM_EFFECTIVE_DT" in sql
    assert 'TD.TERM_TRANS_TYPES' in sql
    assert 'LISTAGG' not in sql
    assert "FH.TRANS IN ('SC', 'SI', 'SF', 'TD', 'TM', 'TN', 'TL', 'TO')" in sql
    assert "MAX(CASE WHEN TRANS = 'SC' THEN 1 ELSE 0 END) AS HAS_SC" in sql
    assert "CASE WHEN TTT.HAS_SC = 1 THEN ', SC' ELSE '' END" in sql
    assert "MAX(CASE WHEN TRANS = 'TD' THEN 1 ELSE 0 END) AS HAS_TD" in sql
    assert 'SUBSTR(' in sql

def test_plancode_list_defaults_to_all_coverages_match():
    _app()
    plancode_tab = PlancodeTab()
    plancode_tab.plancodes.list_values.addItem('ABC123')
    sql = build_cyberlife_sql(collect_audit_criteria('DB2TAB', '', '25', policy_tab=PolicyTab(), display_tab=DisplayTab(), policy2_tab=Policy2Tab(), adv_tab=AdvTab(), coverages_tab=CoveragesTab(), plancode_tab=plancode_tab, benefits_tab=BenefitsTab(), transaction_tab=TransactionTab()))
    assert "COVSALL.PLN_DES_SER_CD IN ('ABC123')" in sql

def test_plancode_list_can_force_cov1_only_match():
    _app()
    plancode_tab = PlancodeTab()
    plancode_tab.plancodes.list_values.addItem('ABC123')
    plancode_tab.chk_cov1_plancode_match_only.setChecked(True)
    sql = build_cyberlife_sql(collect_audit_criteria('DB2TAB', '', '25', policy_tab=PolicyTab(), display_tab=DisplayTab(), policy2_tab=Policy2Tab(), adv_tab=AdvTab(), coverages_tab=CoveragesTab(), plancode_tab=plancode_tab, benefits_tab=BenefitsTab(), transaction_tab=TransactionTab()))
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
    kwargs = dict(policy_tab=PolicyTab(), display_tab=display_tab, policy2_tab=Policy2Tab(), adv_tab=AdvTab(), coverages_tab=CoveragesTab(), plancode_tab=PlancodeTab(), benefits_tab=BenefitsTab(), transaction_tab=TransactionTab())
    assert 'CONVERSION_SC' not in build_cyberlife_sql(collect_audit_criteria('UNIT', '', '25', **kwargs))
    display_tab.chk_conversion_dates.setChecked(True)
    display_tab.chk_termination_date.setChecked(True)
    kwargs['transaction_tab'].transaction1.transaction_types.setText('SI')
    sql = build_cyberlife_sql(collect_audit_criteria('UNIT', '', '25', **kwargs))
    assert _conversion_sc_cte('UNIT') in sql
    assert "VARCHAR_FORMAT(SC.CONV_SC_ENTRY_DT, 'MM/DD/YYYY') CONV_SC_ENTRY_DT" in sql
    assert "VARCHAR_FORMAT(SC.CONV_SC_EFFECTIVE_DT, 'MM/DD/YYYY') CONV_SC_EFFECTIVE_DT" in sql
    assert 'LEFT OUTER JOIN CONVERSION_SC SC' in sql
    for key in ('CK_SYS_CD', 'CK_CMP_CD', 'TCH_POL_ID'):
        assert f'POLICY1.{key} = SC.{key}' in sql
    assert 'AND SC.SC_ROW = 1' in sql
    outer_where = sql.partition('\nWHERE ')[2]
    assert 'SC.' not in outer_where
    assert "LST_ETR_CD = 'O'" not in outer_where
    assert 'TERMINATION_DATES AS TD' in sql
    assert 'FH_FIXED TR1' in sql
    restored = DisplayTab()
    restored.set_state(display_tab.get_state())
    assert restored.chk_conversion_dates.isChecked()
    restored.set_state({})
    assert not restored.chk_conversion_dates.isChecked()

def test_latest_sc_row_excludes_reversals_and_keeps_dates_paired():
    """Execute the production CTE on synthetic rows (no local policy database)."""
    db = sqlite3.connect(':memory:')
    try:
        db.execute('CREATE TABLE LH_BAS_POL\n            (CK_SYS_CD TEXT, CK_CMP_CD TEXT, TCH_POL_ID TEXT, LST_ETR_CD TEXT)')
        db.execute('CREATE TABLE FH_FIXED\n            (CK_CMP_CD TEXT, TCH_POL_ID TEXT, TRANS TEXT, ENTRY_DT TEXT,\n             ASOF_DT TEXT, FCB0_REV_IND TEXT, FCB2_REV_APPL_IND TEXT,\n             ENTRY_TIME TEXT, SEQ_NO INTEGER)')
        policies = [('I', '01', 'PAIR', 'O'), ('I', '01', 'TIE', 'O'), ('I', '01', 'REVERSED', 'O'), ('I', '01', 'MISSING', 'O'), ('I', '01', 'ACTIVE', 'B'), ('I', '01', 'RPU', 'R'), ('I', '04', 'PAIR', 'O'), ('M', '01', 'MODEL', 'O')]
        db.executemany('INSERT INTO LH_BAS_POL VALUES (?, ?, ?, ?)', policies)
        db.executemany('INSERT INTO FH_FIXED VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', [('01', 'PAIR', 'SC', '2026-01-01', '2026-06-01', '0', '0', '12:00:00', 1), ('01', 'PAIR', 'SC', '2026-02-01', '2026-01-15', '0', '0', '12:00:00', 2), ('01', 'PAIR', 'SC', '2026-03-01', '2026-03-01', '1', '0', '12:00:00', 3), ('01', 'PAIR', 'SC', '2026-04-01', '2026-04-01', '0', '1', '12:00:00', 4), ('01', 'PAIR', 'SI', '2026-05-01', '2026-05-01', '0', '0', '12:00:00', 5), ('01', 'TIE', 'SC', '2026-01-01', '2025-12-15', '0', '0', '12:00:00', 1), ('01', 'TIE', 'SC', '2026-01-01', '2025-12-01', '0', '0', '12:00:00', 2), ('01', 'TIE', 'SC', '2026-01-01', '2025-12-20', '0', '0', '08:00:00', 3), ('01', 'TIE', 'SC', None, '2025-12-25', '0', '0', '12:00:00', 4), ('01', 'TIE', 'SC', '2026-01-01', '2025-12-30', '0', '0', None, 5), ('01', 'REVERSED', 'SC', '2026-01-01', '2026-01-01', '0', '1', '12:00:00', 1), ('01', 'ACTIVE', 'SC', '2026-01-01', '2026-01-01', '0', '0', '12:00:00', 1), ('01', 'RPU', 'SC', '2026-01-01', '2026-01-01', '0', '0', '12:00:00', 1), ('04', 'PAIR', 'SC', '2026-07-01', '2026-06-01', '0', '0', '12:00:00', 1), ('01', 'MODEL', 'SC', '2026-08-01', '2026-07-01', '0', '0', '12:00:00', 1)])
        rows = db.execute('WITH ' + _conversion_sc_cte('main') + '\n            SELECT P.CK_SYS_CD, P.CK_CMP_CD, P.TCH_POL_ID,\n                   SC.CONV_SC_ENTRY_DT, SC.CONV_SC_EFFECTIVE_DT\n            FROM LH_BAS_POL P LEFT OUTER JOIN CONVERSION_SC SC\n              ON P.CK_SYS_CD = SC.CK_SYS_CD AND P.CK_CMP_CD = SC.CK_CMP_CD\n             AND P.TCH_POL_ID = SC.TCH_POL_ID AND SC.SC_ROW = 1').fetchall()
        assert len(rows) == len(policies)
        dates = {row[:3]: row[3:] for row in rows}
        assert dates['I', '01', 'PAIR'] == ('2026-02-01', '2026-01-15')
        assert dates['I', '01', 'TIE'] == ('2026-01-01', '2025-12-01')
        assert dates['I', '04', 'PAIR'] == ('2026-07-01', '2026-06-01')
        assert dates['M', '01', 'MODEL'] == ('2026-08-01', '2026-07-01')
        for policy in ('REVERSED', 'MISSING', 'ACTIVE', 'RPU'):
            assert dates['I', '01', policy] == (None, None)
    finally:
        db.close()
