"""Production SQL builders exercised with explicitly restricted effective access."""
import os
from unittest.mock import MagicMock, Mock
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PyQt6.QtWidgets import QApplication, QCheckBox
from suiteview.core import access_control, db2_connection
from suiteview.core.build_env import ReadOnlyDataError, guard_data_writable
from suiteview.core.rates import Rates
from suiteview.core.sql_permissions import guard_query_sql
from suiteview.polview.models import policy_data
from suiteview.polview.models.policy_information import PolicyInformation
from suiteview.audit.cyberlife_criteria import collect_audit_criteria

@pytest.fixture(autouse=True)
def restricted(monkeypatch):
    rights = access_control.EffectiveAccess('RESTRICTED_TEST', 'READER', True, False, False)
    resolver = Mock(return_value=rights)
    monkeypatch.setattr(access_control, 'get_access', resolver)
    monkeypatch.setattr(db2_connection.pyodbc, 'connect', Mock(side_effect=AssertionError('No live database connections')))
    monkeypatch.setattr(db2_connection, 'local_data_enabled', lambda: False)
    with pytest.raises(ReadOnlyDataError):
        guard_data_writable('prove the test is not source-bypassed')
    resolver.reset_mock()
    yield resolver
    assert resolver.call_count > 0
    assert all((call.kwargs == {'refresh': True} for call in resolver.call_args_list))

@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])

@pytest.mark.parametrize('region,schema', [('CKPR', 'DB2TAB'), ('CKAS', 'UNIT')])
def test_policy_information_generates_read_only_header_and_segment_queries(region, schema, monkeypatch):
    manager = MagicMock()
    connection = manager.get_connection.return_value
    cursor = connection.cursor.return_value
    cursor.description = [('CK_CMP_CD',), ('CK_POLICY_NBR',), ('CK_SYS_CD',), ('TCH_POL_ID',)]
    cursor.fetchall.return_value = [('01', 'TEST0001', 'I', 'TEST0001  QXXX')]
    checked_sql = []

    def execute(sql, *parameters):
        guard_query_sql(sql)
        guard_query_sql(sql + ' WITH UR')
        checked_sql.append(sql)
        return cursor
    cursor.execute.side_effect = execute
    monkeypatch.setattr(policy_data, '_ConnectionManager', lambda: manager)
    policy = PolicyInformation('TEST0001', company_code='01', region=region)
    assert policy.exists
    tables = ['LH_BAS_POL', 'TH_BAS_POL', 'LH_COV_PHA', 'LH_SPM_BNF', 'LH_POL_MVRY_VAL', 'LH_COV_INS_RNL_RT', 'LH_POL_TARGET', 'LH_FND_VAL_LOAN', 'FH_FIXED']
    for table in tables:
        assert policy.fetch_table(table)
        assert policy._data.table_error(table) == ''
    assert len(checked_sql) == 1 + len(tables)
    assert all((sql.startswith('WITH DUMBY') for sql in checked_sql))
    assert all((f'FROM {schema}.' in sql for sql in checked_sql))
    assert checked_sql[-1].endswith('ORDER BY ASOF_DT DESC, SEQ_NO DESC')
    connection.commit.assert_not_called()

@pytest.mark.parametrize('kind', ['EPP', 'TPP', 'FLATP', 'MFEE', 'DBD', 'GINT', 'CORR', 'BONUSAV', 'BONUSDUR', 'MTP', 'CTP', 'TBL1CTP', 'TBL1MTP', 'EPU', 'COI', 'SCR', 'BENMTP', 'BENCTP', 'BENCOI', 'BANDSPECS', 'PLNCRD', 'PLNCRG', 'RLNCRD', 'RLNCRG', 'SNETPERIOD', 'RATESPACE', 'COI_SCALE'])
def test_actual_rate_query_builder_runs_under_restricted_access(kind, monkeypatch):
    rates = Rates()
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchall.return_value = [(1,)]
    monkeypatch.setattr(rates, '_get_connection', lambda: connection)
    sql, parameters = rates._create_sql(kind, 'PLAN', issue_age=35, sex='M', rateclass='N', scale=1, band=2, benefit_type='21', state='TX')
    assert sql and parameters
    assert rates._fetch_rates(sql, parameters) == [(1,)]
    cursor.execute.assert_called_once_with(sql, parameters)
    connection.commit.assert_not_called()

@pytest.mark.parametrize('all_display', [False, True])
@pytest.mark.parametrize('region,schema', [('CKPR', 'DB2TAB'), ('CKAS', 'UNIT')])
@pytest.mark.parametrize('transaction_mode', ['independent', 'linked', 'linked_exclude'])
def test_actual_cyberlife_builder_ctes_and_dates_pass_restricted_db2_execution(all_display, region, schema, transaction_mode, app, monkeypatch):
    from suiteview.audit.cyberlife_query import build_cyberlife_sql
    from suiteview.audit.tabs.adv_tab import AdvTab
    from suiteview.audit.tabs.benefits_tab import BenefitsTab
    from suiteview.audit.tabs.coverages_tab import CoveragesTab
    from suiteview.audit.tabs.display_tab import DisplayTab
    from suiteview.audit.tabs.plancode_tab import PlancodeTab
    from suiteview.audit.tabs.policy2_tab import Policy2Tab
    from suiteview.audit.tabs.policy_tab import PolicyTab
    from suiteview.audit.tabs.transaction_tab import TransactionTab
    from suiteview.audit.tabs.wl_tab import WlTab
    display = DisplayTab()
    policy2 = Policy2Tab()
    transaction = TransactionTab()
    wl = WlTab()
    if all_display:
        for check in display.findChildren(QCheckBox):
            check.setChecked(True)
        policy2.txt_term_date_both_lo.setText('2025-01-01')
        policy2.txt_term_last_fin_date_lo.setText('2025-01-01')
        policy2.chk_participating.setChecked(True)
        policy2.list_participating.item(0).setSelected(True)
        wl._select_par()
        transaction.transaction1.transaction_types.setText('SI')
        transaction.transaction2.transaction_types.setText('PR')
        transaction.transaction2.chk_eff_month.setChecked(True)
        transaction.transaction2.chk_eff_day.setChecked(True)
        transaction.transaction2.ranges['gross'][0].setText('0')
        transaction.transaction2.chk_exclude.setChecked(True)
        for panel in (transaction.transaction1, transaction.transaction2):
            for checkbox, choices in panel.reversal_filters.values():
                checkbox.setChecked(True)
                choices.item(0).setSelected(True)
    if transaction_mode != 'independent':
        transaction.transaction2.date_comparisons['entry'].setCurrentText('After Trans1 Eff Date')
        transaction.transaction2.date_comparisons['eff'].setCurrentText('Equal Trans1 Entry Date')
        transaction.transaction2.chk_exclude.setChecked(transaction_mode == 'linked_exclude')
    sql = build_cyberlife_sql(collect_audit_criteria(schema, 'I', '25', policy_tab=PolicyTab(), display_tab=display, policy2_tab=policy2, adv_tab=AdvTab(), coverages_tab=CoveragesTab(), plancode_tab=PlancodeTab(), benefits_tab=BenefitsTab(), transaction_tab=transaction, wl_tab=wl))
    assert 'VARCHAR_FORMAT(' in sql
    if all_display:
        assert 'MONTHS_BETWEEN(' in sql and 'TRUNCATE(' in sql
        assert "DATE('9999-12-31')" in sql and 'CONVERSION_SC' in sql
    if transaction_mode != 'independent':
        assert 'TR2.ENTRY_DT > TR1.ASOF_DT' in sql and 'TR2.ASOF_DT = TR1.ENTRY_DT' in sql
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.description = [('PolicyNumber',)]
    cursor.fetchall.return_value = []
    monkeypatch.setattr(db2_connection.pyodbc, 'connect', Mock(return_value=connection))
    assert db2_connection.DB2Connection(region).execute_query_with_headers_isolated(sql + ' WITH UR') == (['PolicyNumber'], [])
    assert cursor.execute.call_args.args[0].endswith('WITH UR')
    connection.commit.assert_not_called()

@pytest.mark.parametrize('expression', ['CAST(PRM_PAID_TO_DT AS DATE)', 'CAST(POL_PRM_AMT AS DECIMAL(15, 2))', 'DATE(PRM_PAID_TO_DT)', 'TIMESTAMP(PRM_PAID_TO_DT)', 'CAST(PRM_PAID_TO_DT AS TIMESTAMP(6))'])
def test_db2_type_expressions_inside_production_compatibility_cte(expression):
    database = db2_connection.DB2Connection('CKPR')
    sql = database._prepare_sql(f'SELECT {expression} FROM DB2TAB.LH_BAS_POL WHERE CK_POLICY_NBR = ? FETCH FIRST 1 ROWS ONLY WITH UR')
    guard_query_sql(sql)

@pytest.mark.parametrize('method', ['load_interest_rates_for_viewer', 'load_term_rates_for_viewer', 'load_per_diem_for_viewer', 'load_state_variations_for_viewer', 'load_modal_factors_for_viewer', 'load_band_amounts_for_viewer', 'load_policy_fees_for_viewer'])
def test_actual_abr_viewer_queries_pass_restricted_guard(method, monkeypatch):
    from suiteview.abrquote.models.abr_odbc_database import ABROdbcDatabase
    database = ABROdbcDatabase()
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchall.return_value = []

    def execute(sql, *parameters):
        guard_query_sql(sql)
        return cursor
    cursor.execute.side_effect = execute
    monkeypatch.setattr(database, 'connect', lambda: connection)
    headers, rows = getattr(database, method)()
    assert headers and rows == []
    cursor.execute.assert_called_once()
    connection.commit.assert_not_called()
