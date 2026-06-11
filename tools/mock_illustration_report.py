"""Render the Illustration Report tab from a real local-data projection.

Runs U0688012 with the validated force-out scenario (over-funded premium +
year-9 face decrease) so the ledger markers, footnotes, and policy-change
sections all fire, then saves the rendered pages to
~/.suiteview/mock_illustration_report.png for inspection.

Usage:
    venv\\Scripts\\python.exe tools/mock_illustration_report.py
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["SUITEVIEW_LOCAL_DATA"] = "1"
# Render on the native platform — offscreen falls back to box glyphs for
# the monospace font. The widget is grabbed without being shown on screen.


def main() -> None:
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.core.report_builder import build_ul_report
    from suiteview.illustration.models.input_set import (
        IllustrationInputSet, IllustrationOptions, PolicyChangeEvent,
        PolicyChangeKind, ScheduledTransaction, TransactionKind,
    )
    from suiteview.illustration.ui.report_tab import IllustrationReportTab

    clear_cache()
    policy = build_illustration_data("U0688012", region="CKPR", company_code="01")
    future = IllustrationInputSet(
        scheduled_transactions=[
            ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=1,
                                 amount=25000.0, mode="A"),
        ],
        policy_changes=[
            PolicyChangeEvent(kind=PolicyChangeKind.FACE_AMOUNT,
                              effective_date=date(2027, 11, 9), value=75000.0),
        ],
    )
    options = IllustrationOptions(conform_to_tefra=True, conform_to_tamra=True,
                                  exact_days_interest=True)
    results = IllustrationEngine().project(
        policy, months=90, options=options, future_inputs=future)

    report = build_ul_report(policy, results, options=options,
                             future_inputs=future, run_date=date(2026, 6, 10))
    tab = IllustrationReportTab()
    tab.display_report(report)
    tab.resize(1000, 1400)
    tab._sheet_host.adjustSize()
    app.processEvents()

    out = Path.home() / ".suiteview" / "mock_illustration_report.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    tab._sheet_host.grab().save(str(out))
    print(f"pages={len(report.ledger)} ledger rows; saved {out}")


if __name__ == "__main__":
    main()
