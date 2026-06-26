"""Diagnostic: run U0688012 with MD premium + GP exception and dump the months
around 2052-09-09 where the post-exception AV is reported going negative.

    venv\\Scripts\\python.exe tools/diag_md_u0688012.py [policy] [region]
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SUITEVIEW_LOCAL_DATA", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.core.policy_service import get_policy_info, clear_cache
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.illustration_policy_service import build_illustration_data
from suiteview.illustration.core.scenario_builder import build_illustration_scenario
from suiteview.illustration.models.input_set import IllustrationOptions
from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab


def run(policy_number: str, region: str = "CKPR"):
    app = QApplication.instance() or QApplication([])
    clear_cache()
    pi = get_policy_info(policy_number, region, None)
    if pi is None or not getattr(pi, "exists", False):
        print(f"{policy_number}: NOT FOUND (region={region})")
        return
    policy_data = build_illustration_data(policy_number, region=region, company_code=pi.company_code)
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(pi)
    scenario = build_illustration_scenario(
        policy_data,
        inforce_overrides=tab.export_inforce_overrides(),
        future_inputs=tab.export_input_set(),
    )
    months = tab._months_to_maturity(scenario.projectable_policy)

    # Replicate "Monthly Deduction premium type selected + Allow GP Exception":
    # no scheduled premium, MD premium on, exceptions on.
    options = IllustrationOptions(pay_monthly_deduction=True, allow_exception_prems=True)
    pol = scenario.projectable_policy
    print(f"{policy_number}: plancode={pol.plancode!r} is_gpt={pol.is_gpt} "
          f"has_shadow={pol.has_shadow_account} snet={getattr(pol,'snet_period',None)} "
          f"gsp={pol.gsp} glp={pol.glp} accumGLP={pol.accumulated_glp} "
          f"val={pol.valuation_date} AV0={pol.account_value:.2f} months={months}")

    engine = IllustrationEngine()
    results = engine.project(
        pol, months=months, future_inputs=None,
        options=options, stop_on_lapse=False,
    )

    def show(states):
        print("date        durYr/Mo  avBefMD     avAftDed   deduct    MDprem  cap  "
              "GPgross   GPprem   excMode gpMode lapsed  avAftExc   avEnd     premTD     premTDaft   wd       gLimit   room")
        for s in states:
            room = s.guideline_limit - (s.premiums_to_date - s.withdrawals_to_date)
            print(f"{s.date}  {s.policy_year:>2}/{s.policy_month:<2}  "
                  f"{s.guideline_av_before_monthly_deduction:>9.2f}  "
                  f"{s.av_after_deduction:>9.2f}  {s.total_deduction:>8.2f}  "
                  f"{s.md_premium:>7.2f}  {int(s.md_premium_capped)}   "
                  f"{s.gp_exception_prem_gross:>8.2f}  {s.gp_exception_prem:>8.2f}  "
                  f"{int(s.exception_prem_mode)}       {int(s.gp_exception_mode)}     "
                  f"{int(s.lapsed)}      {s.av_after_exception:>9.2f}  {s.av_end_of_month:>9.2f}  "
                  f"{s.premiums_to_date:>9.2f}  {s.premiums_to_date_after_exception:>9.2f}  "
                  f"{s.withdrawals_to_date:>7.2f}  {s.guideline_limit:>7.2f}  {room:>8.2f}")

    proj = results[1:]
    # Focused check: the two discount columns for a window where the MD premium
    # actually pays (room reopens at the anniversary) vs capped months.
    print("\ndate         MDprem   MDdiscount   GPprem    GPdiscount  capped")
    for s in proj:
        if 2052 <= s.date.year <= 2053:
            print(f"{s.date}  {s.md_premium:>7.2f}  {s.md_premium_discount:>9.4f}   "
                  f"{s.gp_exception_prem:>7.2f}  {s.gp_exception_prem_discount:>9.4f}   "
                  f"{int(s.md_premium_capped)}")




if __name__ == "__main__":
    pol = sys.argv[1] if len(sys.argv) > 1 else "U0688012"
    reg = sys.argv[2] if len(sys.argv) > 2 else "CKPR"
    run(pol, reg)
