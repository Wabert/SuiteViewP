"""Check that PolView tooltips render dark text on a light background (native).

Opens a PolView window without loading a policy (no DB access), shows the
tooltips of several representative widgets through Qt's normal tooltip path,
grabs each tooltip and measures its background and text luminance.

    venv\\Scripts\\python.exe tools/app/verify_polview_tooltips.py --output-dir <dir>
Prints JSON; exits non-zero when any tooltip lacks contrast.
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def luminance(color) -> float:
    return (0.2126 * color.red() + 0.7152 * color.green() + 0.0722 * color.blue()) / 255


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    with TemporaryDirectory(prefix="suiteview-tooltips-") as profile:
        os.environ["SUITEVIEW_PROFILE_DIR"] = profile
        from PyQt6.QtCore import QEventLoop, QPoint, QTimer
        from PyQt6.QtGui import QColor
        from PyQt6.QtWidgets import QApplication, QToolTip
        from suiteview.polview.ui.main_window import GetPolicyWindow

        app = QApplication.instance() or QApplication([])
        window = GetPolicyWindow(enable_policy_list=False)
        window.show()

        def pump(ms):
            loop = QEventLoop()
            QTimer.singleShot(ms, loop.quit)
            loop.exec()

        pump(300)
        targets = {
            "lookup policy box": window.lookup_bar.policy_input,
            "tables button": window._tree_toggle_btn,
            "coverages info value": window.coverages_tab.info_group._fields["status_label"],
            "policy tab value": window.policy_tab.col1._fields["prm_paid_to"],
            "summary strip button": window.summary_strip.copy_button,
            "tab bar": window.tabs.tabBar(),
            "table cell viewport": window.coverages_tab.cov_table._data_table.viewport(),
        }
        for name, widget in targets.items():
            text = widget.toolTip() or f"Tooltip check for {name}"
            QToolTip.showText(widget.mapToGlobal(QPoint(4, 4)), text, widget)
            pump(250)
            tip = next((w for w in QApplication.topLevelWidgets()
                        if w.objectName() == "qtooltip_label" and w.isVisible()), None)
            entry = {"widget": name, "shown": tip is not None}
            if tip is not None:
                image = tip.grab().toImage()
                counts = Counter()
                for x in range(2, image.width() - 2, 2):
                    for y in range(2, image.height() - 2, 2):
                        counts[image.pixel(x, y)] += 1
                background = QColor(counts.most_common(1)[0][0])
                darkest = min((QColor(p) for p in counts), key=luminance)
                shot = args.output_dir / f"tooltip_{name.replace(' ', '_')}.png"
                image.save(str(shot))
                entry.update({
                    "background": background.name(), "background_luminance": round(luminance(background), 3),
                    "text": darkest.name(), "text_luminance": round(luminance(darkest), 3),
                    "stylesheet": tip.styleSheet()[:40], "screenshot": str(shot),
                    "readable": luminance(background) > 0.8 and luminance(background) - luminance(darkest) > 0.5,
                })
            results.append(entry)
            QToolTip.hideText()
            pump(600)
        window.close()
        window._loader.shutdown()
    ok = all(r.get("readable") for r in results)
    print(json.dumps({"all_ok": ok, "tooltips": results}, indent=2), flush=True)
    os._exit(0 if ok else 1)


if __name__ == "__main__":
    main()
