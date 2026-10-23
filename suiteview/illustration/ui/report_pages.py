"""Fixed-width illustration report pages: landscape PDF output and on-screen sheets.

RERUN's illustration reports (UL in ``report_tab.py``, par whole life in
``parwl_report.py``) are pages of fixed-width text lines. This module prints them
to a Letter landscape PDF in Courier New and renders the white print-preview
sheets, so every report shares one printer path.
"""
from __future__ import annotations

import math
import re
from datetime import datetime
from html import escape
from pathlib import Path
from typing import List, Optional, Sequence

from PyQt6.QtCore import QMarginsF, QObject, QSizeF, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPageLayout, QPageSize, QTextDocument
from PyQt6.QtPrintSupport import QPrinter
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from suiteview.core.json_store import read_json, write_json
from suiteview.core.profile_paths import profile_path

from .styles import PURPLE_DARK, PURPLE_LIGHT

OUTPUT_FOLDER_KEY = "report_output_folder"
PDF_FONT_PT = 9.0
# Left/right PDF page margin, inches (halved from 0.6in on 2026-10-08 so wide
# exhibits such as the Expense Report use more of the page).
PDF_SIDE_MARGIN_IN = 0.3
# Letter landscape (11in) less the side margins, in points; Courier New's
# advance is 0.6 em, so a line of N characters needs N x 0.6 x size points.
PRINTABLE_WIDTH_PT = (11.0 - 2 * PDF_SIDE_MARGIN_IN) * 72.0
COURIER_ADVANCE_EM = 0.6

# Report tab chrome shared by the UL and par WL report pages.
REPORT_LABEL_STYLE = f"color: {PURPLE_DARK}; background: transparent; font-size: 11px; font-weight: bold;"
REPORT_BUTTON_STYLE = (
    f"QPushButton {{ background-color: #F3ECFC; color: {PURPLE_DARK};"
    " border: 1px solid #7E57C2; border-radius: 4px; padding: 1px 10px;"
    " min-height: 18px; font-size: 10px; font-weight: bold; }")
PRINT_BUTTON_STYLE = REPORT_BUTTON_STYLE + "QPushButton:disabled { color: #9E9E9E; border-color: #C5B3E0; }"
OUTPUT_FOLDER_EDIT_STYLE = (
    "QLineEdit { background: white; color: #1A1A2E; border: 1px solid #7E57C2;"
    " border-radius: 4px; padding: 1px 6px; min-height: 18px; font-size: 10px; }")


def report_settings_file():
    """Persisted illustration report settings (output folder, page toggles)."""
    return profile_path("illustration_settings.json")


def load_output_folder() -> str:
    folder = (read_json(report_settings_file(), default={}) or {}).get(OUTPUT_FOLDER_KEY, "")
    return folder if isinstance(folder, str) else ""


def save_output_folder(folder: str) -> None:
    """Remember the PDF output folder; raises ``OSError`` when the settings can't be written."""
    settings = read_json(report_settings_file(), default={}) or {}
    settings[OUTPUT_FOLDER_KEY] = folder
    write_json(report_settings_file(), settings)


class OutputFolderSetting(QObject):
    """The one profile-persisted PDF output folder every report page shares.

    Only an Output folder row changes it (typing a folder or Browse…); printing
    to another folder in the Save dialog is a one-off and never rewrites it.
    ``changed`` keeps every open row (UL, par WL, term, ISWL RPU, other RERUN
    windows) showing the same folder, so a stale row can't save an old value.
    """

    changed = pyqtSignal(str)

    @staticmethod
    def folder() -> str:
        return load_output_folder()

    def set_folder(self, folder: str) -> None:
        """Persist ``folder``; raises ``OSError`` when the settings can't be written."""
        folder = (folder or "").strip()
        if folder == load_output_folder():
            return
        save_output_folder(folder)
        self.changed.emit(folder)


_output_folder_setting: Optional[OutputFolderSetting] = None


def output_folder_setting() -> OutputFolderSetting:
    """The process-wide output folder setting (shared change signal)."""
    global _output_folder_setting
    if _output_folder_setting is None:
        _output_folder_setting = OutputFolderSetting()
    return _output_folder_setting


class OutputFolderRow(QWidget):
    """"Output folder: [path] [Browse…]" — the only place the PDF output folder changes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel("Output folder:")
        label.setStyleSheet(REPORT_LABEL_STYLE)
        layout.addWidget(label)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Prompt for a folder each time (not set)")
        self.edit.setToolTip(
            "Folder where illustration PDFs are saved. Saved with your profile across sessions;\n"
            "it changes only here (saving a PDF somewhere else does not change it).")
        self.edit.setStyleSheet(OUTPUT_FOLDER_EDIT_STYLE)
        self.edit.setText(load_output_folder())
        self.edit.editingFinished.connect(self._on_edited)
        layout.addWidget(self.edit, 1)
        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.setToolTip("Choose the folder illustration PDFs are saved to.")
        self.browse_btn.setStyleSheet(REPORT_BUTTON_STYLE)
        self.browse_btn.clicked.connect(self._on_browse)
        layout.addWidget(self.browse_btn)
        output_folder_setting().changed.connect(self._show_folder)

    @staticmethod
    def folder() -> str:
        """The saved output folder ("" when not set)."""
        return load_output_folder()

    def pdf_start_path(self, file_name: str) -> str:
        """Where the Save dialog opens: the saved folder when it exists, else just the name."""
        folder = self.folder()
        return str(Path(folder) / file_name) if folder and Path(folder).is_dir() else file_name

    def _show_folder(self, folder: str) -> None:
        if self.edit.text() != folder:
            self.edit.setText(folder)

    def _set_folder(self, folder: str) -> None:
        try:
            output_folder_setting().set_folder(folder)
        except OSError as exc:
            QMessageBox.warning(self, "Output folder", f"Could not save the output folder setting: {exc}")
        self._show_folder(load_output_folder())

    def _on_edited(self) -> None:
        # editingFinished also fires on focus-out with nothing typed: only a real
        # change is saved.
        if self.edit.text().strip() != load_output_folder():
            self._set_folder(self.edit.text())

    def _on_browse(self) -> None:
        current = self.folder()
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose output folder", current if current and Path(current).is_dir() else "")
        if chosen:
            self._set_folder(chosen)


def default_pdf_name(policy_number: str, plancode: str, now: datetime) -> str:
    """``policy - plancode - yyyy-mm-dd hh-mm.pdf`` with characters Windows forbids removed."""
    parts = [p for p in ((policy_number or "").strip(), (plancode or "").strip(),
                         now.strftime("%Y-%m-%d %H-%M")) if p]
    name = " - ".join(parts) if parts else "Illustration"
    return re.sub(r'[<>:"/\\|?*]', "", name) + ".pdf"


def fitting_font_pt(width_chars: int) -> float:
    """The PDF font size (at most 9pt) that fits ``width_chars`` across a landscape page."""
    if width_chars <= 0:
        return PDF_FONT_PT
    fit = PRINTABLE_WIDTH_PT * 0.98 / (COURIER_ADVANCE_EM * width_chars)   # 2% for the layout margin
    return min(PDF_FONT_PT, math.floor(fit * 10.0) / 10.0)


def pdf_printer(path: str) -> QPrinter:
    """A high-resolution Letter landscape PDF printer writing ``path``."""
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(path)
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.Letter))
    printer.setPageOrientation(QPageLayout.Orientation.Landscape)
    printer.setPageMargins(
        QMarginsF(PDF_SIDE_MARGIN_IN, 0.5, PDF_SIDE_MARGIN_IN, 0.5), QPageLayout.Unit.Inch)
    return printer


def pages_document(pages: Sequence[Sequence[str]], printer: QPrinter,
                   font_pt: float = PDF_FONT_PT) -> QTextDocument:
    """Lay fixed-width pages out as a paginated QTextDocument, one report page per PDF page."""
    parts: List[str] = []
    for index, lines in enumerate(pages):
        style = f"font-family:'Courier New',monospace; font-size:{font_pt:g}pt; white-space:pre; margin:0;"
        if index < len(pages) - 1:
            style += " page-break-after:always;"
        # Join with <br/> instead of newlines: Qt splits a <pre> into a new text block
        # at every literal newline, and each block inherits page-break-after:always -
        # one line per PDF page. <br/> keeps the whole page in a single block.
        body = "<br/>".join(escape(line) for line in lines)
        parts.append(f'<pre style="{style}">{body}</pre>')
    document = QTextDocument()
    # Lay out at the printer's DPI: otherwise the fonts are sized for the 96dpi screen
    # while the page rect below is in 1200dpi device pixels (text at ~1/12 scale).
    document.documentLayout().setPaintDevice(printer)
    font = QFont("Courier New")
    font.setPointSizeF(font_pt)
    document.setDefaultFont(font)
    document.setHtml("".join(parts))
    # Pre-paginate to the printer's page rect: an unpaginated document makes
    # QTextDocument.print() re-lay it out with hardcoded 2cm margins.
    document.setPageSize(QSizeF(printer.pageRect(QPrinter.Unit.DevicePixel).size()))
    return document


def write_pages_pdf(pages: Sequence[Sequence[str]], path: str, font_pt: float = PDF_FONT_PT) -> None:
    """Print fixed-width pages to a Letter landscape PDF file."""
    printer = pdf_printer(path)
    pages_document(pages, printer, font_pt).print(printer)


def report_sheet(lines: Sequence[str]) -> QLabel:
    """A white print-preview sheet showing one fixed-width report page."""
    sheet = QLabel("\n".join(lines))
    sheet.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    sheet.setStyleSheet(
        "QLabel {"
        " background-color: white;"
        f" border: 1px solid {PURPLE_LIGHT};"
        " border-radius: 2px;"
        " padding: 28px 17px;"
        " font-family: Consolas, 'Courier New', monospace;"
        " font-size: 11px;"
        " color: #1A1A2E;"
        "}"
    )
    sheet.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return sheet
