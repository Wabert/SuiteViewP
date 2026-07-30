"""Render the Audit Custom Display tab standalone and save a screenshot.

Single-purpose helper: builds a CustomDisplayTab, shows it in a plain window,
selects a table/field in the first row so the criteria controls are visible,
and grabs a PNG for visual verification. No DB2 access required.

Usage:
    venv\\Scripts\\python.exe tools/render_custom_display_tab.py
"""
from __future__ import annotations

import os
import sys

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import Qt, QTimer

# Ensure repo root is importable when run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from suiteview.audit.tabs.custom_display_tab import CustomDisplayTab

_OUT = os.path.join(os.path.expanduser("~"), ".suiteview", "custom_display_tab.png")


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)

    tab = CustomDisplayTab()
    # Enable the first row and pick a table so the field/criteria controls show.
    r = tab.rows[0]
    r.chk_enable.setChecked(True)
    lw = r.combo_tables.list_widget
    items = lw.findItems("Policy (LH_BAS_POL)", Qt.MatchFlag.MatchExactly)
    if items:
        items[0].setSelected(True)
    r.combo_criteria.setCurrentText("Contains")
    r.txt_criteria.setText("SMITH")

    win = QMainWindow()
    win.setWindowTitle("Custom Display Tab")
    win.setCentralWidget(tab)
    win.resize(1150, 200)
    win.show()

    def _capture() -> None:
        os.makedirs(os.path.dirname(_OUT), exist_ok=True)
        win.grab().save(_OUT)
        print(_OUT)
        app.quit()

    QTimer.singleShot(400, _capture)
    app.exec()


if __name__ == "__main__":
    main()
