"""Read-only exercise of RERUN features on a live joint survivor (second-to-die) UL.

Runs one in-force company-26 joint policy through the engine with: a face
decrease (7702 GLP/GSP/7-pay recalc), a DB option change, a new loan plus a
withdrawal, a large lump sum (guideline/TAMRA caps and MEC status) and the
premium solve to a target age. Each scenario reports its key results and any
failure. Nothing is written to DB2 or UL_Rates.

Usage (venv\\Scripts\\python.exe):
    tools\\rates\\exercise_rerun_joint_features.py '{"policy": "000335148", "output": "<report.json>"}'
Keys: policy, company (default 26), region (CKPR), output.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from dateutil.relativedelta import relativedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.json_store import write_json  # noqa: E402
from suiteview.core.local_dev import local_data_enabled  # noqa: E402
from suiteview.illustration.core.calc_engine import IllustrationEngine  # noqa: E402
from suiteview.illustration.core.guaranteed_projection import run_guaranteed_projection  # noqa: E402
from suiteview.illustration.core.illustration_policy_service import build_illustration_data  # noqa: E402
from suiteview.illustration.core.solve_premium_to_target import solve_premium_to_target  # noqa: E402
from suiteview.illustration.models.input_set import (  # noqa: E402
    DatedTransaction, IllustrationInputSet, PolicyChangeEvent, PolicyChangeKind,
    TransactionKind,
)


def _summary(states) -> dict:
    last = states[-1]
    return {
        "months": len(states), "last_date": str(last.date), "lapsed": bool(last.lapsed),
        "last_av": round(float(last.av_end_of_month), 2),
        "max_policy_debt": round(max(float(s.policy_debt) for s in states), 2),
        "forceouts": round(sum(float(s.guideline_forceout) for s in states), 2),
        "capped_months": sum(1 for s in states if s.premium_capped),
        "tamra_capped_months": sum(1 for s in states if s.premium_capped_by_tamra),
        "is_mec": bool(last.is_mec),
        "recalcs": [
            {k: (str(v) if isinstance(v, date) else v) for k, v in s.guideline_recalc.items()
             if not isinstance(v, (dict, list))}
            for s in states if s.guideline_recalc
        ][:2],
    }


def main() -> None:
    arg = sys.argv[1]
    config = json.loads(Path(arg[1:]).read_text(encoding="utf-8-sig")) if arg.startswith("@") else json.loads(arg)
    if local_data_enabled():
        raise RuntimeError("This exercise requires live data, not SUITEVIEW_LOCAL_DATA.")
    policy = build_illustration_data(
        config["policy"], region=config.get("region", "CKPR"),
        company_code=config.get("company", "26"))
    if not policy.is_joint_survivor:
        raise RuntimeError("Not loaded as a joint survivor policy.")
    anniversary = policy.issue_date + relativedelta(years=policy.policy_year)
    next_month = policy.valuation_date + relativedelta(months=1)
    face = policy.total_face
    scenarios = {
        "base": IllustrationInputSet(),
        "face_decrease": IllustrationInputSet(policy_changes=[PolicyChangeEvent(
            kind=PolicyChangeKind.FACE_AMOUNT, effective_date=anniversary,
            value=round(face * 0.8, 2))]),
        "db_option_b": IllustrationInputSet(policy_changes=[PolicyChangeEvent(
            kind=PolicyChangeKind.DB_OPTION, effective_date=anniversary, value="B")]),
        "loan_and_withdrawal": IllustrationInputSet(dated_transactions=[
            DatedTransaction(kind=TransactionKind.LOAN, effective_date=next_month,
                             amount=round(policy.account_value * 0.10, 2)),
            DatedTransaction(kind=TransactionKind.WITHDRAWAL, effective_date=anniversary,
                             amount=round(policy.account_value * 0.05, 2)),
        ]),
        "large_lump_sum": IllustrationInputSet(dated_transactions=[DatedTransaction(
            kind=TransactionKind.PREMIUM, effective_date=next_month, amount=round(face, 2))]),
    }
    engine = IllustrationEngine()
    report = {
        "policy": policy.policy_number, "plancode": policy.plancode,
        "valuation_date": str(policy.valuation_date), "face": face,
        "glp": policy.glp, "gsp": policy.gsp, "seven_pay": policy.tamra_7pay_level,
        "scenarios": {},
    }
    for name, inputs in scenarios.items():
        try:
            current = engine.project(policy, future_inputs=inputs)
            guaranteed = run_guaranteed_projection(
                policy, current, base_future_inputs=inputs, engine=engine)
            report["scenarios"][name] = {"current": _summary(current),
                                         "guaranteed": _summary(guaranteed) if guaranteed else None}
        except Exception as exc:  # reported, never hidden
            report["scenarios"][name] = {"error": f"{type(exc).__name__}: {exc}"}
    try:
        solve = solve_premium_to_target(
            policy, target="sv", amount=1.0, at_age=min(100, int(policy.maturity_age)),
            start_policy_year=policy.policy_year)
        report["solve_sv_to_age_100"] = {
            "premium": solve.premium, "mode": solve.mode,
            "achieved_value": round(solve.achieved_value, 2), "iterations": solve.iterations}
    except Exception as exc:
        report["solve_sv_to_age_100"] = {"error": f"{type(exc).__name__}: {exc}"}
    report["all_ok"] = not any("error" in v for v in report["scenarios"].values()) and (
        "error" not in report["solve_sv_to_age_100"])
    print(json.dumps(report, indent=1, default=str))
    if config.get("output"):
        write_json(config["output"], report)


if __name__ == "__main__":
    main()
