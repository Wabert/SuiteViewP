"""Read-only live check of the Query ADV Decrease Charge Rule filter.

For each selection (0, 1, Blank) this builds the real Query SQL with a small
Max Count, executes it, and independently re-reads TH_NON_TRD_POL for every
returned policy to confirm its DECR_CHRG_ALLOW matches the selection.
Reports counts and checks only; writes nothing.

Usage:
    venv\\Scripts\\python.exe tools/audit/verify_decrease_charge_rule_filter.py
        [--region CKPR] [--max-count 25]
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from suiteview.core.db2_connection import DB2Connection
from suiteview.core.db2_constants import DEFAULT_SCHEMA, REGION_DSN_MAP, REGION_SCHEMA_MAP
from suiteview.core.local_dev import local_data_enabled
from suiteview.audit.cyberlife_tab_collect import collect_cyberlife_tabs
_SELECTIONS = {'0': [0], '1': [1], 'Blank': [2]}

def _matches(selection: str, value) -> bool:
    if selection == 'Blank':
        return value is None or str(value) not in ('0', '1')
    return str(value) == selection

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region', choices=sorted(REGION_DSN_MAP), default='CKPR')
    parser.add_argument('--max-count', default='25')
    args = parser.parse_args()
    if local_data_enabled():
        raise RuntimeError('Decrease Charge Rule verification requires live DB2.')
    from PyQt6.QtWidgets import QApplication
    from suiteview.audit.cyberlife_query import build_cyberlife_sql
    from suiteview.audit.tabs.adv_tab import AdvTab
    from suiteview.audit.tabs.benefits_tab import BenefitsTab
    from suiteview.audit.tabs.coverages_tab import CoveragesTab
    from suiteview.audit.tabs.display_tab import DisplayTab
    from suiteview.audit.tabs.plancode_tab import PlancodeTab
    from suiteview.audit.tabs.policy2_tab import Policy2Tab
    from suiteview.audit.tabs.policy_tab import PolicyTab
    app = QApplication.instance() or QApplication([])
    schema = REGION_SCHEMA_MAP.get(args.region, DEFAULT_SCHEMA)
    db = DB2Connection(args.region)
    output: dict = {'region': args.region, 'selections': {}}
    try:
        for selection, rows in _SELECTIONS.items():
            tabs = dict(policy_tab=PolicyTab(), display_tab=DisplayTab(), policy2_tab=Policy2Tab(), adv_tab=AdvTab(), coverages_tab=CoveragesTab(), plancode_tab=PlancodeTab(), benefits_tab=BenefitsTab())
            adv = tabs['adv_tab']
            adv.chk_decr_chrg_rule.setChecked(True)
            for row in rows:
                adv.list_decr_chrg_rule.item(row).setSelected(True)
            sql = build_cyberlife_sql(collect_cyberlife_tabs(schema, 'I', args.max_count, tabs))
            columns, results = db.execute_query_with_headers(sql)
            upper = [c.upper() for c in columns]
            pol_col = next((i for i, c in enumerate(upper) if c in ('POLICYNUMBER', 'CK_POLICY_NBR', 'POLICY')))
            cmp_col = next((i for i, c in enumerate(upper) if c in ('COMPANY', 'CK_CMP_CD', 'COMPANYCODE')))
            mismatches = 0
            for result in results:
                _, values = db.execute_query_with_headers_isolated(f"SELECT T.DECR_CHRG_ALLOW FROM {schema}.LH_BAS_POL P INNER JOIN {schema}.TH_NON_TRD_POL T ON T.CK_SYS_CD = P.CK_SYS_CD AND T.CK_CMP_CD = P.CK_CMP_CD AND T.TCH_POL_ID = P.TCH_POL_ID WHERE P.CK_SYS_CD = 'I' AND P.CK_CMP_CD = '" + str(result[cmp_col]).strip().replace("'", "''") + "' AND P.CK_POLICY_NBR = '" + str(result[pol_col]).strip().replace("'", "''") + "'")
                if not values or not all((_matches(selection, v[0]) for v in values)):
                    mismatches += 1
            output['selections'][selection] = {'rows': len(results), 'mismatches': mismatches, 'ok': bool(results) and mismatches == 0}
            for widget in tabs.values():
                widget.close()
                widget.deleteLater()
            app.processEvents()
    finally:
        db.close()
    output['all_ok'] = all((item['ok'] for item in output['selections'].values()))
    print(json.dumps(output, indent=2))
    return 0 if output['all_ok'] else 1
if __name__ == '__main__':
    raise SystemExit(main())
