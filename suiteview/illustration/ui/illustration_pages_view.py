"""Shared RERUN pages for the fixed-premium workspaces (par whole life, indeterminate premium term).

* ``IllustrationPagesView`` - the Report page: print-preview sheets of a product's
  fixed-width illustration pages, **Print to PDF** (Letter landscape, the shared output
  folder) and **Ledger to Excel**. The product supplies a page builder and a ledger frame.
* ``InforceChecksView`` - the In-force Check page: CyberLife's values on the record
  against SuiteView's calculation, coloured match / differs / info.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable, List, Optional, Sequence

import pandas as pd
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor, QDesktopServices
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from suiteview.core.excel_export import ExcelExportError, dump_to_new_workbook
from suiteview.illustration.core.inforce_check import CheckLine
from suiteview.ui.widgets.filter_table_view import FilterTableView

from .report_pages import (
    OUTPUT_FOLDER_EDIT_STYLE,
    PRINT_BUTTON_STYLE,
    REPORT_BUTTON_STYLE,
    REPORT_LABEL_STYLE,
    default_pdf_name,
    fitting_font_pt,
    load_output_folder,
    report_sheet,
    save_output_folder,
    write_pages_pdf,
)
from .styles import PURPLE_BG, PURPLE_DARK

logger = logging.getLogger(__name__)

STATUS_COLORS = {"match": QColor("#DFF3E3"), "differs": QColor("#F9D6D5"), "info": QColor("#FFF6D6")}


@dataclass(frozen=True)
class ReportPages:
    """A product's formatted illustration: its pages and what the PDF needs to know."""

    pages: List[List[str]]
    width: int
    policy_number: str
    plancode: str
    status: str


class IllustrationPagesView(QWidget):
    """Report page: print-preview sheets, Print to PDF (landscape) and Ledger to Excel."""

    def __init__(self, build_pages: Callable[[object, date], ReportPages],
                 ledger_frame: Callable[[object], pd.DataFrame], sheet_name: str, parent=None):
        super().__init__(parent)
        self._build_pages = build_pages
        self._ledger_frame = ledger_frame
        self._sheet_name = sheet_name
        self._result = None
        self._report: Optional[ReportPages] = None
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(6)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(REPORT_LABEL_STYLE)
        top.addWidget(self.status_label, 1)
        self.excel_btn = QPushButton("Ledger to Excel")
        self.excel_btn.setStyleSheet(PRINT_BUTTON_STYLE)
        self.excel_btn.setToolTip("Open the annual ledger (every column) in a new unsaved Excel workbook")
        self.excel_btn.clicked.connect(self._to_excel)
        top.addWidget(self.excel_btn)
        self.print_pdf_btn = QPushButton("Print to PDF")
        self.print_pdf_btn.setStyleSheet(PRINT_BUTTON_STYLE)
        self.print_pdf_btn.setToolTip("Save the illustration as a landscape PDF file.")
        self.print_pdf_btn.clicked.connect(self._on_print_pdf)
        top.addWidget(self.print_pdf_btn)
        layout.addLayout(top)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)
        folder_label = QLabel("Output folder:")
        folder_label.setStyleSheet(REPORT_LABEL_STYLE)
        folder_row.addWidget(folder_label)
        self.output_folder_edit = QLineEdit()
        self.output_folder_edit.setPlaceholderText("Prompt for a folder each time (not set)")
        self.output_folder_edit.setToolTip("Folder where illustration PDFs are saved. Saved across sessions.")
        self.output_folder_edit.setStyleSheet(OUTPUT_FOLDER_EDIT_STYLE)
        self.output_folder_edit.setText(load_output_folder())
        self.output_folder_edit.editingFinished.connect(
            lambda: self._set_output_folder(self.output_folder_edit.text().strip()))
        folder_row.addWidget(self.output_folder_edit, 1)
        browse = QPushButton("Browse…")
        browse.setToolTip("Choose the folder illustration PDFs are saved to.")
        browse.setStyleSheet(REPORT_BUTTON_STYLE)
        browse.clicked.connect(self._on_browse_output_folder)
        folder_row.addWidget(browse)
        layout.addLayout(folder_row)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; }")
        layout.addWidget(self.scroll, 1)
        host = QWidget()
        host.setStyleSheet("background: transparent;")
        self._sheet_layout = QVBoxLayout(host)
        self._sheet_layout.setContentsMargins(0, 0, 0, 12)
        self._sheet_layout.setSpacing(14)
        self._sheet_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(host)
        self.clear()

    @property
    def pages(self) -> List[List[str]]:
        return self._report.pages if self._report is not None else []

    def clear(self, message: str = "Run Values to build the illustration.") -> None:
        self._result = None
        self._report = None
        self.status_label.setText(message)
        self.print_pdf_btn.setEnabled(False)
        self.excel_btn.setEnabled(False)
        while self._sheet_layout.count():
            widget = self._sheet_layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()

    def set_result(self, result, run_date: Optional[date] = None) -> None:
        self.clear("")
        self._result = result
        self._report = self._build_pages(result, run_date or date.today())
        for lines in self._report.pages:
            self._sheet_layout.addWidget(report_sheet(lines))
        self.print_pdf_btn.setEnabled(True)
        self.excel_btn.setEnabled(True)
        self.status_label.setText(self._report.status)

    def write_pdf(self, path: str) -> None:
        """Print the displayed pages to a landscape PDF, the font sized to the page width."""
        if self._report is None:
            raise ValueError("Run Values before printing the illustration.")
        write_pages_pdf(self._report.pages, path, fitting_font_pt(self._report.width))

    def _set_output_folder(self, folder: str) -> None:
        if self.output_folder_edit.text() != folder:
            self.output_folder_edit.setText(folder)
        try:
            save_output_folder(folder)
        except OSError as exc:
            QMessageBox.warning(self, "Output folder", f"Could not save the output folder setting: {exc}")

    def _on_browse_output_folder(self) -> None:
        current = self.output_folder_edit.text().strip()
        folder = QFileDialog.getExistingDirectory(self, "Choose output folder",
                                                  current if current and Path(current).is_dir() else "")
        if folder:
            self._set_output_folder(folder)

    def _on_print_pdf(self) -> None:
        if self._report is None:
            return
        name = default_pdf_name(self._report.policy_number, self._report.plancode, datetime.now())
        folder = self.output_folder_edit.text().strip()
        start = str(Path(folder) / name) if folder and Path(folder).is_dir() else name
        path, _ = QFileDialog.getSaveFileName(self, "Print to PDF", start, "PDF Files (*.pdf)")
        if not path:
            return
        chosen = str(Path(path).resolve().parent)
        if chosen != folder:
            self._set_output_folder(chosen)
        try:
            self.write_pdf(path)
        except Exception as exc:  # a failed print must be loud, not a silent no-op
            logger.exception("Illustration PDF failed")
            QMessageBox.critical(self, "Print to PDF", f"Failed to write PDF: {exc}")
            return
        self.status_label.setText(f"Saved {path}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _to_excel(self) -> None:
        if self._result is None:
            return
        frame = self._ledger_frame(self._result)
        try:
            dump_to_new_workbook(list(frame.columns), frame.values.tolist(), sheet_name=self._sheet_name)
        except ExcelExportError as exc:
            QMessageBox.warning(self, "Excel", str(exc))


def checks_frame(checks: Sequence[CheckLine]) -> pd.DataFrame:
    rows = [{"Area": c.area, "Check": c.item, "CyberLife": c.cyberlife, "Calculated": c.calculated,
             "Difference": c.difference, "Status": c.status, "Detail": c.detail} for c in checks]
    return pd.DataFrame(rows, columns=["Area", "Check", "CyberLife", "Calculated", "Difference", "Status", "Detail"])


class InforceChecksView(QWidget):
    """CyberLife's current values against SuiteView's calculation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.summary = QLabel("")
        self.summary.setStyleSheet(f"color: {PURPLE_DARK}; background: transparent; font-weight: bold;")
        layout.addWidget(self.summary)
        self.grid = FilterTableView(self)
        self.grid.apply_ledger_style()
        self.grid.set_full_row_selection(True)
        layout.addWidget(self.grid, 1)

    def load(self, checks: Sequence[CheckLine], error: str = "") -> None:
        frame = checks_frame(checks)
        self.grid.set_dataframe(frame, limit_rows=False)
        self.grid.set_numeric_formatting(default_decimals=None, column_decimals={"Difference": 4})
        highlights = {(row, "Status"): STATUS_COLORS.get(status, QColor("white"))
                      for row, status in enumerate(frame["Status"])}
        self.grid.set_highlighted_cells(highlights)
        self.grid.show_cell_highlights()
        self.grid.autofit_columns_to_data(max_width=520)
        counts = frame["Status"].value_counts().to_dict() if len(frame) else {}
        text = (f"In-force check: {counts.get('match', 0)} match, {counts.get('differs', 0)} differ, "
                f"{counts.get('info', 0)} for information.")
        self.summary.setText(text + (f"  {error}" if error else ""))
