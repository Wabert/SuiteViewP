"""Render the Illustration Values tab header's Current | Guaranteed toggle.

Builds an IllustrationValuesTab from synthetic states (no engine, no DB),
attaches a guaranteed run so the segmented pair appears, and saves two frames:
the default Current Values view and the Guaranteed Values view.

Usage:
    venv\\Scripts\\python.exe tools/render_values_tab_toggle.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "windows")


def main() -> None:
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    from suiteview.illustration.models.calc_state import MonthlyState
    from suiteview.illustration.models.policy_data import (
        CoverageSegment,
        IllustrationPolicyData,
    )
    from suiteview.illustration.ui.values_tab import IllustrationValuesTab

    policy = IllustrationPolicyData(
        face_amount=150000, segments=[CoverageSegment(face_amount=150000)])

    def state(month: int, eav: float) -> MonthlyState:
        return MonthlyState(
            policy_year=1, policy_month=month, attained_age=45,
            av_after_premium=10000, standard_db=150000, gross_db=150000,
            av_end_of_month=eav,
        )

    tab = IllustrationValuesTab()
    tab.display_projection(policy, [state(1, 9990.0), state(2, 9980.0)], months=2)
    tab.set_guaranteed_results(policy, [state(1, 8100.0), state(2, 8050.0)])
    tab.resize(1200, 640)
    tab.show()
    app.processEvents()

    out_dir = Path.home() / ".suiteview"
    out_dir.mkdir(parents=True, exist_ok=True)
    current_png = out_dir / "values_tab_toggle_current.png"
    tab.grab().save(str(current_png))

    tab.guaranteed_toggle.setChecked(True)
    app.processEvents()
    guaranteed_png = out_dir / "values_tab_toggle_guaranteed.png"
    tab.grab().save(str(guaranteed_png))

    print(f"saved {current_png}")
    print(f"saved {guaranteed_png}")


if __name__ == "__main__":
    main()
