"""Characterization tests for CyberLife audit SQL generation."""
from __future__ import annotations
from pathlib import Path
import pytest
from suiteview.audit.cyberlife_sql import ctes_values, select_policy, where_advanced, where_policy
from suiteview.audit.cyberlife_query import build_cyberlife_sql
from tests.cyberlife_sql_cases import CASES, CyberlifeSqlCase, make_tabs
from suiteview.audit.cyberlife_criteria import collect_audit_criteria
GOLDEN_DIR = Path(__file__).parent / 'golden' / 'cyberlife_sql'
GOLDEN_TODAY = "2026-09-25"


@pytest.fixture(autouse=True)
def _freeze_golden_today(monkeypatch):
    for module in (ctes_values, select_policy, where_advanced, where_policy):
        monkeypatch.setattr(module, "today_str", lambda: GOLDEN_TODAY)

def render_case(case: CyberlifeSqlCase) -> str:
    tabs = make_tabs()
    case.configure(tabs)
    return build_cyberlife_sql(collect_audit_criteria(case.schema, case.sys_code, case.max_count_text, coverage_level=case.coverage_level, coverage_scope=case.coverage_scope, **tabs))

@pytest.mark.parametrize('case', CASES, ids=[case.name for case in CASES])
def test_cyberlife_sql_matches_golden(case: CyberlifeSqlCase) -> None:
    assert render_case(case) == (GOLDEN_DIR / f'{case.name}.sql').read_text()
