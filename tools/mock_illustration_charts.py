"""Render the Illustration value + accumulated-charges charts from local data.

Saves ~/.suiteview/mock_illustration_charts.png for inspection.

Usage:
    venv\\Scripts\\python.exe tools/mock_illustration_charts.py [synthetic-debt]

Pass ``synthetic-debt`` to inject a growing loan balance into the projected
states (display-layer check of the conditional Policy Debt chart series).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["SUITEVIEW_LOCAL_DATA"] = "1"


def main() -> None:
    from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

    app = QApplication.instance() or QApplication(sys.argv)

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.models.input_set import IllustrationOptions
    from suiteview.illustration.ui.values_overview import (
        AccumulatedChargesChart, PolicyValueChart, build_charge_bands, build_chart_series,
    )

    clear_cache()
    policy = build_illustration_data("U0688012", region="CKPR", company_code="01")
    options = IllustrationOptions(conform_to_tefra=False, conform_to_tamra=True,
                                  exact_days_interest=True)
    results = IllustrationEngine().project(policy, months=120, options=options)

    if "synthetic-debt" in sys.argv[1:]:
        # Fake a loan taken in year 3 growing at ~6%/yr — verifies the
        # conditional Policy Debt series renders (color, legend chip, hover).
        for index, state in enumerate(results[1:], start=0):
            state.policy_debt = 2_000.0 * 1.06 ** (index / 12.0) if index >= 24 else 0.0

    host = QWidget()
    host.setStyleSheet("background-color: #EDE7F6;")
    layout = QVBoxLayout(host)
    chart = PolicyValueChart()
    chart.set_data(build_chart_series(results[1:]), policy.issue_age)
    chart.setMinimumHeight(300)
    layout.addWidget(chart)
    charges = AccumulatedChargesChart()
    charges.set_data(build_charge_bands(results[1:]), policy.issue_age)
    charges.setMinimumHeight(300)
    layout.addWidget(charges)
    host.resize(980, 640)
    app.processEvents()

    out = Path.home() / ".suiteview" / "mock_illustration_charts.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    host.grab().save(str(out))
    print(f"saved {out}")


if __name__ == "__main__":
    main()
