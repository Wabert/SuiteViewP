"""Probe: run an as-is forecast for one policy and find where EAV goes negative."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.core.policy_service import get_policy_info, clear_cache
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.illustration_policy_service import build_illustration_data
from suiteview.illustration.core.scenario_builder import build_illustration_scenario
from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab


def run(policy_number: str, region: str = "CKPR", company: str | None = None):
    app = QApplication.instance() or QApplication([])
    clear_cache()
    pi = get_policy_info(policy_number, region, company)
    if pi is None or not getattr(pi, "exists", False):
        print(f"{policy_number}: NOT FOUND (region={region})")
        return
    print(f"{policy_number}: found, plancode={pi.base_plancode!r} company={pi.company_code} "
          f"status={getattr(pi,'status_code',None)} modal_prem={getattr(pi,'modal_premium',None)} "
          f"billing_freq={getattr(pi,'billing_frequency',None)} val_date={getattr(pi,'valuation_date',None)}")

    policy_data = build_illustration_data(policy_number, region=region, company_code=pi.company_code)
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(pi)

    scenario = build_illustration_scenario(
        policy_data,
        inforce_overrides=tab.export_inforce_overrides(),
        future_inputs=tab.export_input_set(),
    )
    months = tab._months_to_maturity(scenario.projectable_policy)
    print(f"  modal_premium(data)={policy_data.modal_premium} months_to_maturity={months}")
    engine = IllustrationEngine()
    results = engine.project(
        scenario.projectable_policy,
        months=months,
        future_inputs=scenario.future_inputs,
        options=tab.export_options(),
        stop_on_lapse=False,
    )
    print(f"  projected {len(results)} states")
    # find first negative ending account value
    first_neg = None
    for st in results[1:]:
        if st.av_end_of_month < 0:
            first_neg = st
            break
    if first_neg is None:
        print("  EAV never goes negative")
    else:
        print(f"  FIRST NEGATIVE EAV: date={first_neg.date} dur={first_neg.duration} "
              f"yr={first_neg.policy_year} mo={first_neg.policy_month} av_end={first_neg.av_end_of_month:.2f} "
              f"lapsed={getattr(first_neg,'lapsed',None)}")
    # also show a few sample rows near the end of positive
    print("  first premium rows:")
    for st in [s for s in results[1:] if s.gross_premium > 0][:4]:
        print(f"    {st.date} dur={st.duration} av_end={st.av_end_of_month:.2f} prem={st.gross_premium:.2f}")


if __name__ == "__main__":
    pol = sys.argv[1] if len(sys.argv) > 1 else "S0501200"
    reg = sys.argv[2] if len(sys.argv) > 2 else "CKPR"
    run(pol, reg)
