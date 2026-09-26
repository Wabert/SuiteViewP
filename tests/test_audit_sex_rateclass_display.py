"""Display Sex/Rateclass/Band (67) combined with Coverages rateclass/sex criteria."""
import os
import re
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from suiteview.audit.cyberlife_query import build_cyberlife_sql
from suiteview.audit.tabs.adv_tab import AdvTab
from suiteview.audit.tabs.benefits_tab import BenefitsTab
from suiteview.audit.tabs.coverages_tab import CoveragesTab
from suiteview.audit.tabs.display_tab import DisplayTab
from suiteview.audit.tabs.plancode_tab import PlancodeTab
from suiteview.audit.tabs.policy2_tab import Policy2Tab
from suiteview.audit.tabs.policy_tab import PolicyTab
from tests.audit_criteria_helpers import collect_audit_criteria

def _build(display, coverages, coverage_level=False):
    return build_cyberlife_sql(collect_audit_criteria('DB2TAB', 'I', '25', policy_tab=PolicyTab(), display_tab=display, policy2_tab=Policy2Tab(), adv_tab=AdvTab(), coverages_tab=coverages, plancode_tab=PlancodeTab(), benefits_tab=BenefitsTab(), coverage_level=coverage_level))

def _alias_count(sql, alias):
    return len(re.findall(f'LH_COV_INS_RNL_RT {alias}\\b', sql))

@pytest.mark.parametrize('criterion', ['sex_code_67', 'rateclass'])
def test_display_with_criterion_joins_renewals_once(qtbot, criterion):
    display, coverages = (DisplayTab(), CoveragesTab())
    qtbot.addWidget(display)
    qtbot.addWidget(coverages)
    display.chk_disp_sex_rateclass.setChecked(True)
    coverages.base_cov_widgets[criterion].setCurrentIndex(1)
    sql = _build(display, coverages)
    assert _alias_count(sql, 'COV1_RENEWALS') == 1
    assert 'INNER JOIN DB2TAB.LH_COV_INS_RNL_RT COV1_RENEWALS' in sql
    assert 'COV1_RENEWALS.RT_BAN_CD RenewalBand' in sql

def test_display_only_uses_left_join(qtbot):
    display, coverages = (DisplayTab(), CoveragesTab())
    qtbot.addWidget(display)
    qtbot.addWidget(coverages)
    display.chk_disp_sex_rateclass.setChecked(True)
    sql = _build(display, coverages)
    assert _alias_count(sql, 'COV1_RENEWALS') == 1
    assert 'LEFT OUTER JOIN DB2TAB.LH_COV_INS_RNL_RT COV1_RENEWALS' in sql

def test_coverage_level_uses_result_coverage_alias(qtbot):
    display, coverages = (DisplayTab(), CoveragesTab())
    qtbot.addWidget(display)
    qtbot.addWidget(coverages)
    display.chk_disp_sex_rateclass.setChecked(True)
    coverages.base_cov_widgets['sex_code_67'].setCurrentIndex(1)
    sql = _build(display, coverages, coverage_level=True)
    assert _alias_count(sql, 'COV1_RENEWALS') == 1
    assert _alias_count(sql, 'RESULTCOV_RENEWALS') == 1
