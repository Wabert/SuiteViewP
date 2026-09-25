"""Save a Policy (2) preview and synthetic DB2 SQL for termination-date checks."""
import argparse
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PyQt6.QtWidgets import QApplication
from suiteview.audit.cyberlife_query import build_cyberlife_sql, termination_financial_date
from suiteview.audit.sql_helpers import esc
from suiteview.audit.tabs.adv_tab import AdvTab
from suiteview.audit.tabs.benefits_tab import BenefitsTab
from suiteview.audit.tabs.coverages_tab import CoveragesTab
from suiteview.audit.tabs.display_tab import DisplayTab
from suiteview.audit.tabs.plancode_tab import PlancodeTab
from suiteview.audit.tabs.policy2_tab import Policy2Tab
from suiteview.audit.tabs.policy_tab import PolicyTab
from suiteview.audit.tabs.transaction_tab import TransactionTab
from suiteview.audit.cyberlife_criteria import collect_audit_criteria

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_dir', type=Path)
    parser.add_argument('--policy', help='Optional exact policy for a bounded regression query.')
    parser.add_argument('--company', help='Company required with --policy.')
    args = parser.parse_args()
    if bool(args.policy) != bool(args.company):
        parser.error('--policy and --company must be supplied together')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    tab = Policy2Tab()
    tab.txt_term_date_both_lo.setText('2025-01-01')
    tab.txt_term_date_both_hi.setText('2025-12-31')
    sql = build_cyberlife_sql(collect_audit_criteria('DB2TAB', 'I', '25', policy_tab=PolicyTab(), policy2_tab=tab, display_tab=DisplayTab(), adv_tab=AdvTab(), coverages_tab=CoveragesTab(), plancode_tab=PlancodeTab(), benefits_tab=BenefitsTab(), transaction_tab=TransactionTab()))
    (args.output_dir / 'both-query-preview.sql').write_text(sql, encoding='utf-8')
    if args.policy:
        policy_sql = sql.rsplit('\nFETCH FIRST', 1)[0] + f"\nAND POLICY1.CK_POLICY_NBR = '{esc(args.policy)}'" + f"\nAND POLICY1.CK_CMP_CD = '{esc(args.company)}'" + '\nFETCH FIRST 25 ROWS ONLY\nWITH UR\n'
        (args.output_dir / 'policy-regression.sql').write_text(policy_sql, encoding='utf-8')
    compile_sql = sql.rsplit('\nFETCH FIRST', 1)[0] + '\nAND 1 = 0\nFETCH FIRST 1 ROW ONLY\nWITH UR\n'
    (args.output_dir / 'both-schema-check.sql').write_text(compile_sql, encoding='utf-8')
    tab.resize(1210, 596)
    tab.show()
    app.processEvents()
    if not tab.grab().save(str(args.output_dir / 'policy2-termination-controls.png'), 'PNG'):
        raise RuntimeError('Could not save Policy (2) preview.')
    cases = [('transaction_wins', '01', 1, '99', 'Q', '2025-02-01', '2025-03-01', 1), ('outside_no_fallback', '01', 2, '99', 'P', '2025-02-01', '2024-03-01', 0), ('missing_fallback', '01', 3, '98', 'J', '2025-04-01', '2025-04-01', 1), ('pending_fallback', '01', 4, '97', 'Q', '2025-05-01', '2025-05-01', 1), ('active_no_fallback', '01', 5, '22', 'Q', '2025-06-01', None, 0), ('nonterm_no_fallback', '01', 6, '99', 'C', '2025-06-01', None, 0), ('sentinel_no_fallback', '01', 7, '99', 'L', '9999-12-31', None, 0), ('reversed_fallback', '01', 8, '99', 'P', '2025-07-01', '2025-07-01', 1), ('latest_valid_tx', '01', 9, '99', 'Q', '2024-01-01', '2025-12-31', 1), ('lower_inclusive', '01', 10, '99', 'Q', '2025-01-01', '2025-01-01', 1), ('same_key_other_company', '26', 1, '99', 'Q', '2025-08-01', '2025-08-01', 1), ('active_rider_SC', '01', 11, '22', 'C', '2026-09-08', None, 0), ('null_financial', '01', 12, '99', 'Q', None, None, 0), ('sentinel_tx_fallback', '01', 13, '99', 'R', '2025-10-01', '2025-10-01', 1), ('applied_rev_fallback', '01', 14, '99', 'N', '2025-11-01', '2025-11-01', 1)]
    for number, code in enumerate(('J', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'X'), 20):
        cases.append((f'code_{code}', '01', number, '99', code, '2025-06-15', '2025-06-15', 1))

    def date_sql(value):
        return f"DATE('{value}')" if value else 'CAST(NULL AS DATE)'
    raw_trans = [(1, 'TL', '2025-03-01', '0', '0'), (2, 'SF', '2024-03-01', '0', '0'), (8, 'SF', '2024-01-01', '1', '0'), (9, 'TL', '2024-01-01', '0', '0'), (9, 'SI', '2025-12-31', '0', '0'), (9, 'TL', '9999-12-31', '0', '0'), (11, 'SC', '2025-04-03', '0', '0'), (13, 'TM', '9999-12-31', '0', '0'), (14, 'TN', '2024-01-01', '0', '1')]
    for number, code in enumerate(('SC', 'SI', 'SF', 'TD', 'TM', 'TN', 'TL', 'TO'), 40):
        cases.append((f'active_{code}', '01', number, '22', 'Q', '2025-06-15', None, 0))
        raw_trans.append((number, code, '2025-06-15', '0', '0'))
    cases.append(('nonterm_with_tx', '01', 60, '99', 'C', '2025-06-15', None, 0))
    raw_trans.append((60, 'SF', '2025-06-15', '0', '0'))
    policy_values = '\nUNION ALL\n'.join((f"SELECT '{name}', '{company}', {key}, '{status}', '{code}', {date_sql(financial)}, {date_sql(expected)}, {matched} FROM SYSIBM.SYSDUMMY1" for name, company, key, status, code, financial, expected, matched in cases))
    trans_values = '\nUNION ALL\n'.join((f"SELECT '01', {key}, '{code}', DATE('{entry}'), DATE('2020-01-01'), '{rev}', '{applied}' FROM SYSIBM.SYSDUMMY1" for key, code, entry, rev, applied in raw_trans))
    trans_cte = sql.split(', TERMINATION_TRANS AS\n', 1)[1].split(', PRE_TERMINATION_DATES AS', 1)[0].replace('DB2TAB.FH_FIXED', 'RAW_TRANS').strip()
    both_match = re.search(', TERMINATION_BOTH_DATES AS\\n(.*?\\n   GROUP BY CK_CMP_CD, TCH_POL_ID\\))', sql, re.DOTALL)
    if both_match is None:
        raise RuntimeError('Generated SQL is missing the combined-date CTE.')
    resolved_date = f'COALESCE(TDB.TERM_ENTRY_DT, {termination_financial_date()})'
    join_match = re.search('  LEFT OUTER JOIN TERMINATION_BOTH_DATES AS TDB\\n    ON POLICY1.CK_CMP_CD = TDB.CK_CMP_CD\\n    AND POLICY1.TCH_POL_ID = TDB.TCH_POL_ID(?:\\n    AND [^\\n]+)*', sql)
    if join_match is None:
        raise RuntimeError('Generated SQL is missing the combined-date join.')
    fixture = f"WITH POLICIES\n(CASE_NAME, CK_CMP_CD, TCH_POL_ID, PRM_PAY_STA_REA_CD, LST_ETR_CD,\n LST_FIN_DT, EXPECTED_DT, EXPECTED_MATCH) AS (\n{policy_values}),\nRAW_TRANS\n(CK_CMP_CD, TCH_POL_ID, TRANS, ENTRY_DT, ASOF_DT, FCB0_REV_IND, FCB2_REV_APPL_IND)\nAS (\n{trans_values}),\nTERMINATION_TRANS AS\n{trans_cte},\nTERMINATION_BOTH_DATES AS\n{both_match.group(1)},\nRESOLVED AS (\n SELECT POLICY1.CASE_NAME, POLICY1.EXPECTED_DT, POLICY1.EXPECTED_MATCH,\n {resolved_date} AS ACTUAL_DT\n FROM POLICIES POLICY1\n{join_match.group(0)}\n),\nCHECKED AS (\n SELECT RESOLVED.*,\n CASE WHEN ACTUAL_DT >= DATE('2025-01-01') AND ACTUAL_DT <= DATE('2025-12-31')\n THEN 1 ELSE 0 END AS ACTUAL_MATCH\n FROM RESOLVED\n)\nSELECT COUNT(*) AS TEST_COUNT,\n SUM(CASE WHEN (ACTUAL_DT = EXPECTED_DT OR (ACTUAL_DT IS NULL AND EXPECTED_DT IS NULL))\n AND ACTUAL_MATCH = EXPECTED_MATCH THEN 1 ELSE 0 END) AS PASS_COUNT\nFROM CHECKED\nFETCH FIRST 1 ROW ONLY\nWITH UR\n"
    (args.output_dir / 'synthetic-termination-check.sql').write_text(fixture, encoding='utf-8')
    tab.close()
    print(json.dumps({'output_dir': str(args.output_dir), 'synthetic_cases': len(cases)}))
if __name__ == '__main__':
    main()
