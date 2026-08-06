"""Render the PolicyRecordViewerWindow off-screen and save screenshots.

Auditable preview helper to verify the native green-screen policy-record
viewer: the terminal screen, the readable hover tooltip, and the scrollable
Record Layout below.  With a policy number it renders that policy's LIVE DB2
data; with an empty policy it renders the bundled sample screen.

Usage:
    venv\\Scripts\\python.exe tools/policyrecord/preview_policy_record.py
    venv\\Scripts\\python.exe tools/policyrecord/preview_policy_record.py '{"policy": "U0633187", "region": "CKPR"}'
    venv\\Scripts\\python.exe tools/policyrecord/preview_policy_record.py '{"policy": "", "out": "C:/tmp"}'

Config keys (all optional): policy, region, company, out.
Writes <out>/policy_record_top.png, _tooltip.png, _layout.png
(default out: ~/.suiteview; default policy: U0633187).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QApplication, QToolTip
from PyQt6.QtCore import QTimer, QPoint

from suiteview.polview.ui.policy_record_viewer import (
    PolicyRecordViewerWindow, _MainframeToken,
)


def _parse_cfg(argv):
    cfg = {"policy": "U0633187", "region": "CKPR", "company": "", "out": None}
    if len(argv) > 1 and argv[1].strip().startswith("{"):
        cfg.update(json.loads(argv[1]))
    elif len(argv) > 1:
        keys = ("policy", "region", "tab", "out", "tooltip_field")
        cfg.update({
            key: value
            for key, value in zip(keys, argv[1:])
            if value != "-"
        })
    return cfg


def main():
    cfg = _parse_cfg(sys.argv)
    out_dir = Path(cfg["out"]) if cfg.get("out") else (Path.home() / ".suiteview")
    out_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    window = PolicyRecordViewerWindow(
        policy_number=cfg.get("policy", ""),
        region=cfg.get("region", "CKPR"),
        company_code=cfg.get("company", ""),
    )
    window.resize(1160, 720)
    window.show()

    want_tab = str(cfg.get("tab") or "").strip()
    if want_tab:
        for i in range(window.tabs.count()):
            if window.tabs.tabText(i) == want_tab:
                window.tabs.setCurrentIndex(i)
                break

    def capture_top():
        window.grab().save(str(out_dir / "policy_record_top.png"), "PNG")

        # Force a tooltip from an actual token so the token's QToolTip style
        # (dark green card) is what gets rendered -- representative of real hover.
        # An optional "tooltip_field" picks a specific token (e.g. an example
        # value) so its warning banner can be verified.
        want = str(cfg.get("tooltip_field") or "").strip().lower()
        tokens = [t for t in window.findChildren(_MainframeToken) if t.toolTip()]
        token = None
        if want:
            token = next(
                (t for t in tokens if want in t.toolTip().lower()), None
            )
        if token is None:
            token = tokens[0] if tokens else None
        if token is not None:
            QToolTip.showText(
                token.mapToGlobal(QPoint(4, 4)), token.toolTip(), token,
            )
        QTimer.singleShot(300, capture_tooltip)

    def capture_tooltip():
        app.primaryScreen().grabWindow(0).save(
            str(out_dir / "policy_record_tooltip.png"), "PNG"
        )
        QToolTip.hideText()

        # Scroll the current tab to the bottom to show the Record Layout.
        tab = window.tabs.currentWidget()
        bar = tab.verticalScrollBar()
        bar.setValue(bar.maximum())
        QTimer.singleShot(200, capture_layout)

    def capture_layout():
        window.grab().save(str(out_dir / "policy_record_layout.png"), "PNG")
        print(f"Saved previews to {out_dir}")
        app.quit()

    QTimer.singleShot(500, capture_top)
    app.exec()


if __name__ == "__main__":
    main()
