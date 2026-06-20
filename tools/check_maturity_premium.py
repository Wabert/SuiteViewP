"""Check whether the engine applies a premium on the maturity month.

Projects a short-maturity synthetic policy (real rate tables stubbed out) that
bills a modal premium every month, and prints the tail so the maturity month's
gross premium is visible.
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

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.input_set import IllustrationOptions
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData


def main() -> None:
    maturity_age = 47
    calc_engine.load_plancode = lambda _p: PlancodeConfig(
        plancode="TEST", interest_method="ExactDays", gint=0.0, dbd=0.0,
        premium_load="0", prem_flat_load=0.0, epu_code="0", mfee="5",
        poav_code="0", bonus="0", corridor_code=None, snet_period=0,
        maturity_age=maturity_age, loan_type="Arrears")
    calc_engine.load_bonus_config = lambda _p, _d: BonusConfig()

    policy = IllustrationPolicyData(
        plancode="TEST",
        issue_date=date(2026, 1, 15),
        valuation_date=date(2026, 1, 15),
        issue_age=45,
        attained_age=45,
        maturity_age=maturity_age,
        policy_year=1,
        policy_month=1,
        duration=1,
        face_amount=100_000.0,
        units=100.0,
        db_option="A",
        account_value=100_000.0,
        modal_premium=100.0,
        glp=1_000_000.0,
        gsp=1_000_000.0,
        current_interest_rate=0.0,
        segments=[CoverageSegment(coverage_phase=1, issue_date=date(2026, 1, 15),
                                  face_amount=100_000.0, units=100.0)],
    )

    states = IllustrationEngine().project(
        policy, months=None, options=IllustrationOptions(),
        rates_override=IllustrationRates(), bonus_override=BonusConfig())

    maturity_date = date(2026 + (maturity_age - 45), 1, 15)
    print(f"maturity_age={maturity_age}  maturity_date={maturity_date}  states={len(states)}")
    print(f"{'row':>3} {'date':>12} {'att':>3} {'yr':>3} {'mo':>3} {'gross_prem':>11} "
          f"{'tot_MD':>8} {'AV_end':>12}")
    for i, s in enumerate(states):
        flag = "  <-- maturity" if s.date == maturity_date else ""
        print(f"{i:>3} {str(s.date):>12} {s.attained_age:>3} {s.policy_year:>3} "
              f"{s.policy_month:>3} {s.gross_premium:>11,.2f} {s.total_deduction:>8,.2f} "
              f"{s.av_end_of_month:>12,.2f}{flag}")


if __name__ == "__main__":
    main()
