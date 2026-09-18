"""Render the PolicyRecordViewerWindow off-screen and save screenshots.

Auditable preview helper to verify the native green-screen policy-record
viewer: the terminal screen, the readable hover tooltip, and the scrollable
Record Layout below.  With a policy number it renders that policy's LIVE DB2
data; with an empty policy it shows the no-policy state.

Usage:
    venv\\Scripts\\python.exe tools/policyrecord/preview_policy_record.py
    venv\\Scripts\\python.exe tools/policyrecord/preview_policy_record.py '{"policy": "U0633187", "region": "CKPR"}'
    venv\\Scripts\\python.exe tools/policyrecord/preview_policy_record.py '{"policy": "", "out": "C:/tmp"}'

Config may also be read from @path.json. Optional verification keys:
expect_absent (absent or unsupported segment list), expect_live (segment list), copy_field
(a tooltip field to copy through the real native menu on the selected tab).
Set expect_no_errors to require every displayed segment to be error-free.
Writes <out>/policy_record_top.png, _tooltip.png, _layout.png
(default out: ~/.suiteview/diagnostics; default policy: U0633187).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.profile_paths import diagnostics_dir

from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QTextBrowser, QToolTip
from PyQt6.QtCore import QMimeData, QTimer, QPoint, Qt
from PyQt6.QtTest import QTest

from suiteview.polview.ui.policy_record_viewer import (
    PolicyRecordViewerWindow, _MainframeToken, _TerminalScreen, _UNAVAILABLE_MESSAGE,
)


def _parse_cfg(argv):
    cfg = {"policy": "U0633187", "region": "CKPR", "company": "", "out": None}
    if len(argv) > 1 and argv[1].startswith("@"):
        cfg.update(json.loads(Path(argv[1][1:]).read_text(encoding="utf-8")))
    elif len(argv) > 1 and argv[1].strip().startswith("{"):
        cfg.update(json.loads(argv[1]))
    elif len(argv) > 1:
        keys = ("policy", "region", "tab", "out", "tooltip_field")
        cfg.update({
            key: value
            for key, value in zip(keys, argv[1:])
            if value != "-"
        })
    return cfg


def _verify(window, cfg, app):
    tabs = {}
    for index in range(window.tabs.count()):
        tab = window.tabs.widget(index)
        labels = [label.text() for label in tab.findChildren(QLabel)]
        live = bool(tab.findChildren(_TerminalScreen))
        if not live:
            assert any(text.startswith("LIVE DATA ERROR") for text in labels)
            assert not tab.findChildren(_MainframeToken)
            assert not tab.findChildren(QTextBrowser)
            assert _UNAVAILABLE_MESSAGE in labels
        assert not any("CAPTURED REFERENCE" in text for text in labels)
        tabs[window.tabs.tabText(index)] = {
            "live": live, "error": any(text.startswith("LIVE DATA ERROR") for text in labels),
        }
    assert set(cfg.get("expect_absent", [])).isdisjoint(tabs), "An absent segment is still visible."
    for segment in cfg.get("expect_live", []):
        assert segment in tabs and tabs[segment]["live"] and not tabs[segment]["error"]
    if cfg.get("expect_no_errors"):
        assert not any(tab["error"] for tab in tabs.values()), "A segment has a live data error."
    result = {"tabs": tabs}
    if cfg.get("copy_field"):
        tab = window.tabs.currentWidget()
        field = cfg["copy_field"].lower()
        token = next(token for token in tab.findChildren(_MainframeToken)
                     if field in token.toolTip().lower())
        clipboard = app.clipboard()
        saved = QMimeData()
        current = clipboard.mimeData()
        if current is not None:
            for mime_type in current.formats():
                saved.setData(mime_type, current.data(mime_type))
        menu_seen = []

        def choose_copy():
            menu = app.activePopupWidget()
            if isinstance(menu, QMenu):
                menu_seen.append(True)
                QTest.keyClick(menu, Qt.Key.Key_Down)
                QTest.keyClick(menu, Qt.Key.Key_Return)

        try:
            QTimer.singleShot(100, choose_copy)
            token.customContextMenuRequested.emit(QPoint(1, 1))
            assert menu_seen, "Native Copy menu did not open."
            assert clipboard.text() == token.text(), "Clipboard did not receive the displayed value."
            result["copy_verified"] = True
        finally:
            clipboard.setMimeData(saved)
    return result


def main():
    cfg = _parse_cfg(sys.argv)
    out_dir = Path(cfg["out"]) if cfg.get("out") else (diagnostics_dir())
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
        else:
            raise ValueError(f"Requested segment {want_tab} is not present for this policy.")
    app.processEvents()
    verification = _verify(window, cfg, app)
    (out_dir / "policy_record_state.json").write_text(
        json.dumps(verification, indent=2), encoding="utf-8",
    )
    print(json.dumps(verification))

    def capture_top():
        window.grab().save(str(out_dir / "policy_record_top.png"), "PNG")

        # Force a tooltip from an actual token so the token's QToolTip style
        # (dark green card) is what gets rendered -- representative of real hover.
        # An optional "tooltip_field" picks a specific token (e.g. an example
        # value) so its warning banner can be verified.
        want = str(cfg.get("tooltip_field") or "").strip().lower()
        tab = window.tabs.currentWidget()
        tokens = [t for t in tab.findChildren(_MainframeToken) if t.toolTip()] if tab else []
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
        if tab is not None:
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
