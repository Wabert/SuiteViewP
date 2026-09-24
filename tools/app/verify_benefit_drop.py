"""Verify U0416030 Benefit 39 drop through native inputs, Run Values and saved Compare."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date
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
    parser.add_argument("--case", default="C43B")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    original_hash = hashlib.sha256(args.bundle.read_bytes()).hexdigest()
    checks = {}
    with TemporaryDirectory(prefix="suiteview-benefit-drop-") as profile:
        os.environ["SUITEVIEW_PROFILE_DIR"] = profile
        os.environ["QT_QPA_PLATFORM"] = "windows"
        from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton
        from suiteview.core.rates import owned_rate_connections
        from suiteview.illustration.core.compare_runner import run_scenario
        from suiteview.illustration.models.imported_case_store import load_imported_case
        from suiteview.illustration.ui.inputs_dynamic import FramelessDialog
        from suiteview.illustration.ui.main_window import IllustrationWindow
        from suiteview.illustration.ui.saved_case_scenario import materialize_saved_case

        app = QApplication.instance() or QApplication([])
        source = load_imported_case(args.bundle, args.case)
        case = deepcopy(source)
        assert case.policy_number == "U0416030"
        original = deepcopy(case.policy_snapshot)
        dynamic = case.inputs["dynamic"]
        dynamic.update(illustrated_rate="3.000", lumpsum="", forecast_loan="",
                       forecast_withdrawal="", apply_prem_to_loan=False, tamra=True,
                       riders={})
        for key in dynamic["sections"]:
            dynamic["sections"][key] = []
        dynamic["sections"]["premiums"] = [
            {"type": "Prem to Maturity", "year": "25", "mode": "M"},
        ]
        messages = []

        def message(_parent, title, text, *unused):
            messages.append(f"{title}: {text}")
            return QMessageBox.StandardButton.Ok

        window = IllustrationWindow()
        try:
            with (owned_rate_connections(),
                  patch.object(QMessageBox, "information", message),
                  patch.object(QMessageBox, "warning", message),
                  patch.object(QMessageBox, "critical", message)):
                control = run_scenario(materialize_saved_case(case, strict=True))
                assert control.ok, control.error
                window._load_case_snapshot(case)
                window.show()
                app.processEvents()
                panel = window.inputs_tab.dynamic_panel.riders_panel
                selected = []

                def choose_drop(dialog):
                    buttons = {button.text(): button for button in dialog.findChildren(QPushButton)}
                    checks["drop_button_enabled"] = buttons["Drop rider"].isEnabled()
                    assert checks["drop_button_enabled"]
                    buttons["Drop rider"].click()
                    dialog.show()
                    app.processEvents()
                    if args.screenshot:
                        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                        assert dialog.grab().save(str(args.screenshot))
                    selected.append(True)
                    dialog.accept()
                    return 1

                with patch.object(FramelessDialog, "exec", choose_drop):
                    panel._buttons["ben:39:1"].click()
                assert selected
                events = window.inputs_tab.export_input_set().policy_changes
                checks["exports_drop_at_forecast"] = (
                    len(events) == 1 and events[0].metadata["target"] == "ben:39:1"
                    and events[0].value == 0 and events[0].effective_date == date(2026, 10, 15))
                window._on_run_values()
                assert window.values_tab._current_view is not None, messages
                current = window.values_tab._current_view[1]
                guaranteed = window.values_tab._guaranteed_view[1]
                for label, rows in (("current", current), ("guaranteed", guaranteed)):
                    future = [row for row in rows if row.date >= date(2026, 10, 15)]
                    checks[f"{label}_no_charges_after_drop"] = bool(future) and all(
                        row.benefit_charges == 0 for row in future)
                checks["keep_control_has_waiver_charges"] = any(
                    row.benefit_charges > 0 for row in control.results
                    if date(2026, 10, 15) <= row.date < date(2028, 2, 15))
                case.inputs["dynamic"]["riders"] = panel.capture_adjustments()
                # JSON round trip exercises the persisted rider decision shape.
                case.inputs["dynamic"]["riders"] = json.loads(json.dumps(
                    case.inputs["dynamic"]["riders"]))
                restored = run_scenario(materialize_saved_case(case, strict=True))
                assert restored.ok, restored.error
                checks["saved_compare_matches_native"] = restored.results == current
                checks["snapshot_unchanged"] = case.policy_snapshot == original
                checks["no_ui_errors"] = not messages
        finally:
            window.close()
            window.deleteLater()
            app.processEvents()
    checks["source_file_unchanged"] = hashlib.sha256(args.bundle.read_bytes()).hexdigest() == original_hash
    report = {"checks": checks, "all_ok": all(checks.values())}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
