"""Shared worker and panel helpers for UL and Term workups."""

from __future__ import annotations

import os
import subprocess
import sys

from PyQt6.QtWidgets import QLabel, QMessageBox, QPushButton, QWidget

from suiteview.ratemanager.rm_styles import TEXT_MID
from suiteview.ratemanager.ui_helpers import set_expanding_panel_visible


def open_output_path(path: str) -> None:
    """Open an existing file or folder in the platform shell."""
    if not path or not (os.path.isfile(path) or os.path.isdir(path)):
        return
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class BaseWorkupPanel(QWidget):
    """Common UI behavior shared by UL and Term workup panels."""

    error_title = "Workup Error"

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionLabel")
        return label

    def _dim_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(f"color: {TEXT_MID}; font-size: 12px;")
        return label

    def _small_btn(self, text: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("SecondaryBtn")
        button.clicked.connect(slot)
        return button

    def _toggle_warnings(self):
        shown = self.warn_toggle.isChecked()
        self.warn_area.setVisible(shown)
        self.warn_toggle.setText(
            ("▾" if shown else "▸") + self.warn_toggle.text()[1:],
        )

    def _toggle_log(self):
        shown = self.log_toggle.isChecked()
        set_expanding_panel_visible(self, self.log, shown)
        self.log_toggle.setText(("▾" if shown else "▸") + "  Processing output")

    def _show_warnings(self, warnings: list):
        if warnings:
            self.warn_toggle.setText(f"▸  Warnings ({len(warnings)})")
            self.warn_toggle.setVisible(True)
            self.warn_area.setPlainText("\n".join(f"⚠ {item}" for item in warnings))
        else:
            self.warn_toggle.setVisible(False)
            self.warn_area.setVisible(False)
            self.warn_toggle.setChecked(False)

    def _on_progress(self, pct: float, msg: str):
        self.progress_bar.setValue(int(pct * 1000))
        if msg:
            self.log.append(msg)

    def _on_error(self, err: str):
        self.btn_analyze.setEnabled(True)
        self.btn_build.setEnabled(self._analysis is not None)
        if hasattr(self, "space_lbl"):
            self.space_lbl.setText("")
        self.log.append(f"\n✗  Error: {err}")
        QMessageBox.critical(self, self.error_title, err.split("\n")[0])

    def _open_output(self):
        open_output_path(self._output_path)
