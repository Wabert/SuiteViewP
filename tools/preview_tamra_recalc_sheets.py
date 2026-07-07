"""Render the TAMRA recalc sheets (all three cases) to PNGs for visual review.

Builds a GuidelineRecalcDetailView per tamra_case with representative detail
dicts (including a real 7-pay PV breakdown from a hand-built basis) and grabs
each TAMRA tab to ~/.suiteview/tamra_sheet_<case>_<tab>.png.

Usage:
    venv\\Scripts\\python.exe tools/preview_tamra_recalc_sheets.py
"""
import json
import os
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from suiteview.illustration.core.guideline_pv import guideline_7pay_detail  # noqa: E402
from suiteview.illustration.core.monthly_guideline import (  # noqa: E402
    GuidelineBasis,
    GuidelineMonth,
)


def _seven_pay_pv():
    months = []
    for m in range(240):
        months.append(GuidelineMonth(
            attained_age=45 + m // 12,
            coi_rate=0.0009,
            fee=10.0,
            epu=5.0,
            is_anniversary=(m % 12 == 0),
        ))
    basis = GuidelineBasis(
        months=months, total_sa=100_000.0, db_option="A",
        ctp=0.0, guaranteed_rate=0.0,
    )
    return guideline_7pay_detail(basis, starting_av=5_000.0)


def _backtest():
    from suiteview.illustration.ui.values_tab import _seven_pay_backtest

    policy = SimpleNamespace(
        tamra_7year_contributions=[1_000.0, 1_200.0, 0, 0, 0, 0, 0])
    ws = date(2024, 1, 15)
    states = [
        SimpleNamespace(tamra_7pay_start_date=ws, tamra_year=3,
                        accumulated_7pay=2_200.0, amount_in_7pay=2_200.0,
                        date=date(2026, 3, 15)),
        SimpleNamespace(tamra_7pay_start_date=ws, tamra_year=3,
                        accumulated_7pay=2_500.0, amount_in_7pay=2_200.0,
                        date=date(2026, 4, 15)),
        SimpleNamespace(tamra_7pay_start_date=ws, tamra_year=3,
                        accumulated_7pay=2_900.0, amount_in_7pay=2_500.0,
                        date=date(2026, 5, 15)),
    ]
    detail = {"seven_pay_new": 800.0, "seven_pay_window_start": ws,
              "tamra_year_at_change": 3}
    return _seven_pay_backtest(policy, states, 2, detail)


def main():
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from suiteview.illustration.ui.values_tab import GuidelineRecalcDetailView

    base = {
        "change_kind": "Specified Amount Change",
        "change_date": date(2026, 6, 9),
        "glp_before": 96.0, "glp_after": 120.0, "glp_prior": 96.0, "glp_new": 120.0,
        "gsp_before": 192.0, "gsp_after": 240.0, "gsp_prior": 192.0, "gsp_new": 240.0,
    }
    cases = {
        "no_recalc": dict(base, tamra_case="no_recalc", tamra_year_at_change=12,
                          seven_pay_prior=60.0, seven_pay_new=48.0,
                          seven_pay_prior_start=date(2015, 6, 9),
                          seven_pay_window_start=date(2015, 6, 9)),
        "within_period": dict(base, tamra_case="within_period", tamra_year_at_change=3,
                              seven_pay_prior=60.0, seven_pay_new=48.0,
                              seven_pay_window_start=date(2024, 1, 15),
                              seven_pay_start_av=5_000.0,
                              seven_pay_pv=_seven_pay_pv(),
                              seven_pay_backtest=_backtest()),
        "new_period": dict(base, tamra_case="new_period", tamra_year_at_change=12,
                           seven_pay_prior=60.0, seven_pay_new=48.0,
                           seven_pay_window_start=date(2026, 6, 9),
                           seven_pay_start_av=5_000.0,
                           seven_pay_pv=_seven_pay_pv()),
    }

    out_dir = Path.home() / ".suiteview"
    out_dir.mkdir(exist_ok=True)
    tamra_tabs = {"TAMRA Calc": "calc", "MEC Back-Test": "backtest",
                  "New 7-Pay Period": "newperiod"}
    written = []
    for case, detail in cases.items():
        view = GuidelineRecalcDetailView()
        view.resize(1100, 620)
        view.show_recalc(detail)
        for index in range(view.tabs.count()):
            title = view.tabs.tabText(index)
            slug = tamra_tabs.get(title)
            if slug is None:
                continue
            view.tabs.setCurrentIndex(index)
            app.processEvents()
            path = out_dir / f"tamra_sheet_{case}_{slug}.png"
            view.grab().save(str(path))
            written.append(str(path))
    print(json.dumps({"written": written}, indent=2))


if __name__ == "__main__":
    main()
