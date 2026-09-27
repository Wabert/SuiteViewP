"""EXPERIMENT: quantify the PW target-rate gap in the U0356726-DBO recalc.

RERUN looks the PW (benefit 39) TARGET rate up by the Rates_Control
target-index key (300&M&0&0&age -> 0.044); the app's Rates.get_ben_mtp keys
Select_RATE_BENMTP by 39/sex/rateclass/band (-> 0.042). This script runs the
DBO B->A case twice — stock, and with get_ben_mtp patched to the RERUN rate —
and prints the post-change vMTP / vGLP / vGSP / 7-pay next to the RERUN
reference values, to confirm the residual cents are fully explained by the
rate-source gap (WORK_LAPTOP_SPEC §5.4).

Usage:
    venv\\Scripts\\python.exe tools/engine/repro_pw_target_rate_gap.py
"""
from __future__ import annotations

def _project_with_engine(engine, policy, **kwargs):
    from suiteview.illustration.api import project_policy

    if "future_inputs" in kwargs:
        kwargs["inputs"] = kwargs.pop("future_inputs")
    if "rates_override" in kwargs:
        kwargs["rates"] = kwargs.pop("rates_override")
    return project_policy(policy, engine=engine, **kwargs).states
def _load_policy_data(*args, **kwargs):
    from suiteview.illustration.api import load_policy_data

    return load_policy_data(*args, **kwargs)
import datetime
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

RERUN_REF = {"mtp_after": 432.48, "glp_new": -925.20, "gsp_new": 11573.40,
             "seven_pay_new": 5272.08}
PW_RERUN_RATE = 0.044


def run_case(patch_pw: bool) -> dict:
    from suiteview.polview.services.policy_service import clear_cache
    from suiteview.core import rates as rates_module
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.models.input_set import (
        IllustrationInputSet, IllustrationOptions, PolicyChangeEvent,
        PolicyChangeKind, ScheduledTransaction, TransactionKind,
    )

    original = rates_module.Rates.get_ben_mtp
    if patch_pw:
        def patched(self, plancode, issue_age, sex, rateclass, band, benefit_type):
            if benefit_type == "39":
                return PW_RERUN_RATE
            return original(self, plancode, issue_age, sex, rateclass, band, benefit_type)
        rates_module.Rates.get_ben_mtp = patched
    try:
        clear_cache()
        policy = _load_policy_data("U0356726", region="CKPR", company_code="01")
        inputs = IllustrationInputSet(
            scheduled_transactions=[ScheduledTransaction(
                kind=TransactionKind.PREMIUM, policy_year=1, amount=60.0, mode="M")],
            policy_changes=[PolicyChangeEvent(
                kind=PolicyChangeKind.DB_OPTION,
                effective_date=datetime.date(2027, 10, 1), value="A")],
        )
        options = IllustrationOptions(
            conform_to_tefra=True, conform_to_tamra=True,
            allow_exception_prems=False, exact_days_interest=False)
        states = _project_with_engine(IllustrationEngine(), 
            policy, months=40, future_inputs=inputs, options=options)
        chg = next(s for s in states if s.guideline_recalc)
        return {
            "mtp_after": chg.mtp_annual,
            "glp_new": chg.glp,
            "gsp_new": chg.gsp,
            "seven_pay_new": chg.tamra_7pay_level,
        }
    finally:
        rates_module.Rates.get_ben_mtp = original


def main() -> None:
    out = {"rerun_reference": RERUN_REF,
           "stock": run_case(False),
           "pw_rate_0.044": run_case(True)}
    for label in ("stock", "pw_rate_0.044"):
        out[f"{label}_deltas_vs_rerun"] = {
            k: round(out[label][k] - RERUN_REF[k], 4) for k in RERUN_REF}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
