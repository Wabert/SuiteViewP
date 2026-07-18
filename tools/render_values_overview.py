"""Render the Illustration Values Overview (KPIs + annual/monthly ledger) to PNG.

Runs a real local projection (SUITEVIEW_LOCAL_DATA=1) and grabs the
ValuesOverview widget — the frozen Year|Month|Age|Date pane, the
Contributions/Distributions rollups, and the relocated cash-flow columns after
the spacer — with one year expanded to its monthly rows.

Saves two frames: the resting view and one horizontally scrolled to prove the
freeze pane holds.

Usage:
    venv\\Scripts\\python.exe tools/render_values_overview.py [policy] [months]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["SUITEVIEW_LOCAL_DATA"] = "1"
os.environ.setdefault("QT_QPA_PLATFORM", "windows")


def main() -> None:
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.models.input_set import IllustrationOptions
    from suiteview.illustration.ui.values_overview import ValuesOverview

    policy_number = sys.argv[1] if len(sys.argv) > 1 else "U0688012"
    months = int(sys.argv[2]) if len(sys.argv) > 2 else 120

    clear_cache()
    policy = build_illustration_data(policy_number, region="CKPR", company_code="01")
    options = IllustrationOptions(conform_to_tefra=False, conform_to_tamra=True,
                                  exact_days_interest=True)
    results = IllustrationEngine().project(policy, months=months, options=options)

    overview = ValuesOverview()
    overview.display(policy, results)
    if overview._year_items:
        overview.jump_to_year(min(overview._year_items))  # first year expanded → monthly rows
    # Narrow enough that the value columns overflow — the freeze pane engages.
    overview.resize(1000, 700)
    overview.show()
    app.processEvents()
    app.processEvents()

    out_dir = Path.home() / ".suiteview"
    out_dir.mkdir(parents=True, exist_ok=True)
    resting = out_dir / "values_overview_ledger.png"
    overview.grab().save(str(resting))

    # Scroll the value columns to the far right — the frozen locator pane must
    # hold Year | Month | Age | Date in place.
    scrollbar = overview.ledger.horizontalScrollBar()
    scrollbar.setValue(scrollbar.maximum())
    app.processEvents()
    scrolled = out_dir / "values_overview_ledger_scrolled.png"
    overview.grab().save(str(scrolled))

    print(f"saved {resting}")
    print(f"saved {scrolled}")


if __name__ == "__main__":
    main()
