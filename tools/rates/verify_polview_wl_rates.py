"""Verify a live policy's PolView WL cash-value matrix and optionally capture it.

Usage: venv\\Scripts\\python.exe tools\\rates\\verify_polview_wl_rates.py @config.json
Config: policy, company, region, coverage (1-based), output, screenshot, expected.
Expected may contain rate_key, issue_age, count, and rates keyed by duration.
Alternatively, expected.message verifies an unavailable-file message in the
actual Rates view without looking up a schedule (screenshot remains optional).
Only reads live policy/rate data; the screenshot loads just the Rates surface.
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.json_store import write_json
from suiteview.core.local_dev import local_data_enabled
from suiteview.core.policy_service import get_policy_info


def capture(policy, index, expected_result, output):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    from suiteview.polview.ui.main_window import GetPolicyWindow

    app = QApplication.instance() or QApplication([])
    window = GetPolicyWindow(enable_policy_list=False)
    try:
        window._policy = policy
        window.lookup_bar.set_policy_display(policy.company_code, policy.policy_number, policy.region)
        window.records_tree.enable_rates_tab(policy)
        window.records_tree.show_rates_tab()
        window._toggle_tree_panel()
        window.resize(1180, 880)
        window.move(100, 60)
        window.show()
        tree = window.records_tree._tree
        parent = tree.topLevelItem(0)
        parent.setExpanded(True)
        item = parent.child(index - 1)
        tree.setCurrentItem(item)
        tree._on_item_clicked(item, 0)
        raw = window.raw_table_tab
        if isinstance(expected_result, str):
            if raw._current_cols or raw._current_rows:
                raise RuntimeError("An unavailable-file message must clear previous rates.")
            for grid in (raw._normal_grid, raw._transposed_grid):
                actual = grid.model.data(grid.model.index(0, 0), Qt.ItemDataRole.DisplayRole)
                if actual != expected_result:
                    raise RuntimeError(f"Unexpected Rates message: {actual!r}")
        elif (raw._current_cols != expected_result[0]
                or raw._current_rows != [tuple(row) for row in expected_result[1:]]):
            raise RuntimeError("The actual PolView rate selection did not display the verified matrix.")
        app.processEvents()
        window.repaint()
        app.processEvents()
        if output:
            target = Path(output)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not window.grab().save(str(target), "PNG"):
                raise RuntimeError(f"Could not save screenshot: {target}")
    finally:
        window.close()
        app.processEvents()


def main():
    arg = sys.argv[1]
    config = json.loads(Path(arg[1:]).read_text(encoding="utf-8")) if arg.startswith("@") else json.loads(arg)
    if local_data_enabled():
        raise RuntimeError("This verification requires live data, not SUITEVIEW_LOCAL_DATA.")
    policy = get_policy_info(
        config["policy"], region=config.get("region", "CKPR"),
        company_code=config.get("company"), use_cache=False,
    )
    if policy is None or not policy.exists:
        raise RuntimeError("Policy was not found or live policy access failed.")
    if policy.is_advanced_product or policy.product_type != "WL":
        raise RuntimeError("Select a traditional Whole Life policy.")
    index = config.get("coverage", 1)
    expected = config.get("expected", {})
    if "message" in expected:
        message = expected["message"]
        if not isinstance(message, str) or not message:
            raise ValueError("expected.message must be a nonempty string.")
        capture(policy, index, message, config.get("screenshot"))
        report = {
            "all_ok": True, "policy": policy.policy_number, "company": policy.company_code,
            "coverage": index, "premium_pay_status": policy.premium_pay_status_description,
            "message": message,
        }
        if config.get("output"):
            write_json(config["output"], report)
        print(json.dumps(report, indent=2))
        return
    key, age = policy.cov_cash_value_key(index), policy.cov_issue_age(index)
    rates = policy._get_rates()
    try:
        matrix = policy.build_coverage_rate_matrix(index)
        if not matrix:
            raise RuntimeError(f"No cash-value schedule for company {policy.company_code}, key {key}, age {age}.")
        duration_column = matrix[0].index("Duration")
        rate_column = matrix[0].index("CV")
        actual = {
            row[duration_column]: row[rate_column] for row in matrix[1:]
            if row[duration_column] != ""
        }
        cursor = rates._get_connection().cursor()
        try:
            raw = cursor.execute(
                "SELECT [DURATION], [RATE] FROM [WL_RATE_CV] "
                "WHERE [USER_CODE] = ? AND [RATE_KEY] = ? AND [ISSUE_AGE] = ? "
                "AND [USER_DEFINED] = ? ORDER BY [DURATION]",
                [policy.company_code, key, age, ""],
            ).fetchall()
        finally:
            cursor.close()
        if actual != dict(raw):
            raise RuntimeError("PolView displayed durations/rates differ from the database.")
        observed = {"rate_key": key, "issue_age": age, "count": len(actual)}
        for field in ("rate_key", "issue_age", "count"):
            if field in expected and expected[field] != observed[field]:
                raise RuntimeError(f"Unexpected {field}: {observed[field]}")
        for duration, value in expected.get("rates", {}).items():
            if actual.get(int(duration)) != Decimal(value):
                raise RuntimeError(f"Unexpected cash-value rate at duration {duration}.")
        report = {
            "all_ok": True, "policy": policy.policy_number, "company": policy.company_code,
            "coverage": index, "plancode": policy.cov_plancode(index), **observed,
            "user_defined": "", "source": "WL_RATE_CV",
            "first_duration": min(actual), "last_duration": max(actual),
            "database_matches_display": True,
            "rates": {str(duration): str(value) for duration, value in actual.items()},
        }
        if config.get("screenshot"):
            capture(policy, index, matrix, config["screenshot"])
            report["screenshot"] = config["screenshot"]
        if config.get("output"):
            write_json(config["output"], report)
        print(json.dumps(report, indent=2))
    finally:
        if rates is not None:
            rates.close()


if __name__ == "__main__":
    main()
