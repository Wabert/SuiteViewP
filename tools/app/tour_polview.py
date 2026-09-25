"""Load live policies in native PolView and screenshot every tab (read-only).

Uses an isolated temporary profile. Writes one PNG per tab per policy and a
JSON report of tab titles/states to --output-dir.

    venv\\Scripts\\python.exe tools/app/tour_polview.py --policy U0613620 --company 01 --output-dir <dir>
    venv\\Scripts\\python.exe tools/app/tour_polview.py --policy U0613620 --policy 13034048 --output-dir <dir>
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower() or "tab"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", action="append", required=True,
                        help="Policy number; repeat for several. Use POLICY:CO to pin a company.")
    parser.add_argument("--company", default="")
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--size", default="1400x860")
    parser.add_argument("--tabs", default="", help="Comma-separated tab-title filter")
    parser.add_argument("--panels", action="store_true",
                        help="Also open the Tables & Rates panel's Tables view")
    parser.add_argument("--dialogs", action="store_true",
                        help="After the last policy, open Timeline and Compare (vs earlier policies)")
    args = parser.parse_args()
    width, height = (int(v) for v in args.size.lower().split("x"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = {"policies": [], "ui_messages": []}

    with TemporaryDirectory(prefix="suiteview-polview-tour-") as profile:
        os.environ["SUITEVIEW_PROFILE_DIR"] = profile
        from PyQt6.QtCore import QEventLoop, QTimer, qInstallMessageHandler
        from PyQt6.QtWidgets import QApplication, QMessageBox
        from suiteview.polview.ui import main_window

        def qt_message(mode, context, message):
            sys.stderr.write(f"[Qt {mode.name}] {message} ({context.file}:{context.line})\n")
            sys.stderr.flush()

        qInstallMessageHandler(qt_message)
        app = QApplication.instance() or QApplication([])

        def dialog(_parent, title, message, *unused):
            report["ui_messages"].append(f"{title}: {message}")
            return QMessageBox.StandardButton.Ok

        def pump(ms: int):
            loop = QEventLoop()
            QTimer.singleShot(ms, loop.quit)
            loop.exec()

        def wait_until(predicate, timeout_ms=180000):
            loop = QEventLoop()
            poll = QTimer()
            poll.setInterval(20)
            poll.timeout.connect(lambda: loop.quit() if predicate() else None)
            timeout = QTimer()
            timeout.setSingleShot(True)
            timeout.timeout.connect(loop.quit)
            poll.start()
            timeout.start(timeout_ms)
            if not predicate():
                loop.exec()
            poll.stop()
            timeout.stop()
            return predicate()

        wanted = {t.strip().lower() for t in args.tabs.split(",") if t.strip()}
        with patch.object(QMessageBox, "information", dialog), \
                patch.object(QMessageBox, "warning", dialog), \
                patch.object(QMessageBox, "critical", dialog), \
                patch.object(main_window, "_show_odbc_warning",
                             lambda _p, dsn, error_detail="": report["ui_messages"].append(
                                 f"{dsn}: {error_detail}")):
            window = main_window.GetPolicyWindow()
            window.resize(width, height)
            window.show()
            pump(300)
            for spec in args.policy:
                policy, _, company = spec.partition(":")
                company = company or args.company
                settled = {"done": False}

                def on_settled(*_a, flag=settled):
                    flag["done"] = True

                window.background_ready.connect(on_settled)
                window.load_policy(policy, region=args.region, company_code=company)
                ok = wait_until(lambda: settled["done"])
                window.background_ready.disconnect(on_settled)
                pump(400)
                entry = {"policy": policy, "company": company, "settled": ok, "tabs": []}
                for index in range(window.tabs.count()):
                    title = window.tabs.tabText(index).replace("&&", "&")
                    if wanted and not any(w in title.lower() for w in wanted):
                        continue
                    enabled = window.tabs.isTabEnabled(index)
                    shot = None
                    if enabled:
                        window.tabs.setCurrentIndex(index)
                        pump(700)
                        shot = args.output_dir / f"{_slug(policy)}_{index:02d}_{_slug(title)}.png"
                        window.grab().save(str(shot), "PNG")
                    entry["tabs"].append({
                        "index": index, "title": title, "enabled": enabled,
                        "tooltip": window.tabs.tabToolTip(index),
                        "screenshot": str(shot) if shot else None,
                    })
                entry["status"] = window._status_label.text()
                if args.panels:
                    window._toggle_tree_panel()
                    window.records_tree._on_tab_clicked("tables")
                    pump(500)
                    shot = args.output_dir / f"{_slug(policy)}_panel_tables.png"
                    window.grab().save(str(shot), "PNG")
                    tree = window.records_tree._tree
                    entry["tables_panel"] = [
                        tree.topLevelItem(i).text(0).strip() for i in range(tree.topLevelItemCount())
                    ]
                    window._toggle_tree_panel()
                report["policies"].append(entry)
            if args.dialogs:
                from suiteview.polview.ui.polview_dialogs import CompareDialog, TimelineDialog

                window._open_timeline()
                window._open_compare()
                pump(600)
                for dialog in window._dialogs:
                    kind = "timeline" if isinstance(dialog, TimelineDialog) else (
                        "compare" if isinstance(dialog, CompareDialog) else "dialog")
                    shot = args.output_dir / f"dialog_{kind}.png"
                    dialog.grab().save(str(shot), "PNG")
                    info = {"kind": kind, "screenshot": str(shot), "rows": dialog.table.rowCount()}
                    if kind == "compare":
                        info["summary"] = dialog.summary.text()
                    report.setdefault("dialogs", []).append(info)
            window.close()
            pump(200)
            window._loader.shutdown()

    (args.output_dir / "tour.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    code = 0 if all(p["settled"] for p in report["policies"]) else 1
    # Skip interpreter teardown of Qt objects; the report is already written.
    os._exit(code)


if __name__ == "__main__":
    raise SystemExit(main())
