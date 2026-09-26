"""Characterization tests for CyberLife audit SQL generation."""
from __future__ import annotations
from datetime import date
from pathlib import Path
import pytest
from suiteview.audit.cyberlife_query import build_cyberlife_sql
from tests.cyberlife_sql_cases import CASES, CyberlifeSqlCase, make_tabs
from suiteview.audit.cyberlife_criteria import AuditCriteriaBundle, CriteriaCollector
GOLDEN_DIR = Path(__file__).parent / 'golden' / 'cyberlife_sql'
# Goldens were captured on this date; pinning it keeps them independent of the clock.
GOLDEN_AS_OF = date(2026, 9, 25)


def render_case(case: CyberlifeSqlCase) -> str:
    tabs = make_tabs()
    case.configure(tabs)
    return build_cyberlife_sql(_collect_case(case, tabs, GOLDEN_AS_OF))


def _collect_case(case: CyberlifeSqlCase, tabs: dict[str, object], as_of: date):
    return CriteriaCollector(AuditCriteriaBundle(
        schema=case.schema,
        sys_code=case.sys_code,
        max_count_text=case.max_count_text,
        coverage_level=case.coverage_level,
        coverage_scope=case.coverage_scope,
        as_of=as_of,
        tabs={
            "policy": tabs["policy_tab"],
            "display": tabs["display_tab"],
            "policy2": tabs["policy2_tab"],
            "adv": tabs["adv_tab"],
            "coverages": tabs["coverages_tab"],
            "plancode": tabs["plancode_tab"],
            "benefits": tabs["benefits_tab"],
            "transaction": tabs["transaction_tab"],
            "custom_display": tabs["custom_display_tab"],
            "people": tabs["people_tab"],
            "segment52": tabs["segment52_tab"],
            "wl": tabs["wl_tab"],
        },
    )).collect()

@pytest.mark.parametrize('case', CASES, ids=[case.name for case in CASES])
def test_cyberlife_sql_matches_golden(case: CyberlifeSqlCase) -> None:
    assert render_case(case) == (GOLDEN_DIR / f'{case.name}.sql').read_text()

def test_sql_uses_the_collected_as_of_date_everywhere() -> None:
    case = next(c for c in CASES if c.name == 'display_all')
    tabs = make_tabs()
    case.configure(tabs)
    sql = build_cyberlife_sql(_collect_case(case, tabs, date(2031, 2, 3)))
    assert "'2031-02-03'" in sql
    assert "'2026-09-25'" not in sql
