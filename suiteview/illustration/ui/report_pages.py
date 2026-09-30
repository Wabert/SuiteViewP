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
from typing import List, Sequence

from PyQt6.QtCore import QMarginsF, QSizeF, Qt
from PyQt6.QtGui import QFont, QPageLayout, QPageSize, QTextDocument
from PyQt6.QtPrintSupport import QPrinter
from PyQt6.QtWidgets import QLabel, QSizePolicy

from suiteview.core.json_store import read_json, write_json
from suiteview.core.profile_paths import profile_path

from .styles import PURPLE_DARK, PURPLE_LIGHT

OUTPUT_FOLDER_KEY = "report_output_folder"
PDF_FONT_PT = 9.0
# Letter landscape (11in) less the 0.6in side margins, in points; Courier New's
# advance is 0.6 em, so a line of N characters needs N x 0.6 x size points.
PRINTABLE_WIDTH_PT = (11.0 - 1.2) * 72.0
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
    printer.setPageMargins(QMarginsF(0.6, 0.5, 0.6, 0.5), QPageLayout.Unit.Inch)
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
        " padding: 28px 34px;"
        " font-family: Consolas, 'Courier New', monospace;"
        " font-size: 11px;"
        " color: #1A1A2E;"
        "}"
    )
    sheet.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return sheet
