import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from suiteview.audit.cyberlife_query import build_cyberlife_sql, name_match_predicate
from suiteview.audit.db2_table_fields import CUSTOM_DISPLAY_TABLES, FIELD_KINDS, TABLE_FIELDS
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

def test_catalog_exposes_segment_tables_with_plain_labels():
    assert list(CUSTOM_DISPLAY_TABLES.items()) == [
        ('Seg 01 - LH_BAS_POL', 'LH_BAS_POL'),
        ('Seg 01 - TH_BAS_POL', 'TH_BAS_POL'),
        ('Seg 02 - LH_COV_PHA', 'LH_COV_PHA'),
        ('Seg 02 - TH_COV_PHA', 'TH_COV_PHA'),
        ('Seg 35 - LH_SPE_FQY_PRM', 'LH_SPE_FQY_PRM'),
        ('Seg 66 - LH_NON_TRD_POL', 'LH_NON_TRD_POL'),
        ('Seg 66 - TH_NON_TRD_POL', 'TH_NON_TRD_POL'),
        ('Seg 72 - LH_CTT_NOTE', 'LH_CTT_NOTE'),
    ]
    for table in CUSTOM_DISPLAY_TABLES.values():
        fields = [field for field, _desc in TABLE_FIELDS.get(table, [])]
        assert fields, f'no fields for {table}'
        assert len(fields) == len(set(fields)), f'duplicate fields for {table}'
        assert {'CK_SYS_CD', 'CK_CMP_CD', 'TCH_POL_ID'} <= set(fields), table
        assert set(FIELD_KINDS[table]) == set(fields), table


def test_catalog_module_matches_generator():
    from tools.audit import build_db2_table_fields as gen

    expected = gen.render(gen.read_table_fields())
    actual = gen.OUT.read_text(encoding='utf-8').replace('\r\n', '\n')
    assert actual == expected, 'rerun tools/audit/build_db2_table_fields.py'


def test_catalog_uses_live_column_names():
    lh_cov = {field for field, _desc in TABLE_FIELDS['LH_COV_PHA']}
    non_trd = {field for field, _desc in TABLE_FIELDS['LH_NON_TRD_POL']}
    assert 'DEATH_BEN_ADJ_IND' in lh_cov and 'DTH_BEN_ADJ_IND' not in lh_cov
    assert 'GAV_RULE_CODE' in non_trd and 'PLVL_GAV_RULE' not in non_trd


def test_seg35_special_frequency_joins_on_policy_key():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 35 - LH_SPE_FQY_PRM', ['SPE_FQY_PRM_AMT'])
    sql = _build(tab, coverage_level=True)
    assert '  , CUSTOM_LH_SPE_FQY_PRM.SPE_FQY_PRM_AMT SPE_FQY_PRM_AMT' in sql
    assert 'LEFT OUTER JOIN DB2TAB.LH_SPE_FQY_PRM CUSTOM_LH_SPE_FQY_PRM' in sql
    assert 'ON POLICY1.CK_SYS_CD = CUSTOM_LH_SPE_FQY_PRM.CK_SYS_CD' in sql
    assert 'COV_PHA_NBR = CUSTOM_LH_SPE_FQY_PRM.COV_PHA_NBR' not in sql


def test_seg66_policy_table_joins_on_policy_key():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 66 - LH_NON_TRD_POL', ['GAV_RULE_CODE'])
    sql = _build(tab, coverage_level=True)
    assert '  , CUSTOM_LH_NON_TRD_POL.GAV_RULE_CODE GAV_RULE_CODE' in sql
    assert 'LEFT OUTER JOIN DB2TAB.LH_NON_TRD_POL CUSTOM_LH_NON_TRD_POL' in sql
    assert 'ON POLICY1.CK_SYS_CD = CUSTOM_LH_NON_TRD_POL.CK_SYS_CD' in sql
    assert 'POLICY1.TCH_POL_ID = CUSTOM_LH_NON_TRD_POL.TCH_POL_ID' in sql
    assert 'COV_PHA_NBR = CUSTOM_LH_NON_TRD_POL.COV_PHA_NBR' not in sql


def test_th_cov_pha_joins_on_result_coverage():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 02 - TH_COV_PHA', ['OPT_EXER_IND'])
    sql = _build(tab, coverage_level=True)
    assert 'ON RESULTCOV.CK_SYS_CD = CUSTOM_THCOV.CK_SYS_CD' in sql
    assert 'AND RESULTCOV.COV_PHA_NBR = CUSTOM_THCOV.COV_PHA_NBR' in sql


def test_seg72_note_criteria_filters_joined_table():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 72 - LH_CTT_NOTE', ['POLICY_NT_TXT'])
    tab.rows[0].combo_criteria.setCurrentText('Contains')
    tab.rows[0].txt_criteria.setText('lapse')
    sql = _build(tab)
    assert 'LEFT OUTER JOIN DB2TAB.LH_CTT_NOTE CUSTOM_LH_CTT_NOTE' in sql
    assert "UPPER(TRIM(CUSTOM_LH_CTT_NOTE.POLICY_NT_TXT)) LIKE '%LAPSE%'" in sql


def test_same_field_from_two_tables_gets_unique_column_names():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 66 - LH_NON_TRD_POL', ['CK_CMP_CD'], row=0)
    _select(tab, 'Seg 72 - LH_CTT_NOTE', ['CK_CMP_CD'], row=1)
    sql = _build(tab)
    assert '  , CUSTOM_LH_NON_TRD_POL.CK_CMP_CD CK_CMP_CD' in sql
    assert '  , CUSTOM_LH_CTT_NOTE.CK_CMP_CD LH_CTT_NOTE_CK_CMP_CD' in sql


def _criteria(tab, match_type: str, value: str, value_to: str = '', row: int = 0):
    r = tab.rows[row]
    r.combo_criteria.setCurrentText(match_type)
    r.txt_criteria.setText(value)
    r.txt_criteria_to.setText(value_to)


def test_field_kinds_come_from_live_db2_types():
    assert FIELD_KINDS['LH_BAS_POL']['APP_WRT_DT'] == 'date'
    assert FIELD_KINDS['LH_SPE_FQY_PRM']['SPE_FQY_PRM_AMT'] == 'decimal'
    assert FIELD_KINDS['LH_BAS_POL']['BIL_DAY_NBR'] == 'integer'
    assert FIELD_KINDS['LH_BAS_POL']['POL_ISS_ST_CD'] == 'text'


def test_exact_on_numeric_field_compares_as_number():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 35 - LH_SPE_FQY_PRM', ['SPE_FQY_PRM_AMT'])
    _criteria(tab, 'Exact', '1,250.50')
    sql = _build(tab)
    assert 'CUSTOM_LH_SPE_FQY_PRM.SPE_FQY_PRM_AMT = 1250.50' in sql
    assert "SPE_FQY_PRM_AMT)) = '" not in sql


def test_exact_on_date_field_compares_as_date():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 01 - LH_BAS_POL', ['APP_WRT_DT'])
    _criteria(tab, 'Exact', '3/5/2024')
    sql = _build(tab)
    assert "POLICY1.APP_WRT_DT = '2024-03-05'" in sql


def test_exact_on_integer_field_rejects_fraction_and_text():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 01 - LH_BAS_POL', ['BIL_DAY_NBR'])
    _criteria(tab, 'Exact', '1.5')
    with pytest.raises(ValueError, match='whole number'):
        _build(tab)
    _criteria(tab, 'Exact', 'abc')
    with pytest.raises(ValueError, match='LH_BAS_POL.BIL_DAY_NBR'):
        _build(tab)


def test_exact_on_date_field_rejects_bad_date():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 01 - LH_BAS_POL', ['APP_WRT_DT'])
    _criteria(tab, 'Exact', '13/45/2024')
    with pytest.raises(ValueError, match='MM/DD/YYYY'):
        _build(tab)


def test_range_on_numeric_field_is_inclusive_and_open_ended():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 35 - LH_SPE_FQY_PRM', ['SPE_FQY_PRM_AMT'])
    _criteria(tab, 'Range', '100', '250.75')
    assert tab.get_criteria_filters() == [
        ('LH_SPE_FQY_PRM', ['SPE_FQY_PRM_AMT'], 'Range', '100', '250.75')]
    sql = _build(tab)
    assert ('(CUSTOM_LH_SPE_FQY_PRM.SPE_FQY_PRM_AMT >= 100'
            ' AND CUSTOM_LH_SPE_FQY_PRM.SPE_FQY_PRM_AMT <= 250.75)') in sql
    _criteria(tab, 'Range', '', '50')
    sql = _build(tab)
    assert 'CUSTOM_LH_SPE_FQY_PRM.SPE_FQY_PRM_AMT <= 50' in sql
    assert 'SPE_FQY_PRM_AMT >=' not in sql


def test_range_on_date_field_and_reversed_bounds():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 01 - LH_BAS_POL', ['APP_WRT_DT'])
    _criteria(tab, 'Range', '01/01/2020', '12/31/2020')
    sql = _build(tab)
    assert "(POLICY1.APP_WRT_DT >= '2020-01-01' AND POLICY1.APP_WRT_DT <= '2020-12-31')" in sql
    _criteria(tab, 'Range', '12/31/2020', '01/01/2020')
    with pytest.raises(ValueError, match='From must not be greater than To'):
        _build(tab)


def test_range_on_text_field_compares_trimmed_text():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 01 - LH_BAS_POL', ['POL_ISS_ST_CD'])
    _criteria(tab, 'Range', '10', '20')
    sql = _build(tab)
    assert ("(UPPER(TRIM(POLICY1.POL_ISS_ST_CD)) >= '10'"
            " AND UPPER(TRIM(POLICY1.POL_ISS_ST_CD)) <= '20')") in sql


def test_range_multiple_fields_are_or_combined():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 35 - LH_SPE_FQY_PRM', ['SPE_FQY_PRM_AMT', 'TOT_POL_PRM_AMT'])
    _criteria(tab, 'Range', '100', '')
    sql = _build(tab)
    assert ('(CUSTOM_LH_SPE_FQY_PRM.SPE_FQY_PRM_AMT >= 100'
            ' OR CUSTOM_LH_SPE_FQY_PRM.TOT_POL_PRM_AMT >= 100)') in sql


def test_range_shows_second_input_without_shifting_row():
    _app()
    tab = CustomDisplayTab()
    tab.show()
    row = tab.rows[0]
    remove_x = row.btn_remove.x()
    assert row.txt_criteria_to.isHidden() and row.lbl_to.isHidden()
    row.combo_criteria.setCurrentText('Range')
    QApplication.processEvents()
    assert not row.txt_criteria_to.isHidden() and not row.lbl_to.isHidden()
    assert row.btn_remove.x() == remove_x
    row.combo_criteria.setCurrentText('Exact')
    assert row.txt_criteria_to.isHidden()
    tab.close()


def test_range_value_to_ignored_unless_range_and_placeholder_hints_type():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 01 - LH_BAS_POL', ['APP_WRT_DT'])
    _criteria(tab, 'Exact', '01/02/2024', '01/03/2024')
    assert tab.get_criteria_filters() == [
        ('LH_BAS_POL', ['APP_WRT_DT'], 'Exact', '01/02/2024', '')]
    assert tab.rows[0].txt_criteria.placeholderText() == 'MM/DD/YYYY'
    tab.rows[0].combo_criteria.setCurrentText('Range')
    assert tab.rows[0].txt_criteria_to.placeholderText() == 'MM/DD/YYYY'


def test_range_state_round_trips():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 35 - LH_SPE_FQY_PRM', ['SPE_FQY_PRM_AMT'])
    _criteria(tab, 'Range', '10', '20')
    restored = CustomDisplayTab()
    restored.set_state(tab.get_state())
    row = restored.rows[0]
    assert row.combo_criteria.currentText() == 'Range'
    assert not row.txt_criteria_to.isHidden()
    assert restored.get_criteria_filters() == [
        ('LH_SPE_FQY_PRM', ['SPE_FQY_PRM_AMT'], 'Range', '10', '20')]


def test_add_and_remove_rows():
    _app()
    tab = CustomDisplayTab()
    added = tab.add_row()
    assert len(tab.rows) == 4 and tab.rows[-1] is added
    _select(tab, 'Seg 66 - TH_NON_TRD_POL', ['DECR_CHRG_ALLOW'], row=3)
    assert ('TH_NON_TRD_POL', 'DECR_CHRG_ALLOW') in tab.get_selected_fields()
    added.btn_remove.click()
    assert len(tab.rows) == 3
    assert tab.get_selected_fields() == []
    tab.remove_row(tab.rows[0])
    tab.remove_row(tab.rows[0])
    assert len(tab.rows) == 1
    assert not tab.rows[0].btn_remove.isEnabled()
    tab.remove_row(tab.rows[0])
    assert len(tab.rows) == 1


def test_state_round_trips_added_rows_and_table_choice():
    _app()
    tab = CustomDisplayTab()
    tab.add_row()
    tab.add_row()
    _select(tab, 'Seg 72 - LH_CTT_NOTE', ['CRN_DT'], row=4)
    restored = CustomDisplayTab()
    restored.set_state(tab.get_state())
    assert len(restored.rows) == 5
    row = restored.rows[4]
    assert row.combo_tables.text() == 'Seg 72 - LH_CTT_NOTE'
    assert row.combo_fields.selected_values() == ['CRN_DT']
    assert ('LH_CTT_NOTE', 'CRN_DT') in restored.get_selected_fields()


def test_clear_state_resets_to_default_blank_rows():
    _app()
    tab = CustomDisplayTab()
    tab.add_row()
    _select(tab, 'Seg 01 - LH_BAS_POL', ['APP_WRT_DT'])
    tab.set_state({})
    assert len(tab.rows) == 3
    assert tab.get_selected_fields() == []
    assert tab.rows[0].combo_tables.text() == ''

def test_disabled_tab_adds_nothing():
    _app()
    tab = CustomDisplayTab()
    _table_item(tab, 'Seg 01 - LH_BAS_POL').setSelected(True)
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
    _select(tab, 'Seg 01 - LH_BAS_POL', ['APP_WRT_DT'])
    assert ('LH_BAS_POL', 'APP_WRT_DT') in tab.get_selected_fields()
    sql = _build(tab)
    assert '  , POLICY1.APP_WRT_DT APP_WRT_DT' in sql

def test_coverage_level_field_uses_coverage1_alias():
    _app()
    tab = CustomDisplayTab()
    field = TABLE_FIELDS['LH_COV_PHA'][0][0]
    _select(tab, 'Seg 02 - LH_COV_PHA', [field])
    sql = _build(tab)
    assert f'  , COVERAGE1.{field} {field}' in sql

def test_th_bas_pol_field_adds_dedicated_join():
    _app()
    tab = CustomDisplayTab()
    field = TABLE_FIELDS['TH_BAS_POL'][0][0]
    _select(tab, 'Seg 01 - TH_BAS_POL', [field])
    sql = _build(tab)
    assert f'  , CUSTOM_THBAS.{field} {field}' in sql
    assert 'LEFT OUTER JOIN DB2TAB.TH_BAS_POL CUSTOM_THBAS' in sql
    assert 'POLICY1.TCH_POL_ID = CUSTOM_THBAS.TCH_POL_ID' in sql

def test_th_cov_pha_field_adds_dedicated_join_matched_on_coverage():
    _app()
    tab = CustomDisplayTab()
    field = TABLE_FIELDS['TH_COV_PHA'][0][0]
    _select(tab, 'Seg 02 - TH_COV_PHA', [field])
    sql = _build(tab)
    assert f'  , CUSTOM_THCOV.{field} {field}' in sql
    assert 'LEFT OUTER JOIN DB2TAB.TH_COV_PHA CUSTOM_THCOV' in sql
    assert 'COVERAGE1.COV_PHA_NBR = CUSTOM_THCOV.COV_PHA_NBR' in sql

def test_coverage_level_uses_resultcov_alias_for_th_cov():
    _app()
    tab = CustomDisplayTab()
    field = TABLE_FIELDS['TH_COV_PHA'][0][0]
    _select(tab, 'Seg 02 - TH_COV_PHA', [field])
    sql = _build(tab, coverage_level=True)
    assert 'RESULTCOV.COV_PHA_NBR = CUSTOM_THCOV.COV_PHA_NBR' in sql

def test_state_round_trips_selections():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 01 - LH_BAS_POL', ['APP_WRT_DT'])
    state = tab.get_state()
    restored = CustomDisplayTab()
    restored.set_state(state)
    assert restored.rows[0].chk_enable.isChecked()
    assert ('LH_BAS_POL', 'APP_WRT_DT') in restored.get_selected_fields()

def test_multiple_rows_combine_fields_from_different_tables():
    _app()
    tab = CustomDisplayTab()
    assert len(tab.rows) == 3
    _select(tab, 'Seg 01 - LH_BAS_POL', ['APP_WRT_DT'], row=0)
    th_field = TABLE_FIELDS['TH_BAS_POL'][0][0]
    _select(tab, 'Seg 01 - TH_BAS_POL', [th_field], row=1)
    selected = tab.get_selected_fields()
    assert ('LH_BAS_POL', 'APP_WRT_DT') in selected
    assert ('TH_BAS_POL', th_field) in selected
    sql = _build(tab)
    assert '  , POLICY1.APP_WRT_DT APP_WRT_DT' in sql
    assert f'  , CUSTOM_THBAS.{th_field} {th_field}' in sql

def test_switching_tables_remembers_field_selections():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 01 - LH_BAS_POL', ['APP_WRT_DT'])
    _table_item(tab, 'Seg 02 - LH_COV_PHA').setSelected(True)
    _table_item(tab, 'Seg 01 - LH_BAS_POL').setSelected(True)
    assert ('LH_BAS_POL', 'APP_WRT_DT') in tab.get_selected_fields()

def test_blank_criteria_adds_no_where():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 01 - LH_BAS_POL', ['APP_WRT_DT'])
    assert tab.get_criteria_filters() == []
    sql = _build(tab)
    assert 'LIKE' not in sql
    assert 'UPPER(TRIM(POLICY1.APP_WRT_DT))' not in sql

def test_contains_criteria_adds_like_where():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 01 - LH_BAS_POL', ['APP_WRT_DT'])
    r = tab.rows[0]
    r.combo_criteria.setCurrentText('Contains')
    r.txt_criteria.setText('smith')
    filters = tab.get_criteria_filters()
    assert filters == [('LH_BAS_POL', ['APP_WRT_DT'], 'Contains', 'smith', '')]
    sql = _build(tab)
    assert "UPPER(TRIM(POLICY1.APP_WRT_DT)) LIKE '%SMITH%'" in sql

def test_exact_on_text_field_adds_trimmed_upper_equals_where():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 01 - LH_BAS_POL', ['POL_ISS_ST_CD'])
    r = tab.rows[0]
    r.combo_criteria.setCurrentText('Exact')
    r.txt_criteria.setText('abc')
    sql = _build(tab)
    assert "UPPER(TRIM(POLICY1.POL_ISS_ST_CD)) = 'ABC'" in sql

def test_criteria_ignored_when_row_disabled():
    _app()
    tab = CustomDisplayTab()
    _select(tab, 'Seg 01 - LH_BAS_POL', ['APP_WRT_DT'])
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
    _select(tab, 'Seg 01 - LH_BAS_POL', ['APP_WRT_DT'])
    tab.rows[0].combo_criteria.setCurrentText('Contains')
    tab.rows[0].txt_criteria.setText('smith')
    state = tab.get_state()
    restored = CustomDisplayTab()
    restored.set_state(state)
    assert restored.rows[0].combo_criteria.currentText() == 'Contains'
    assert restored.rows[0].txt_criteria.text() == 'smith'
    assert restored.get_criteria_filters() == [('LH_BAS_POL', ['APP_WRT_DT'], 'Contains', 'smith', '')]
