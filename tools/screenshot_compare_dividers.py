"""Render the Illustration Compare tab with stub data and save a PNG so the
pink divider fill (delegate paint) can be eyeballed.

Verifies the fix for the QSS-suppressed separator background: the ledger-style
stylesheet ignores the model BackgroundRole, so the divider is painted by a
delegate instead. Renders two- and three-scenario ledgers.

Usage:
    venv\\Scripts\\python.exe tools/screenshot_compare_dividers.py
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

OUT_DIR = Path(os.environ.get("TEMP", str(ROOT))) / "compare_divider_shots"


def _run(years: int, premium: float, av: float):
    from suiteview.illustration.models.calc_state import MonthlyState

    rows = [MonthlyState(date=date(2026, 1, 1), policy_year=0, policy_month=0,
                         attained_age=44)]
    for year in range(1, years + 1):
        rows.append(MonthlyState(
            date=date(2026, 1, 1), policy_year=year, policy_month=12,
            attained_age=44 + year, gross_premium=premium,
            av_end_of_month=av + 1000.0 * year,
            ending_sv=av - 1000.0 + 1000.0 * year, ending_db=90_000.0))
    return rows


def main() -> None:
    from PyQt6.QtWidgets import QApplication
    from suiteview.illustration.core.compare_runner import (
        ComparisonResult, ScenarioOutcome, build_comparison_ledger, build_kpi_rows,
    )
    from suiteview.illustration.ui.compare_tab import IllustrationCompareTab

    app = QApplication.instance() or QApplication([])  # noqa: F841
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    def outcome(label, results):
        return ScenarioOutcome(
            label=label, results=results,
            policy=SimpleNamespace(is_mec=False))

    cases = {
        "compare_two.png": [
            outcome("01-UE000576 - MD Prems", _run(20, 600.0, 12_000.0)),
            outcome("01-UE000576 - 07/19/2026", _run(20, 1800.0, 12_000.0)),
        ],
        "compare_three.png": [
            outcome("Current Inputs", _run(20, 600.0, 12_000.0)),
            outcome("Opt A", _run(20, 1200.0, 12_000.0)),
            outcome("Opt B", _run(20, 1800.0, 12_000.0)),
        ],
    }

    for filename, outcomes in cases.items():
        result = ComparisonResult(
            outcomes=outcomes, kpis=build_kpi_rows(outcomes),
            ledger=build_comparison_ledger(outcomes))
        tab = IllustrationCompareTab()
        tab.resize(900, 520)
        tab.populate_comparison(result)
        tab.ledger_view.resize(880, 460)
        app.processEvents()
        path = OUT_DIR / filename
        tab.grab().save(str(path))
        print(f"saved {path}")


if __name__ == "__main__":
    main()
