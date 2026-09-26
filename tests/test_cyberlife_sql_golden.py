"""Characterization tests for CyberLife audit SQL generation."""
from __future__ import annotations

from pathlib import Path

import pytest

from suiteview.audit import sql_helpers
from suiteview.audit.cyberlife_criteria import collect_audit_criteria
from suiteview.audit.cyberlife_query import build_cyberlife_sql
from suiteview.audit.cyberlife_sql import (
    ctes_values,
    select_policy,
    where_advanced,
    where_policy,
)
from tests.cyberlife_sql_cases import CASES, CyberlifeSqlCase, make_tabs

GOLDEN_DIR = Path(__file__).parent / "golden" / "cyberlife_sql"
GOLDEN_TODAY = "2026-09-25"


def render_case(case: CyberlifeSqlCase) -> str:
    tabs = make_tabs()
    case.configure(tabs)
    return build_cyberlife_sql(
        collect_audit_criteria(
            case.schema,
            case.sys_code,
            case.max_count_text,
            coverage_level=case.coverage_level,
            coverage_scope=case.coverage_scope,
            **tabs,
        )
    )


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_cyberlife_sql_matches_golden(monkeypatch, case: CyberlifeSqlCase) -> None:
    for module in (sql_helpers, ctes_values, select_policy, where_advanced, where_policy):
        monkeypatch.setattr(module, "today_str", lambda: GOLDEN_TODAY)
    assert render_case(case) == (GOLDEN_DIR / f"{case.name}.sql").read_text()
