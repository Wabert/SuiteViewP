"""Verify saved-case guideline recalculations end at min(policy maturity, 100), read-only."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--case", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    before_hash = hashlib.sha256(args.bundle.read_bytes()).hexdigest()
    report = {"checks": {}, "recalculations": []}
    checks = report["checks"]
    with TemporaryDirectory(prefix="suiteview-guideline-") as profile:
        os.environ["SUITEVIEW_PROFILE_DIR"] = profile
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        from suiteview.core.rates import owned_rate_connections
        from suiteview.illustration.core.compare_runner import run_scenario
        from suiteview.illustration.models.imported_case_store import load_imported_case
        from suiteview.illustration.ui.saved_case_scenario import materialize_saved_case

        app = QApplication.instance() or QApplication([])
        case = load_imported_case(args.bundle, args.case)
        original = deepcopy(case.policy_snapshot)
        with owned_rate_connections():
            outcome = run_scenario(materialize_saved_case(case, strict=True))
        assert outcome.results is not None
        end_age = min(outcome.policy.maturity_age, 100)
        report.update(policy=case.policy_number, maturity_age=outcome.policy.maturity_age,
                      guideline_endowment_age=end_age)
        for state in outcome.results:
            detail = state.guideline_recalc
            if "monthly_pv_recalc" not in detail:
                continue
            for side in ("before", "after"):
                for premium in ("glp", "gsp"):
                    pv = detail["monthly_pv_recalc"][side][premium]
                    rows = pv["glp_rows"]
                    key = f"{state.date}_{side}_{premium}"
                    checks[key + "_terminal_age"] = rows[-1]["Age"] == end_age and rows[-1]["_endowment"]
                    checks[key + "_no_later_charges"] = all(
                        row["Age"] < end_age for row in rows[:-1])
                    checks[key + "_reconciles"] = abs(
                        pv["glp_rollup"]["premium"] - detail[f"{premium}_{side}"]) <= 0.005
                    report["recalculations"].append({
                        "date": state.date, "side": side, "premium": premium,
                        "months": pv["glp_rollup"]["months"],
                        "endowment_age": rows[-1]["Age"],
                        "amount": pv["glp_rollup"]["premium"],
                    })
        checks["recalculations_present"] = bool(report["recalculations"])
        checks["snapshot_unchanged"] = case.policy_snapshot == original
        app.processEvents()
    checks["file_unchanged"] = hashlib.sha256(args.bundle.read_bytes()).hexdigest() == before_hash
    report["all_ok"] = all(checks.values())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
