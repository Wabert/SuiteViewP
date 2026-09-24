"""Read-only native verification of the live Policy tab's Calculated MD."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise ValueError("Live verification cannot use local policy data.")

    with tempfile.TemporaryDirectory(prefix="suiteview-md-ui-") as profile:
        os.environ["SUITEVIEW_PROFILE_DIR"] = profile
        from PyQt6.QtWidgets import QApplication, QMessageBox
        from suiteview.illustration.ui.main_window import IllustrationWindow
        from suiteview.polview.ui.formatting import format_currency

        def fail_dialog(_parent, title, text, *_args, **_kwargs):
            raise RuntimeError(f"{title}: {text}")

        app = QApplication.instance() or QApplication([])
        window = IllustrationWindow()
        try:
            with patch.object(QMessageBox, "critical", fail_dialog), patch.object(
                QMessageBox, "warning", fail_dialog,
            ):
                window._on_get_policy(
                    args.policy.strip().upper(), args.region.strip().upper(),
                    args.company.strip().upper(),
                )
            checks = window._live_policy_checks
            if checks is None or checks[2] is None:
                raise AssertionError(window.policy_tab.rate_warning_label.text())
            expected = format_currency(checks[2].md_check_calculated_deduction, "$")
            before = window.policy_tab.policy_info.get_value("calculated_md")
            window._refresh_policy_basis()
            after = window.policy_tab.policy_info.get_value("calculated_md")
            result = {
                "policy": args.policy,
                "cyberlife_md": window.policy_tab.policy_info.get_value("cyberlife_md"),
                "calculated_md": after,
                "survives_refresh": before == after == expected,
                "warnings_preserved": window.policy_tab.rate_warning_label.text()
                == "\n".join(checks[1]),
            }
            window.resize(1500, 900)
            window.show()
            app.processEvents()
            label = window.policy_tab.policy_info._labels["calculated_md"]
            result["label_visible"] = label.isVisible() and bool(label.text())
            if args.screenshot:
                args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                if not window.grab().save(str(args.screenshot), "PNG"):
                    raise RuntimeError(f"Cannot save screenshot: {args.screenshot}")
            result["all_ok"] = all(result[key] for key in (
                "survives_refresh", "warnings_preserved", "label_visible"))
            print(json.dumps(result, indent=2))
            return 0 if result["all_ok"] else 1
        finally:
            window.close()
            app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
