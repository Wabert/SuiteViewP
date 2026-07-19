"""Render the Illustration Input tab with a "Solve" premium row selected —
shows the Premium Solve criteria group under the Premiums rows — and with the
Max Level caveat banner active at the bottom (under Riders and Benefits).

Saves ~/.suiteview/mock_premium_solve_group.png and
      ~/.suiteview/mock_max_level_caveat.png.

Usage:
    venv\\Scripts\\python.exe tools/mock_premium_solve_group.py
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
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    from suiteview.core.policy_service import clear_cache, get_policy_info
    from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab

    clear_cache()
    policy_info = get_policy_info("U0656998", region="CKPR")
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(policy_info)
    panel = tab.dynamic_panel

    out_dir = Path.home() / ".suiteview"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) Solve premium type → the criteria group under the Premiums rows.
    row = panel.premium_section.rows()[0]
    row.type_combo.setCurrentText("Solve")
    panel.solve_amount_edit.set_value(100_000, decimals=2)
    panel.solve_age_edit.set_value(100)
    tab.resize(1240, 780)
    tab.show()
    app.processEvents()
    tab.grab().save(str(out_dir / "mock_premium_solve_group.png"))

    # 2) Max Level + face change after the forecast date → caveat banner at
    #    the bottom, under Riders and Benefits.
    row.type_combo.setCurrentText("Max Level Allowed")
    face_row = panel.face_section.rows()[0]
    face_row.year_edit.set_value(int(panel._ctx.forecast_year) + 3)
    face_row._year_edited()
    face_row.amount_edit.set_value(40_000, decimals=0)
    tab._refresh_max_level_caveat()
    app.processEvents()
    tab.grab().save(str(out_dir / "mock_max_level_caveat.png"))
    tab.hide()
    print(str(out_dir / "mock_premium_solve_group.png"))
    print(str(out_dir / "mock_max_level_caveat.png"))


if __name__ == "__main__":
    main()
