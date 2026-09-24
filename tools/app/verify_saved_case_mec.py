"""Read-only MEC verification for a saved bundle, optionally through native Run Values."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--case", required=True)
    parser.add_argument("--tamra", choices=("on", "off"), default="off")
    parser.add_argument("--expect-year", type=int)
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.screenshot and not args.native:
        parser.error("--screenshot requires --native")
    source_hash = hashlib.sha256(args.bundle.read_bytes()).hexdigest()
    report = {"checks": {}}
    checks = report["checks"]
    with TemporaryDirectory(prefix="suiteview-mec-") as profile:
        os.environ["SUITEVIEW_PROFILE_DIR"] = profile
        os.environ.setdefault("QT_QPA_PLATFORM", "windows" if args.native else "offscreen")
        from PyQt6.QtWidgets import QApplication, QMessageBox
        from suiteview.core.rates import owned_rate_connections
        from suiteview.illustration.core.compare_runner import _mec_status, run_scenario
        from suiteview.illustration.core.report_builder import _annualize
        from suiteview.illustration.models.imported_case_store import load_imported_case
        from suiteview.illustration.ui.saved_case_scenario import materialize_saved_case
        from suiteview.illustration.ui.values_overview import LEDGER_COLUMNS, _status_text

        app = QApplication.instance() or QApplication([])
        case = load_imported_case(args.bundle, args.case)
        original = deepcopy(case)
        case = deepcopy(case)
        case.inputs["dynamic"]["tamra"] = args.tamra == "on"
        with owned_rate_connections():
            spec = materialize_saved_case(case, strict=True)
            outcome = run_scenario(spec)
            results = outcome.results
            assert results is not None
            checks["requested_tamra_option"] = outcome.options.conform_to_tamra == (args.tamra == "on")
            rows, report_year, _ = _annualize(outcome.policy, results, outcome.options)
            first = next((s for s in results[1:] if s.is_mec), None)
            breached = next((
                s for s in results[1:]
                if 1 <= s.tamra_year <= 7
                and s.accumulated_7pay > s.tamra_7pay_level * s.tamra_year + 0.005
            ), None)
            report.update(
                policy=case.policy_number, case=case.name, tamra=args.tamra,
                first_mec_date=first.date if first else None,
                first_mec_year=first.mec_year if first else None,
                first_excess_date=breached.date if breached else None,
                first_excess_year=breached.policy_year if breached else None,
                contributions=breached.accumulated_7pay if breached else None,
                seven_pay_level=breached.tamra_7pay_level if breached else None,
                tamra_year=breached.tamra_year if breached else None,
                seven_pay_start=breached.tamra_7pay_start_date if breached else None,
                report_mec_year=report_year,
                compare_status=_mec_status(outcome.policy, results[1:]),
                values_status=_status_text(first) if first else "",
            )
            if args.expect_year is not None:
                checks["expected_engine_year"] = first is not None and first.mec_year == args.expect_year
                checks["expected_report_year"] = report_year == args.expect_year
                checks["expected_compare_year"] = report["compare_status"] == f"Becomes MEC (Yr {args.expect_year})"
                checks["values_status"] = first is not None and "MEC" in _status_text(first)
                checks["report_marker"] = any(r.year == args.expect_year and "&" in r.markers for r in rows)
            checks["snapshot_unchanged"] = case.policy_snapshot == original.policy_snapshot
            if args.native:
                from suiteview.illustration.ui.main_window import IllustrationWindow

                messages = []

                def message(_parent, title, text, *unused):
                    messages.append(f"{title}: {text}")
                    return QMessageBox.StandardButton.Ok

                window = IllustrationWindow()
                try:
                    with (patch.object(QMessageBox, "information", message),
                          patch.object(QMessageBox, "warning", message),
                          patch.object(QMessageBox, "critical", message)):
                        window._load_case_snapshot(case)
                        window._on_run_values()
                    assert window.values_tab._current_view is not None, messages
                    native_results = window.values_tab._current_view[1]
                    checks["native_matches_compare"] = native_results == results
                    checks["native_guaranteed_available"] = window.values_tab._guaranteed_view is not None
                    checks["no_native_errors"] = not messages
                    ledger = window.values_tab.overview.ledger
                    status_column = LEDGER_COLUMNS.index("Status")
                    visible_mec_year = next((
                        int(ledger.topLevelItem(i).text(0))
                        for i in range(ledger.topLevelItemCount())
                        if "MEC" in ledger.topLevelItem(i).text(status_column)
                    ), None)
                    report["native_ledger_first_mec_year"] = visible_mec_year
                    if args.expect_year is not None:
                        checks["native_ledger_mec_year"] = visible_mec_year == args.expect_year
                    if args.screenshot:
                        window.values_tab.overview.simple_toggle.setChecked(True)
                        window.show()
                        app.processEvents()
                        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                        assert window.grab().save(str(args.screenshot))
                    report["native_messages"] = messages
                finally:
                    window.close()
                    window.deleteLater()
                    app.processEvents()
    checks["saved_file_unchanged"] = hashlib.sha256(args.bundle.read_bytes()).hexdigest() == source_hash
    report["all_ok"] = all(checks.values())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
