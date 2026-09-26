import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from suiteview.audit.cyberlife_query import build_cyberlife_sql, name_match_predicate
from suiteview.audit.db2_table_fields import CUSTOM_DISPLAY_TABLES, TABLE_FIELDS
from suiteview.audit.tabs.adv_tab import AdvTab
from suiteview.audit.tabs.benefits_tab import BenefitsTab
from suiteview.audit.tabs.coverages_tab import CoveragesTab
from suiteview.audit.tabs.custom_display_tab import CustomDisplayTab
from suiteview.audit.tabs.display_tab import DisplayTab
from suiteview.audit.tabs.plancode_tab import PlancodeTab
from suiteview.audit.tabs.policy2_tab import Policy2Tab
from suiteview.audit.tabs.policy_tab import PolicyTab
from suiteview.audit.tabs.transaction_tab import TransactionTab
from tests.audit_criteria_helpers import collect_audit_criteria
_QT_APP = None

def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP

def _table_item(tab: CustomDisplayTab, label: str, row: int=0):
    lw = tab.rows[row].combo_tables.list_widget
    return lw.findItems(label, Qt.MatchFlag.MatchExactly)[0]

def _select(tab: CustomDisplayTab, table_label: str, fields: list[str], row: int=0):
    """Helper: enable, pick a table by label, and select the given fields."""
    r = tab.rows[row]
    r.chk_enable.setChecked(True)
    _table_item(tab, table_label, row).setSelected(True)
    fw = r.combo_fields.list_widget
    for i in range(fw.count()):
        item = fw.item(i)
        if item.data(Qt.ItemDataRole.UserRole) in fields:
            item.setSelected(True)

def _build(custom_tab: CustomDisplayTab, coverage_level: bool=False) -> str:
    return build_cyberlife_sql(collect_audit_criteria('DB2TAB', '', '25', policy_tab=PolicyTab(), display_tab=DisplayTab(), policy2_tab=Policy2Tab(), adv_tab=AdvTab(), coverages_tab=CoveragesTab(), plancode_tab=PlancodeTab(), benefits_tab=BenefitsTab(), transaction_tab=TransactionTab(), coverage_level=coverage_level, custom_display_tab=custom_tab))


def test_custom_display_collection_surfaces_errors():
    _app()

    class BrokenCustomDisplay:
        def get_selected_fields(self):
            raise RuntimeError('selection failed')

        def get_criteria_filters(self):
            return []

    with pytest.raises(RuntimeError, match='selection failed'):
        collect_audit_criteria(
            'DB2TAB', '', '25',
            policy_tab=PolicyTab(), display_tab=DisplayTab(), policy2_tab=Policy2Tab(),
            adv_tab=AdvTab(), coverages_tab=CoveragesTab(), plancode_tab=PlancodeTab(),
            benefits_tab=BenefitsTab(), transaction_tab=TransactionTab(),
            custom_display_tab=BrokenCustomDisplay(),
        )


def test_name_match_like_escapes_wildcards_literally():
    predicate = name_match_predicate("PERSON.FIRST_NAME", "Contains", "Ann_%\\")
    assert predicate == (
        "UPPER(TRIM(PERSON.FIRST_NAME)) LIKE '%ANN\\_\\%\\\\%' ESCAPE '\\'"
    )

def test_catalog_only_exposes_requested_tables():
    assert set(CUSTOM_DISPLAY_TABLES.values()) == {'LH_BAS_POL', 'TH_BAS_POL', 'LH_COV_PHA', 'TH_COV_PHA'}
    for table in CUSTOM_DISPLAY_TABLES.values():
        assert TABLE_FIELDS.get(table), f'no fields for {table}'

def test_disabled_tab_adds_nothing():
    _app()
    tab = CustomDisplayTab()
    _table_item(tab, 'Policy (LH_BAS_POL)').setSelected(True)
    fw = tab.rows[0].combo_fields.list_widget
    for i in range(min(2, fw.count())):
        fw.item(i).setSelected(True)
    assert tab.get_selected_fields() == []
    sql = _build(tab)
    assert 'CUSTOM_THBAS' not in sql
    assert 'CUSTOM_THCOV' not in sql

def test_policy_level_field_uses_policy1_alias():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Policy (LH_BAS_POL)', ['APP_WRT_DT'])
    assert ('LH_BAS_POL', 'APP_WRT_DT') in tab.get_selected_fields()
    sql = _build(tab)
    assert '  , POLICY1.APP_WRT_DT APP_WRT_DT' in sql

def test_coverage_level_field_uses_coverage1_alias():
    _app()
    tab = CustomDisplayTab()
    field = TABLE_FIELDS['LH_COV_PHA'][0][0]
    _select(tab, 'Coverage (LH_COV_PHA)', [field])
    sql = _build(tab)
    assert f'  , COVERAGE1.{field} {field}' in sql

def test_th_bas_pol_field_adds_dedicated_join():
    _app()
    tab = CustomDisplayTab()
    field = TABLE_FIELDS['TH_BAS_POL'][0][0]
    _select(tab, 'Policy Adv (TH_BAS_POL)', [field])
    sql = _build(tab)
    assert f'  , CUSTOM_THBAS.{field} {field}' in sql
    assert 'LEFT OUTER JOIN DB2TAB.TH_BAS_POL CUSTOM_THBAS' in sql
    assert 'POLICY1.TCH_POL_ID = CUSTOM_THBAS.TCH_POL_ID' in sql

def test_th_cov_pha_field_adds_dedicated_join_matched_on_coverage():
    _app()
    tab = CustomDisplayTab()
    field = TABLE_FIELDS['TH_COV_PHA'][0][0]
    _select(tab, 'Coverage Adv (TH_COV_PHA)', [field])
    sql = _build(tab)
    assert f'  , CUSTOM_THCOV.{field} {field}' in sql
    assert 'LEFT OUTER JOIN DB2TAB.TH_COV_PHA CUSTOM_THCOV' in sql
    assert 'COVERAGE1.COV_PHA_NBR = CUSTOM_THCOV.COV_PHA_NBR' in sql

def test_coverage_level_uses_resultcov_alias_for_th_cov():
    _app()
    tab = CustomDisplayTab()
    field = TABLE_FIELDS['TH_COV_PHA'][0][0]
    _select(tab, 'Coverage Adv (TH_COV_PHA)', [field])
    sql = _build(tab, coverage_level=True)
    assert 'RESULTCOV.COV_PHA_NBR = CUSTOM_THCOV.COV_PHA_NBR' in sql

def test_state_round_trips_selections():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Policy (LH_BAS_POL)', ['APP_WRT_DT'])
    state = tab.get_state()
    restored = CustomDisplayTab()
    restored.set_state(state)
    assert restored.rows[0].chk_enable.isChecked()
    assert ('LH_BAS_POL', 'APP_WRT_DT') in restored.get_selected_fields()

def test_multiple_rows_combine_fields_from_different_tables():
    _app()
    tab = CustomDisplayTab()
    assert len(tab.rows) == 3
    _select(tab, 'Policy (LH_BAS_POL)', ['APP_WRT_DT'], row=0)
    th_field = TABLE_FIELDS['TH_BAS_POL'][0][0]
    _select(tab, 'Policy Adv (TH_BAS_POL)', [th_field], row=1)
    selected = tab.get_selected_fields()
    assert ('LH_BAS_POL', 'APP_WRT_DT') in selected
    assert ('TH_BAS_POL', th_field) in selected
    sql = _build(tab)
    assert '  , POLICY1.APP_WRT_DT APP_WRT_DT' in sql
    assert f'  , CUSTOM_THBAS.{th_field} {th_field}' in sql

def test_switching_tables_remembers_field_selections():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Policy (LH_BAS_POL)', ['APP_WRT_DT'])
    _table_item(tab, 'Coverage (LH_COV_PHA)').setSelected(True)
    _table_item(tab, 'Policy (LH_BAS_POL)').setSelected(True)
    assert ('LH_BAS_POL', 'APP_WRT_DT') in tab.get_selected_fields()

def test_blank_criteria_adds_no_where():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Policy (LH_BAS_POL)', ['APP_WRT_DT'])
    assert tab.get_criteria_filters() == []
    sql = _build(tab)
    assert 'LIKE' not in sql
    assert 'UPPER(TRIM(POLICY1.APP_WRT_DT))' not in sql

def test_contains_criteria_adds_like_where():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Policy (LH_BAS_POL)', ['APP_WRT_DT'])
    r = tab.rows[0]
    r.combo_criteria.setCurrentText('Contains')
    r.txt_criteria.setText('smith')
    filters = tab.get_criteria_filters()
    assert filters == [('LH_BAS_POL', ['APP_WRT_DT'], 'Contains', 'smith')]
    sql = _build(tab)
    assert "UPPER(TRIM(POLICY1.APP_WRT_DT)) LIKE '%SMITH%'" in sql

def test_exact_criteria_adds_equals_where():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Policy (LH_BAS_POL)', ['APP_WRT_DT'])
    r = tab.rows[0]
    r.combo_criteria.setCurrentText('Exact')
    r.txt_criteria.setText('ABC')
    sql = _build(tab)
    assert "UPPER(TRIM(POLICY1.APP_WRT_DT)) = 'ABC'" in sql

def test_criteria_ignored_when_row_disabled():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Policy (LH_BAS_POL)', ['APP_WRT_DT'])
    r = tab.rows[0]
    r.combo_criteria.setCurrentText('Contains')
    r.txt_criteria.setText('smith')
    r.chk_enable.setChecked(False)
    assert tab.get_criteria_filters() == []
    sql = _build(tab)
    assert 'LIKE' not in sql

def test_criteria_state_round_trips():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Policy (LH_BAS_POL)', ['APP_WRT_DT'])
    tab.rows[0].combo_criteria.setCurrentText('Contains')
    tab.rows[0].txt_criteria.setText('smith')
    state = tab.get_state()
    restored = CustomDisplayTab()
    restored.set_state(state)
    assert restored.rows[0].combo_criteria.currentText() == 'Contains'
    assert restored.rows[0].txt_criteria.text() == 'smith'
    assert restored.get_criteria_filters() == [('LH_BAS_POL', ['APP_WRT_DT'], 'Contains', 'smith')]
