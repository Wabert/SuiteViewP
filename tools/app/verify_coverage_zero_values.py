"""Check live DB2 coverage amounts against the actual PolView coverage grid.

Usage: venv\\Scripts\\python.exe tools\\app\\verify_coverage_zero_values.py @config.json
JSON keys: policy (required), company, region, screenshot, output.
Read-only; refuses local data and requires at least one zero specified amount.
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtWidgets import QApplication

from suiteview.core.json_store import write_json
from suiteview.core.local_dev import local_data_enabled
from suiteview.core.policy_service import get_policy_info
from suiteview.polview.ui.formatting import format_amount
from suiteview.polview.ui.tabs.coverages_tab import CoveragesTab


def main():
    arg = sys.argv[1]
    config = json.loads(
        Path(arg[1:]).read_text(encoding="utf-8") if arg.startswith("@") else arg
    )
    if local_data_enabled():
        raise RuntimeError("Live DB2 verification cannot use local SQLite data.")
    policy = get_policy_info(
        config["policy"].strip().upper(),
        company_code=config.get("company"),
        region=config.get("region", "CKPR"),
        use_cache=False,
    )
    if policy is None or not policy.exists:
        raise RuntimeError("Policy not found or live DB2 access failed.")

    rows = policy.fetch_table("LH_COV_PHA")
    coverages = policy.get_coverages()
    if not rows or len(coverages) != len(rows):
        raise RuntimeError("Coverage model does not contain every DB2 row.")
    app = QApplication.instance() or QApplication([])
    tab = CoveragesTab()
    try:
        tab._populate_coverages_from_policy(policy, coverages)
        table = tab.cov_table
        columns = {
            table._data_table.horizontalHeaderItem(col).text(): col
            for col in range(table.columnCount())
        }
        checks = []
        zero_amounts = 0
        for index, (raw, coverage) in enumerate(zip(rows, coverages)):
            vpu = raw.get("COV_VPU_AMT")
            for field, attribute, column in (
                ("COV_UNT_QTY", "face_amount", "Amount"),
                ("OGN_SPC_UNT_QTY", "orig_amount", "Orig Amt"),
            ):
                units = raw.get(field)
                expected = (
                    Decimal(str(units)) * Decimal(str(vpu))
                    if units is not None and vpu is not None else None
                )
                actual = getattr(coverage, attribute)
                if actual != expected:
                    raise AssertionError(f"Phase {coverage.cov_pha_nbr}: {attribute} != DB2 amount")
                if column not in columns:
                    continue
                displayed = table.item(index, columns[column]).text()
                if displayed != format_amount(expected):
                    raise AssertionError(f"Phase {coverage.cov_pha_nbr}: {column} displayed {displayed!r}")
                if column == "Amount" and expected == 0:
                    zero_amounts += 1
                checks.append({
                    "phase": coverage.cov_pha_nbr, "column": column,
                    "db2_amount": str(expected) if expected is not None else None,
                    "displayed": displayed,
                })
        if zero_amounts == 0:
            raise AssertionError("No zero current specified amounts were exercised.")
        if config.get("screenshot"):
            tab.resize(1500, 620)
            tab.show()
            app.processEvents()
            target = Path(config["screenshot"])
            target.parent.mkdir(parents=True, exist_ok=True)
            if not tab.cov_group.grab().save(str(target), "PNG"):
                raise RuntimeError(f"Could not save screenshot: {target}")
        report = {
            "all_ok": True, "policy": policy.policy_number,
            "company": policy.company_code, "coverage_count": len(coverages),
            "zero_current_amounts": zero_amounts, "checks": checks,
        }
        if config.get("output"):
            write_json(Path(config["output"]), report)
        print(json.dumps(report, indent=2))
    finally:
        tab.close()
        app.processEvents()


if __name__ == "__main__":
    main()
