"""Characterization tests for CyberLife audit SQL generation."""
from __future__ import annotations
from datetime import date
from pathlib import Path
import pytest
from suiteview.audit import sql_helpers
from suiteview.audit.cyberlife_query import build_cyberlife_sql
from tests.cyberlife_sql_cases import CASES, CyberlifeSqlCase, make_tabs
from suiteview.audit.cyberlife_criteria import collect_audit_criteria
GOLDEN_DIR = Path(__file__).parent / 'golden' / 'cyberlife_sql'
# Goldens were captured on this date; pinning it keeps them independent of the clock.
GOLDEN_AS_OF = date(2026, 9, 25)


class _GoldenDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 25)


@pytest.fixture(autouse=True)
def _freeze_golden_sql_today(monkeypatch):
    monkeypatch.setattr(sql_helpers, "date", _GoldenDate)


def render_case(case: CyberlifeSqlCase) -> str:
    tabs = make_tabs()
    case.configure(tabs)
    return build_cyberlife_sql(collect_audit_criteria(case.schema, case.sys_code, case.max_count_text, coverage_level=case.coverage_level, coverage_scope=case.coverage_scope, as_of=GOLDEN_AS_OF, **tabs))

@pytest.mark.parametrize('case', CASES, ids=[case.name for case in CASES])
def test_cyberlife_sql_matches_golden(case: CyberlifeSqlCase) -> None:
    assert render_case(case) == (GOLDEN_DIR / f'{case.name}.sql').read_text()

def test_sql_uses_the_collected_as_of_date_everywhere() -> None:
    case = next(c for c in CASES if c.name == 'display_all')
    tabs = make_tabs()
    case.configure(tabs)
    sql = build_cyberlife_sql(collect_audit_criteria(
        case.schema, case.sys_code, case.max_count_text,
        coverage_level=case.coverage_level, coverage_scope=case.coverage_scope,
        as_of=date(2031, 2, 3), **tabs))
    assert "'2031-02-03'" in sql
    assert "'2026-09-25'" not in sql
