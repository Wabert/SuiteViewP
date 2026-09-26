"""Read-only check of target-based waiver amounts and guideline recalc charges."""

import argparse
from copy import deepcopy
from datetime import date
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.models.input_set import (
    IllustrationInputSet, PolicyChangeEvent, PolicyChangeKind,
)
from suiteview.illustration.models.plancode_config import load_plancode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument("--face", required=True, type=float)
    parser.add_argument("--region", default="CKPR")
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise ValueError("Live verification cannot use local policy data.")
    policy = _load_policy_data(args.policy, args.region, args.company)
    original = deepcopy(policy)
    config = load_plancode(policy.plancode)
    inputs = IllustrationInputSet(policy_changes=[PolicyChangeEvent(
        kind=PolicyChangeKind.FACE_AMOUNT, effective_date=args.date, value=args.face,
    )])
    months = (
        (args.date.year - policy.valuation_date.year) * 12
        + args.date.month - policy.valuation_date.month + 2
    )
    states = _project_with_engine(IllustrationEngine(), policy, months=months, future_inputs=inputs)
    rows = [{
        "date": state.date,
        "mtp": state.mtp_detail.get("vMTP"),
        "ctp": state.ctp_detail.get("vCTP"),
        "benefit_amounts": state.benefit_amounts,
        "benefit_charges": state.benefit_charge_detail,
    } for state in states]
    field = "vMTP" if config.pwot_coi_basis == 2 else "vCTP"
    follows = []
    guideline_checks = []
    guideline_rows = []
    for state in states:
        if state.date < args.date:
            continue
        detail = state.mtp_detail if config.pwot_coi_basis == 2 else state.ctp_detail
        for key, value in state.benefit_amounts.items():
            if key.startswith("4"):
                follows.append(abs(value - detail[field]) < 1e-8)
        recalc = state.guideline_recalc
        if recalc:
            for side in ("before", "after"):
                for kind in ("glp", "gsp"):
                    first = recalc["monthly_pv_recalc"][side][kind]["glp_rows"][0]
                    charges = {}
                    for key, charge in state.benefit_charge_detail.items():
                        if key.startswith("4"):
                            label = f"Benefit {key[0]} {key[1:]}".strip()
                            charges[key] = first[label]
                            if side == "after":
                                guideline_checks.append(abs(first[label] - charge) < 1e-8)
                    guideline_rows.append({
                        "side": side, "kind": kind, "charges": charges,
                        "premium": recalc[f"{kind}_{side}"],
                    })
    unchanged = policy == original
    ok = (
        config.pwot_coi_basis in (2, 3) and bool(follows) and all(follows)
        and bool(guideline_checks) and all(guideline_checks) and unchanged
    )
    print(json.dumps({
        "policy": args.policy, "plancode": policy.plancode,
        "pwot_coi_basis": config.pwot_coi_basis, "source_unchanged": unchanged,
        "rows": rows, "guideline_rows": guideline_rows, "all_ok": ok,
    }, default=str, indent=2))
    return 0 if ok else 1


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
