"""Verify PolView stored CV/NSP rates and Guaranteed Cash Value against live DB2.

Usage: venv\\Scripts\\python.exe tools\\app\\verify_guaranteed_cash_value.py @config.json
JSON keys: cases (list of {policy, company, region, gcv, basis, as_of}),
screenshot_dir, output. ``gcv`` is the expected display text ("N/A" allowed);
``basis`` is "CV", "NSP" or null; ``as_of`` is an ISO date or omitted.

Read-only. Each case is loaded through the real PolView prefetch session and
the Policy / Targets & Accumulators tabs render under cached_reads_only().
Refuses local SQLite data.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtWidgets import QApplication

from suiteview.core.json_store import write_json
from suiteview.core.local_dev import local_data_enabled
from suiteview.polview.services.policy_prefetch import PolicyLoadSession
from suiteview.polview.ui.tabs.policy_tab import PolicyTab
from suiteview.polview.ui.tabs.targets_tab import TargetsAccumulatorsTab


def _check_case(app, case, screenshot_dir):
    session = PolicyLoadSession(
        case["policy"], case.get("region", "CKPR"), case.get("company", ""),
    )
    try:
        initial = session.load_initial()
        if not initial.available:
            raise RuntimeError(f"{case['policy']}: policy not found")
        policy_stage = session.prepare("policy").policy
        targets_stage = session.prepare("targets").policy
    finally:
        session.close()

    policy_tab = PolicyTab()
    targets_tab = TargetsAccumulatorsTab()
    try:
        with policy_stage.cached_reads_only():
            policy_tab.load_data_from_policy(policy_stage)
        with targets_stage.cached_reads_only():
            targets_tab.load_data_from_policy(targets_stage)
            gcv = targets_stage.rates.guaranteed_cash_value()
            rates = targets_stage.rates.cov_cash_value_rates(1)

        c = policy_tab.col2
        rate_rows = [
            (c._labels[attr].text(), c.get_value(attr))
            for attr in PolicyTab._CV_RATE_FIELDS if not c._fields[attr].isHidden()
        ]
        accum = targets_tab.accum_widget
        displayed = accum.get_value("gcv_label")
        tooltip = accum._fields["gcv_label"].toolTip()

        failures = []
        if "gcv" in case and displayed != case["gcv"]:
            failures.append(f"GCV displayed {displayed!r}, expected {case['gcv']!r}")
        if "basis" in case and rates["basis"] != case["basis"]:
            failures.append(f"basis {rates['basis']!r}, expected {case['basis']!r}")
        if case.get("as_of") and str(gcv["as_of"]) != case["as_of"]:
            failures.append(f"as_of {gcv['as_of']}, expected {case['as_of']}")

        if screenshot_dir:
            target_dir = Path(screenshot_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            for name, widget in (("policy", policy_tab), ("targets", targets_tab)):
                widget.resize(1500, 700)
                widget.show()
                app.processEvents()
                path = target_dir / f"{case['policy']}_{name}.png"
                if not widget.grab().save(str(path), "PNG"):
                    raise RuntimeError(f"Could not save screenshot: {path}")

        return {
            "policy": case["policy"], "company": targets_stage.company_code,
            "status": targets_stage.status.premium_pay_status_code,
            "ok": not failures, "failures": failures,
            "basis_display": c.get_value("cv_rate_basis"), "rate_rows": rate_rows,
            "gcv_display": displayed, "as_of": str(gcv["as_of"]),
            "reason": gcv["reason"], "tooltip": tooltip,
        }
    finally:
        policy_tab.close()
        targets_tab.close()
        app.processEvents()


def main():
    arg = sys.argv[1]
    config = json.loads(
        Path(arg[1:]).read_text(encoding="utf-8") if arg.startswith("@") else arg
    )
    if local_data_enabled():
        raise RuntimeError("Live DB2 verification cannot use local SQLite data.")
    app = QApplication.instance() or QApplication([])
    results = [_check_case(app, case, config.get("screenshot_dir"))
               for case in config["cases"]]
    report = {"all_ok": all(r["ok"] for r in results), "cases": results}
    if config.get("output"):
        write_json(Path(config["output"]), report)
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["all_ok"] else 1)


if __name__ == "__main__":
    main()
