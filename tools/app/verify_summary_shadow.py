"""Native, no-DB check of RERUN's Summary shadow columns."""

import argparse
from dataclasses import replace
from datetime import date
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="suiteview-summary-shadow-") as profile:
        os.environ["SUITEVIEW_PROFILE_DIR"] = profile
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QApplication
        from suiteview.illustration.core.summary_results import SHADOW_SUMMARY_COLUMNS
        from suiteview.illustration.models.calc_state import MonthlyState
        from suiteview.illustration.models.policy_data import IllustrationPolicyData
        from suiteview.illustration.ui.main_window import IllustrationWindow

        app = QApplication.instance() or QApplication([])
        window = IllustrationWindow()
        try:
            policy = IllustrationPolicyData(
                policy_number="SYNTHETIC", face_amount=100000, ccv_active=True,
            )
            state = MonthlyState(
                date=date(2026, 9, 26), policy_year=12, policy_month=11,
                attained_age=36, shadow_target_prem=745.84, shadow_coi=23.45,
                shadow_epu=4.56, shadow_rider_charges=7.89, shadow_md=40.9,
                shadow_int_rate=0.045, shadow_eav=752.81,
            )
            values = window.values_tab
            values.display_projection(policy, [state], months=0)
            values.set_guaranteed_results(policy, [replace(state, shadow_eav=700.25)])
            window.tabs.setCurrentWidget(values)
            window.resize(1600, 700)
            window.show()
            values._drill_down(0, "LN")
            app.processEvents()
            grid = values._tab_grids["Summary"]
            bar = grid.table_view.horizontalScrollBar()
            bar.setValue(bar.maximum())
            QTest.qWait(150)
            checks = {}
            checks["column_order"] = list(grid.df.columns[-7:]) == list(SHADOW_SUMMARY_COLUMNS)
            checks["headers"] = all(
                grid.model.headerData(
                    grid.df.columns.get_loc(name), Qt.Orientation.Horizontal,
                    Qt.ItemDataRole.DisplayRole,
                ) == name for name in SHADOW_SUMMARY_COLUMNS
            )
            checks["current_values"] = grid.df.iloc[0][list(SHADOW_SUMMARY_COLUMNS)].tolist() == [
                745.84, 23.45, 4.56, 7.89, 40.9, 0.045, 752.81,
            ]
            checks["visible"] = grid.isVisible()
            header = grid.table_view.horizontalHeader()
            checks["shadow_columns_fit"] = all(
                0 <= header.sectionViewportPosition(grid.df.columns.get_loc(name))
                and header.sectionViewportPosition(grid.df.columns.get_loc(name))
                + header.sectionSize(grid.df.columns.get_loc(name))
                <= grid.table_view.viewport().width()
                for name in SHADOW_SUMMARY_COLUMNS
            )
            if args.screenshot:
                args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                if not window.grab().save(str(args.screenshot), "PNG"):
                    raise RuntimeError(f"Cannot save screenshot: {args.screenshot}")
            values.guaranteed_toggle.click()
            checks["guaranteed_values"] = bool(grid.df.iloc[0]["vShadowEAV"] == 700.25)
            values.current_toggle.click()
            checks["current_restored"] = bool(grid.df.iloc[0]["vShadowEAV"] == 752.81)
            ok = all(checks.values())
            print(json.dumps({"checks": checks, "all_ok": ok}, indent=2))
            return 0 if ok else 1
        finally:
            window.close()
            app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
