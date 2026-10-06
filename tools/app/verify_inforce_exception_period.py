"""Read-only live RERUN exception-period projection and native notice capture."""
import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.solve_level_to_exception import solve_level_to_exception
from suiteview.illustration.models.input_set import IllustrationOptions
from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--company")
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    policy = _load_policy_data(
        args.policy.strip().upper(), region=args.region.strip().upper(),
        company_code=args.company)
    original = copy.deepcopy(policy)
    assert policy.in_exception_period, (
        "Policy is not a known GP / zero-GLP inforce basis with its guideline limit used up.")
    options = IllustrationOptions(allow_exception_prems=False, exact_days_interest=False)
    states = _project_with_engine(IllustrationEngine(), policy, options=options)
    solved = solve_level_to_exception(policy, base_options=options)
    app = QApplication.instance() or QApplication([])
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(
        policy, has_shadow=policy.has_shadow_account, shadow_ceased=policy.ccv_ceased)
    tab.resize(1150, 740)
    tab.show()
    app.processEvents()
    notice = tab.dynamic_panel.suspended_banner
    args.output_dir.mkdir(parents=True, exist_ok=True)
    screenshot = args.output_dir / "exception-period.png"
    assert tab.grab().save(str(screenshot))
    exception_rows = [s for s in states[1:] if s.gp_exception_prem > 0]
    checks = {
        "starting_exception_mode": states[0].gp_exception_mode,
        "no_regular_or_md_premiums": all(
            s.gross_premium == 0 and s.md_premium == 0 for s in states),
        "no_premium_while_av_remains": all(
            s.gp_exception_prem == 0 for s in states[1:]
            if s.av_after_deduction - s.asset_charge > 0),
        "calculated_exception_premiums": bool(exception_rows),
        "zero_level_premium_solved": solved.premium == 0,
        "red_notice_visible": notice.isVisible() and "EXCEPTION PREMIUM PERIOD" in notice.text(),
        "source_unchanged": policy == original,
    }
    result = {
        "policy": policy.policy_number, "definition": policy.def_of_life_ins,
        "glp": policy.glp, "opening_av": policy.account_value,
        "months": len(states) - 1,
        "first_exception_date": str(exception_rows[0].date) if exception_rows else None,
        "first_exception_premium": exception_rows[0].gp_exception_prem if exception_rows else None,
        "notice": notice.text(), "screenshot": str(screenshot),
        "checks": checks, "all_ok": all(checks.values()),
    }
    (args.output_dir / "verification.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    tab.close()
    return 0 if result["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
def _load_policy_data(*args, **kwargs):
    from suiteview.illustration.api import load_policy_data

    return load_policy_data(*args, **kwargs)
def _project_with_engine(engine, policy, **kwargs):
    from suiteview.illustration.api import project_policy

    if "future_inputs" in kwargs:
        kwargs["inputs"] = kwargs.pop("future_inputs")
    if "rates_override" in kwargs:
        kwargs["rates"] = kwargs.pop("rates_override")
    return project_policy(policy, engine=engine, **kwargs).states
