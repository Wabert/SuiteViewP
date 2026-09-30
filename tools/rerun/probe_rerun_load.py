"""Run RERUN's standard load and projection on a live policy and report each stage, read-only.

Usage: venv\\Scripts\\python.exe tools\\rerun\\probe_rerun_load.py <policy> [company] [months]

Stages: ``load_policy_data`` (PolicyInformation -> IllustrationPolicyData), plancode
config, rate bundle, then a short ``project_policy`` run. The first failure is printed
with its traceback, so product support gaps (e.g. ISWL) show exactly where they stop.
"""

import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.local_dev import local_data_enabled


def _stage(name, fn):
    try:
        result = fn()
    except Exception as exc:  # report the first failing stage, with its trace
        print(json.dumps({"stage": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        traceback.print_exc()
        raise SystemExit(1)
    print(json.dumps({"stage": name, "ok": True}))
    return result


def main() -> None:
    if local_data_enabled():
        raise RuntimeError("This probe reads live data only.")
    policy_number = sys.argv[1]
    company = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None
    months = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    from suiteview.illustration.api import load_policy_data, project_policy
    from suiteview.illustration.models.plancode_config import load_plancode
    from suiteview.illustration.core.rate_loader import load_rates

    policy = _stage("load_policy_data", lambda: load_policy_data(policy_number, company_code=company))
    print(json.dumps({"product_type": policy.product_type, "plancode": policy.plancode,
                      "face": policy.face_amount, "modal_premium": policy.modal_premium,
                      "account_value": policy.account_value, "def_of_life_ins": policy.def_of_life_ins,
                      "valuation_date": str(policy.valuation_date)}, default=str))
    config = _stage("load_plancode", lambda: load_plancode(policy.plancode))
    rates = _stage("load_rates", lambda: load_rates(policy, config))
    run = _stage("project_policy", lambda: project_policy(policy, config=config, rates=rates, months=months))
    for state in run.states[: months + 1]:
        print(json.dumps({"date": str(state.date), "year": state.policy_year, "month": state.policy_month,
                          "av": round(state.av_end_of_month if hasattr(state, "av_end_of_month")
                                      else getattr(state, "account_value", 0.0), 2)}, default=str))


if __name__ == "__main__":
    main()
