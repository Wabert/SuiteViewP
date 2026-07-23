"""
Diagnostic: render the Coverage Level checkbox variants to compare styling.

Renders three checked checkboxes and saves a PNG so we can see whether the
AuditBottomBar parent stylesheet cascade changes the indicator rendering:

  A. Shared make_checkbox() standalone (the "correct" look)
  B. Current inline-styled checkbox INSIDE an AuditBottomBar-styled container
  C. Shared make_checkbox() INSIDE an AuditBottomBar-styled container

Usage:
    venv\\Scripts\\python.exe tools/diag_coverage_checkbox.py [output_path]
"""
import os
import sys
from pathlib import Path

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QCheckBox,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import QTimer

from suiteview.audit.tabs._styles import (
    make_checkbox, _ensure_checkmark, _CHECKMARK_PATH,
)
from suiteview.audit.ui.bottom_bar import FOOTER_BG
from suiteview.ui.theme import apply_global_theme


def _inline_checkbox() -> QCheckBox:
    """Replicates the current audit_window.py inline style."""
    _ensure_checkmark()
    icon = _CHECKMARK_PATH.replace("\\", "/")
    cb = QCheckBox("Coverage Level")
    cb.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
    cb.setStyleSheet(
        "QCheckBox::indicator { border: 1px solid #1E5BA8; width: 12px;"
        " height: 12px; background-color: white; }"
        "QCheckBox::indicator:checked {"
        "  background-color: #1E5BA8; border: 1px solid #14407A;"
        f"  image: url({icon});"
        "}")
    return cb


def _bar_container(child: QCheckBox) -> QWidget:
    box = QWidget()
    box.setStyleSheet(
        f"QWidget {{ background-color: {FOOTER_BG}; color: #111; }}"
        "QLabel { background-color: transparent; }"
    )
    lay = QVBoxLayout(box)
    lay.addWidget(child)
    return box


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else str(
        Path.home() / ".suiteview" / "diag_checkbox.png"
    )
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    app.setStyle("Fusion")

    root = QWidget()
    root.setStyleSheet("background: #ffffff;")
    v = QVBoxLayout(root)

    a = make_checkbox("Coverage Level", checked=True)
    v.addWidget(QLabel("A. make_checkbox standalone (target look):"))
    v.addWidget(a)

    b = _inline_checkbox()
    b.setChecked(True)
    v.addWidget(QLabel("B. current inline style inside bottom-bar cascade:"))
    v.addWidget(_bar_container(b))

    c = make_checkbox("Coverage Level", checked=True)
    v.addWidget(QLabel("C. make_checkbox inside bottom-bar cascade:"))
    v.addWidget(_bar_container(c))

    root.resize(360, 240)
    root.show()

    def capture():
        pix = root.grab()
        pix.save(output, "PNG")
        print(f"Saved {output}")
        app.quit()

    QTimer.singleShot(300, capture)
    app.exec()


if __name__ == "__main__":
    main()
