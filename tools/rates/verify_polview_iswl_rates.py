"""Verify a live ISWL/WL policy's PolView fixed-premium rates and capture them.

Usage: venv\\Scripts\\python.exe tools\\rates\\verify_polview_iswl_rates.py @config.json [--output-dir <dir>]
Pinned case: tools\\rates\\iswl_rates_13034048_case.json. ``--output-dir`` sets
the screenshot directory and writes <policy>_iswl_rates.json there.
Config: {"policy", "company", "region", "coverage": 1, "output": report.json,
         "screenshot_dir": directory,
         "expected": {"user_code": "00", "cash_values": {"31": "333.00"},
                      "premiums": {"**": "11.76", "10": "0.98"},
                      "annual_premium": "318.50", "modal_premium": "33.02",
                      "pol_prm_amt": "33.02", "coi_scales": [1, 2, 3]}}

Reads live policy and UL_Rates data only. Each Rates-tree leaf is selected
through the real PolView window, its displayed grid must equal the model's
matrix, and optional screenshots of each leaf are saved.
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.json_store import write_json
from suiteview.core.local_dev import local_data_enabled
from suiteview.core.policy_service import get_policy_info



def capture(policy, selections, screenshot_dir):
    """Select each (category, index, matrix) leaf in the real window."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    from suiteview.polview.ui.main_window import GetPolicyWindow

    app = QApplication.instance() or QApplication([])
    window = GetPolicyWindow(enable_policy_list=False)
    shots = {}
    try:
        window._policy = policy
        window.lookup_bar.set_policy_display(policy.company_code, policy.policy_number, policy.region)
        window.records_tree.enable_rates_tab(policy)
        window.records_tree.show_rates_tab()
        window._toggle_tree_panel()
        window.resize(1500, 900)
        window.move(60, 40)
        window.show()
        tree = window.records_tree._tree
        for category, index, matrix, name in selections:
            item = None
            for i in range(tree.topLevelItemCount()):
                top = tree.topLevelItem(i)
                top.setExpanded(True)
                for j in range(top.childCount()):
                    data = top.child(j).data(0, Qt.ItemDataRole.UserRole) or {}
                    if data.get("category") == category and data.get("index") == index:
                        item = top.child(j)
            if item is None:
                raise RuntimeError(f"The Rates tree has no {category} leaf {index}.")
            tree.setCurrentItem(item)
            tree._on_item_clicked(item, 0)
            raw = window.raw_table_tab
            if raw._current_cols != matrix[0] or raw._current_rows != [tuple(r) for r in matrix[1:]]:
                raise RuntimeError(f"PolView did not display the verified {category} matrix.")
            app.processEvents()
            window.repaint()
            app.processEvents()
            if screenshot_dir:
                target = Path(screenshot_dir) / f"{policy.policy_number}_{name}.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                if not window.grab().save(str(target), "PNG"):
                    raise RuntimeError(f"Could not save screenshot: {target}")
                shots[category] = str(target)
    finally:
        window.close()
        app.processEvents()
    return shots


def main():
    arg = sys.argv[1]
    config = json.loads(Path(arg[1:]).read_text(encoding="utf-8")) if arg.startswith("@") else json.loads(arg)
    if len(sys.argv) == 4 and sys.argv[2] == "--output-dir":
        config["screenshot_dir"] = sys.argv[3]
        config["output"] = str(Path(sys.argv[3]) / f"{config['policy']}_iswl_rates.json")
    if local_data_enabled():
        raise RuntimeError("This verification requires live data, not SUITEVIEW_LOCAL_DATA.")
    policy = get_policy_info(
        config["policy"], region=config.get("region", "CKPR"),
        company_code=config.get("company"), use_cache=False,
    )
    if policy is None or not policy.exists:
        raise RuntimeError("Policy was not found or live policy access failed.")
    if not policy.has_fixed_premium_rates:
        raise RuntimeError("Select an ISWL or traditional Whole Life policy.")
    index = config.get("coverage", 1)
    expected = config.get("expected", {})
    iswl = policy.product_type == "ISWL"
    rates = policy._get_rates()
    failures = []

    def check(label, actual, wanted):
        if wanted is not None and str(actual) != str(wanted):
            failures.append(f"{label}: displayed {actual!r}, expected {wanted!r}")

    try:
        matrices = {
            "Coverages": policy.build_coverage_rate_matrix(index),
            "Premium Rates": policy.build_premium_rate_matrix(index),
            "Modal Premium": policy.build_modal_premium_matrix(),
        }
        matrices["Cash Values"] = (policy.build_whole_life_coverage_rate_matrix(index)
                                   if iswl else matrices["Coverages"])
        check("user_code", policy.cyberlife_rate_user_code, expected.get("user_code"))

        cv = matrices["Cash Values"]
        cv_values = {}
        if cv:
            d, v = cv[0].index("Duration"), cv[0].index("CV")
            cv_values = {str(row[d]): str(row[v]) for row in cv[1:] if row[d] != ""}
        for duration, value in expected.get("cash_values", {}).items():
            check(f"CV duration {duration}", cv_values.get(duration), Decimal(value))
        cv_info = {row[0]: row[1] for row in (cv or [[]])[1:] if row and row[0]}

        premium = matrices["Premium Rates"]
        rate_col = premium[0].index("Rate")
        displayed = {row[3]: row[rate_col] for row in premium[1:] if row[2] and row[4] == "N"}
        for option, value in expected.get("premiums", {}).items():
            check(f"premium {option}", displayed.get(option), value)

        modal = {row[3]: row for row in matrices["Modal Premium"][1:] if row[3]}
        amount = matrices["Modal Premium"][0].index("Amount")
        check("annual premium", modal.get("Annual premium", [None] * 8)[amount], expected.get("annual_premium"))
        check("modal premium", modal.get("Calculated modal premium", [None] * 8)[amount],
              expected.get("modal_premium"))
        check("POL_PRM_AMT", modal.get("LH_BAS_POL.POL_PRM_AMT", [None] * 8)[amount], expected.get("pol_prm_amt"))

        coverage_columns = matrices["Coverages"][0]
        if iswl and "coi_scales" in expected:
            scales = sorted([1] + [int(c.split("S")[1]) for c in coverage_columns if c.startswith("COI S")])
            check("COI scales", scales, sorted(expected["coi_scales"]))

        names = {"Coverages": "coverage", "Cash Values": "cash_values",
                 "Premium Rates": "premium_rates", "Modal Premium": "modal_premium"}
        selections = [(c, index if c != "Modal Premium" else 1, matrices[c], names[c])
                      for c in names if matrices[c] and (iswl or c != "Cash Values")]
        shots = capture(policy, selections, config.get("screenshot_dir"))
        report = {
            "all_ok": not failures, "failures": failures,
            "policy": policy.policy_number, "company": policy.company_code,
            "user_code": policy.cyberlife_rate_user_code, "product_type": policy.product_type,
            "coverage": index, "plancode": policy.cov_plancode(index),
            "coverage_columns": coverage_columns,
            "cash_value_count": len(cv_values), "stored_cv_check": cv_info.get("02 Stored CV"),
            "premiums": displayed,
            "modal_lines": {key: row[2:] for key, row in modal.items()},
            "displayed_matches_model": True, "screenshots": shots,
        }
        if config.get("output"):
            write_json(config["output"], report)
        print(json.dumps(report, indent=2, default=str))
        if failures:
            sys.exit(1)
    finally:
        if rates is not None:
            rates.close()


if __name__ == "__main__":
    main()
