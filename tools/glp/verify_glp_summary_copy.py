"""Verify the GLP Exception Calculation Summary clipboard-copy format.

Builds synthetic forecast results and exercises the real
``PolicySupportTab`` summary/copy helpers (constructed via ``__new__`` to skip
the Qt widget setup) so we can confirm the plain-text block matches the
requested format without launching the desktop app.

Usage:
    venv\\Scripts\\python.exe tools/glp/verify_glp_summary_copy.py
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from suiteview.polview.ui.tabs.policy_support_tab import PolicySupportTab
from suiteview.polview.services.guideline_exception_adjustment import (
    GuidelineExceptionAdjustmentResult,
    GuidelineExceptionZeroGlpForecastResult,
    GuidelineExceptionForecastRow,
    GuidelineExceptionTargetForecastResult,
)


def _row(d: date, premium: float) -> GuidelineExceptionForecastRow:
    return GuidelineExceptionForecastRow(
        date=d,
        policy_year=1,
        policy_month=1,
        interest_credited=0.0,
        premium=premium,
        monthly_deduction=0.0,
        account_value=0.0,
        glp=0.0,
        accumulated_glp=0.0,
        premiums_to_date=0.0,
        accumulated_withdrawals=0.0,
        force_out=0.0,
        exception_premium=0.0,
        in_exception_mode=True,
        policy_debt=0.0,
    )


def _make_result(current_glp: float) -> GuidelineExceptionTargetForecastResult:
    target = date(2027, 3, 15)
    summary = GuidelineExceptionAdjustmentResult(
        current_valuation_date=date(2026, 3, 15),
        target_date=target,
        months_to_target=12,
        total_premium_needed=1500.00,
        room_available=0.0,
        accumulated_glp=8000.00,          # current Accum GLP (FROM value)
        premiums_paid_to_date=48765.43,
        accumulated_withdrawals=1234.56,
        adjustment_to_accum_glp=41030.87,
        new_accum_glp=49030.87,
        message="",
    )
    # Three months before target are included in both table and summary.
    rows = [
        _row(date(2026, 12, 15), 500.00),
        _row(date(2027, 1, 15), 500.00),
        _row(date(2027, 2, 15), 500.00),
    ]
    zero_glp = GuidelineExceptionZeroGlpForecastResult(
        summary=summary, rows=rows, premium=500.0, premium_mode="M",
        exception_start=date(2026, 12, 15))
    return GuidelineExceptionTargetForecastResult(
        premium=1200.0,
        premium_mode="Annual",
        exception_start=date(2026, 12, 15),
        rows=rows,
        zero_glp=zero_glp,
        no_forceout=replace(
            zero_glp, premium=0.0, rows=[],
            summary=replace(summary, total_premium_needed=0.0)),
        current_glp=current_glp,
    )


class _StubField:
    def __init__(self, text: str):
        self._text = text

    def text(self) -> str:
        return self._text


def _copy_text(result, target_text: str) -> str:
    tab = PolicySupportTab.__new__(PolicySupportTab)
    tab._glp_result = result
    tab._glp_target_date = _StubField(target_text)
    return tab._glp_summary_copy_text()


def main() -> None:
    cases = {}

    # GLP not already zero -> include "New GLP = 0" and "AND GLP TO 0.00".
    r1 = _make_result(current_glp=6543.21)
    cases["glp_not_zero"] = _copy_text(r1, "03/15/2027")

    # GLP already zero -> omit "New GLP = 0" and the "AND GLP TO 0.00" clause.
    r2 = _make_result(current_glp=0.0)
    cases["glp_zero"] = _copy_text(r2, "03/15/2027")

    # No exception premium required.
    r3 = _make_result(current_glp=100.0)
    r3.exception_start = None
    cases["no_exception"] = _copy_text(r3, "03/15/2027")

    cases["all_ok"] = (
        "New GLP = 0" in cases["glp_not_zero"]
        and "AND GLP TO 0.00" in cases["glp_not_zero"]
        and "New GLP = 0" not in cases["glp_zero"]
        and "AND GLP TO 0.00" not in cases["glp_zero"]
        and "Premium to get to 03/15/2027 = 1,500.00" in cases["glp_zero"]
        and "DO NOT ADJUST" in cases["no_exception"]
    )
    print(json.dumps(cases, indent=2))
    if not cases["all_ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
