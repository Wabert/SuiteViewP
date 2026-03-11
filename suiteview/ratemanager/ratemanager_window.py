"""
Rate Manager Window — PyQt6 UI for IAF Rate File Conversion

Uses the SuiteView FramelessWindowBase with standard blue/gold theme.
Provides file browser, output directory picker, progress bar, log, and
Convert / Open buttons.
"""

import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QLineEdit, QTextEdit, QProgressBar,
    QMessageBox, QFrame, QSizePolicy, QRadioButton, QGroupBox,
)

from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from suiteview.ratemanager.parser import IAFParser
from suiteview.ratemanager.exporter import (
    IAFExporter, generate_output_filename, extract_region_from_filename,
)
from suiteview.ratemanager.rate_reformatter import RateReformatter


# ---------------------------------------------------------------------------
# Standard SuiteView palette (blue & gold)
# ---------------------------------------------------------------------------

BLUE        = "#1A3A7A"
BLUE_LIGHT  = "#2A5AAA"
BLUE_DARK   = "#0D3A7A"
GOLD        = "#D4A017"
GOLD_TEXT   = "#FFD54F"
GOLD_PRIMARY = "#FFC107"

BG_DARK     = "#1E1E2E"
BG_MID      = "#2D2D44"
BG_INPUT    = "#252540"
TEXT        = "#E8E8F0"
TEXT_MID    = "#A0A0B8"
BORDER      = "#3D3D5C"

# Header colours for FramelessWindowBase
HEADER_COLORS = ("#1E5BA8", "#0D3A7A", "#082B5C")
BORDER_COLOR  = "#D4A017"


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class ConversionWorker(QThread):
    """Run parsing + export in a background thread."""
    progress = pyqtSignal(float, str)      # (0-1, message)
    finished = pyqtSignal(str)             # output_path on success
    error = pyqtSignal(str)                # error message

    def __init__(self, input_path: str, output_dir: str):
        super().__init__()
        self.input_path = input_path
        self.output_dir = output_dir

    def run(self):
        try:
            # Parse
            self.progress.emit(0.0, "Parsing IAF file…")
            parser = IAFParser()
            result = parser.parse(
                self.input_path,
                progress_cb=lambda p: self.progress.emit(p * 0.5, f"Parsing… {p:.0%}"),
            )
            if result.error:
                self.error.emit(result.error)
                return

            self.progress.emit(0.5, f"Parsed {result.line_count:,} lines  —  "
                               f"{len(result.products)} products, "
                               f"{len(result.rates):,} rates")

            # Build output path
            fname = generate_output_filename(result, self.input_path)
            out_path = os.path.join(self.output_dir, fname)

            # Export
            self.progress.emit(0.55, "Building workbook…")
            IAFExporter.export(
                result, out_path,
                progress_cb=lambda p: self.progress.emit(0.5 + p * 0.5,
                                                         f"Exporting… {p:.0%}"),
            )
            self.progress.emit(1.0, f"Saved → {out_path}")
            self.finished.emit(out_path)

        except Exception as exc:
            self.error.emit(str(exc))


class ReformatDBWorker(QThread):
    """Run parsing + DB reformat in a background thread."""
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(str)             # output directory
    error = pyqtSignal(str)

    def __init__(self, input_path: str, output_dir: str, starting_index: int):
        super().__init__()
        self.input_path = input_path
        self.output_dir = output_dir
        self.starting_index = starting_index

    def run(self):
        try:
            # Parse
            self.progress.emit(0.0, "Parsing IAF file…")
            parser = IAFParser()
            result = parser.parse(
                self.input_path,
                progress_cb=lambda p: self.progress.emit(p * 0.3, f"Parsing… {p:.0%}"),
            )
            if result.error:
                self.error.emit(result.error)
                return

            self.progress.emit(0.3, f"Parsed {len(result.rates):,} rates")

            # Create output subdirectory named for the plancode
            plancode = result.products[0].plancode.strip() if result.products else "output"
            db_dir = os.path.join(self.output_dir, f"{plancode}_DB")
            os.makedirs(db_dir, exist_ok=True)

            # Reformat
            self.progress.emit(0.35, f"Reformatting to DB format (index start={self.starting_index})…")

            def _reformat_progress(step, total):
                pct = 0.35 + (step / total) * 0.60
                labels = ["POINTER", "Current COI", "Guaranteed COI", "Target Premiums"]
                label = labels[step - 1] if step <= len(labels) else f"Step {step}"
                self.progress.emit(pct, f"  ✓ {label} complete")

            reformatter = RateReformatter(
                result,
                starting_index=self.starting_index,
                progress_callback=_reformat_progress,
            )
            res = reformatter.reformat(db_dir)

            if res.error:
                self.error.emit(res.error)
                return

            self.progress.emit(0.95, "")
            self.progress.emit(0.95, f"── DB Reformat Summary ──")
            self.progress.emit(0.96, f"  Plancode:       {reformatter.plancode}")
            self.progress.emit(0.96, f"  Combos:         {res.combo_count}")
            self.progress.emit(0.97, f"  Index range:    {self.starting_index}–{self.starting_index + res.combo_count - 1}")
            self.progress.emit(0.97, f"  Current COI:    {res.current_coi_rows:,} rows")
            self.progress.emit(0.98, f"  Guaranteed COI: {res.guaranteed_coi_rows:,} rows")
            self.progress.emit(0.98, f"  Target rows:    {res.target_rows:,} rows")
            self.progress.emit(1.0, f"\n✓  Saved to → {db_dir}")
            self.finished.emit(db_dir)

        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Main window (FramelessWindowBase subclass)
# ---------------------------------------------------------------------------

class RateManagerWindow(FramelessWindowBase):
    """SuiteView Rate File Converter — frameless blue/gold themed window."""

    def __init__(self, parent=None):
        self._output_path: str = ""
        self._worker: ConversionWorker | None = None
        self._reformat_worker: ReformatDBWorker | None = None

        super().__init__(
            title="SuiteView:  Rate File Converter",
            default_size=(740, 560),
            min_size=(580, 420),
            parent=parent,
            header_colors=HEADER_COLORS,
            border_color=BORDER_COLOR,
        )

    # ------------------------------------------------------------------
    # build_content — called by FramelessWindowBase
    # ------------------------------------------------------------------

    def build_content(self) -> QWidget:
        body = QWidget()
        body.setObjectName("RateManagerBody")
        body.setStyleSheet(self._body_stylesheet())

        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # ── Subtitle ────────────────────────────────────────────────
        subtitle = QLabel("Convert Cyberlife IAF rate flat files to Excel workbooks using the Danny method.")
        subtitle.setObjectName("Subtitle")
        layout.addWidget(subtitle)

        # ── Input file row ──────────────────────────────────────────
        lbl_in = QLabel("Input IAF File:")
        lbl_in.setObjectName("SectionLabel")
        layout.addWidget(lbl_in)

        row_in = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Select an IAF text file…")
        row_in.addWidget(self.input_edit)
        btn_browse = QPushButton("Browse…")
        btn_browse.setObjectName("SecondaryBtn")
        btn_browse.setFixedWidth(90)
        btn_browse.clicked.connect(self._browse_input)
        row_in.addWidget(btn_browse)
        layout.addLayout(row_in)

        # ── Output dir row ──────────────────────────────────────────
        lbl_out = QLabel("Output Folder:")
        lbl_out.setObjectName("SectionLabel")
        layout.addWidget(lbl_out)

        row_out = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Same folder as input file")
        row_out.addWidget(self.output_edit)
        btn_out = QPushButton("Browse…")
        btn_out.setObjectName("SecondaryBtn")
        btn_out.setFixedWidth(90)
        btn_out.clicked.connect(self._browse_output)
        row_out.addWidget(btn_out)
        layout.addLayout(row_out)

        # ── Progress bar ────────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(20)
        layout.addWidget(self.progress_bar)

        # ── Log area ────────────────────────────────────────────────
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setObjectName("LogArea")
        layout.addWidget(self.log, stretch=1)

        # ── Output Mode Selection ───────────────────────────────────
        lbl_mode = QLabel("Output Mode:")
        lbl_mode.setObjectName("SectionLabel")
        layout.addWidget(lbl_mode)

        # Option 1: Excel workbook
        opt1_row = QHBoxLayout()
        self.radio_excel = QRadioButton("Excel Workbook")
        self.radio_excel.setChecked(True)
        self.radio_excel.setStyleSheet(f"QRadioButton {{ color: {TEXT}; font-size: 13px; font-weight: bold; }}"
                                       f"QRadioButton::indicator {{ width: 14px; height: 14px; }}")
        self.radio_excel.toggled.connect(self._on_mode_changed)
        opt1_row.addWidget(self.radio_excel)
        self.lbl_excel_file = QLabel("")
        self.lbl_excel_file.setObjectName("FilePreview")
        opt1_row.addWidget(self.lbl_excel_file, stretch=1)
        layout.addLayout(opt1_row)

        # Option 2: DB reformat
        opt2_row = QHBoxLayout()
        self.radio_db = QRadioButton("DB Reformat  (UL_Rates CSV)")
        self.radio_db.setStyleSheet(f"QRadioButton {{ color: {TEXT}; font-size: 13px; font-weight: bold; }}"
                                    f"QRadioButton::indicator {{ width: 14px; height: 14px; }}")
        self.radio_db.toggled.connect(self._on_mode_changed)
        opt2_row.addWidget(self.radio_db)
        self.lbl_db_folder = QLabel("")
        self.lbl_db_folder.setObjectName("FilePreview")
        opt2_row.addWidget(self.lbl_db_folder, stretch=1)
        layout.addLayout(opt2_row)

        # Starting index (only visible for DB mode)
        self.idx_row_widget = QWidget()
        idx_row = QHBoxLayout(self.idx_row_widget)
        idx_row.setContentsMargins(24, 0, 0, 0)
        lbl_idx = QLabel("Starting POINTER Index:")
        lbl_idx.setStyleSheet(f"color: {TEXT_MID}; font-size: 12px;")
        idx_row.addWidget(lbl_idx)
        self.index_edit = QLineEdit("13400")
        self.index_edit.setFixedWidth(80)
        self.index_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        idx_row.addWidget(self.index_edit)
        idx_row.addStretch()
        self.idx_row_widget.setVisible(False)
        layout.addWidget(self.idx_row_widget)

        # ── Action buttons ──────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_open = QPushButton("Open Output")
        self.btn_open.setObjectName("SecondaryBtn")
        self.btn_open.setEnabled(False)
        self.btn_open.clicked.connect(self._open_output)
        btn_row.addWidget(self.btn_open)

        self.btn_run = QPushButton("  Convert  ")
        self.btn_run.setObjectName("PrimaryBtn")
        self.btn_run.clicked.connect(self._on_run_clicked)
        btn_row.addWidget(self.btn_run)

        layout.addLayout(btn_row)

        return body

    # ------------------------------------------------------------------
    # Stylesheet
    # ------------------------------------------------------------------

    @staticmethod
    def _body_stylesheet() -> str:
        return f"""
            #RateManagerBody {{
                background: {BG_DARK};
            }}

            #Subtitle {{
                color: {TEXT_MID};
                font-size: 12px;
                font-style: italic;
            }}

            #SectionLabel {{
                color: {GOLD_TEXT};
                font-weight: bold;
                font-size: 13px;
            }}

            QLineEdit {{
                background: {BG_INPUT};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 13px;
                selection-background-color: {BLUE};
            }}
            QLineEdit:focus {{
                border-color: {GOLD};
            }}

            #SecondaryBtn {{
                background: {BG_MID};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 13px;
            }}
            #SecondaryBtn:hover {{
                background: {BLUE};
                border-color: {GOLD};
            }}
            #SecondaryBtn:disabled {{
                color: #555;
            }}

            #PrimaryBtn {{
                background: {BLUE};
                color: {GOLD_TEXT};
                border: 2px solid {GOLD};
                border-radius: 4px;
                padding: 8px 28px;
                font-size: 14px;
                font-weight: bold;
            }}
            #PrimaryBtn:hover {{
                background: {BLUE_LIGHT};
            }}
            #PrimaryBtn:disabled {{
                background: #333;
                color: #666;
                border-color: #444;
            }}

            #LogArea {{
                background: {BG_INPUT};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                font-family: 'Cascadia Code', 'Consolas', monospace;
                font-size: 12px;
            }}

            QProgressBar {{
                background: {BG_INPUT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                text-align: center;
                color: {TEXT};
                font-size: 12px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {BLUE}, stop:1 {GOLD});
                border-radius: 3px;
            }}

            #FilePreview {{
                color: {TEXT_MID};
                font-size: 11px;
                font-style: italic;
                padding-left: 8px;
            }}
        """

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _browse_input(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select IAF Rate File", "",
            "Text Files (*.txt);;All Files (*)")
        if path:
            self.input_edit.setText(path)
            if not self.output_edit.text():
                self.output_edit.setText(os.path.dirname(path))
            self._update_file_previews()

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_edit.setText(folder)
            self._update_file_previews()

    def _on_mode_changed(self):
        db_mode = self.radio_db.isChecked()
        self.idx_row_widget.setVisible(db_mode)
        if db_mode:
            self.btn_run.setText("  Reformat to DB  ")
        else:
            self.btn_run.setText("  Convert  ")

    def _on_run_clicked(self):
        if self.radio_db.isChecked():
            self._start_reformat()
        else:
            self._start_conversion()

    def _update_file_previews(self):
        input_path = self.input_edit.text().strip()
        output_dir = self.output_edit.text().strip()
        if not input_path:
            self.lbl_excel_file.setText("")
            self.lbl_db_folder.setText("")
            return
        if not output_dir:
            output_dir = os.path.dirname(input_path)

        # Excel filename preview
        basename = os.path.basename(input_path)
        region = extract_region_from_filename(input_path)
        # Extract plancode from filename (first part before '.')
        plancode = basename.split('.')[0] if '.' in basename else basename
        if region:
            xlsx_name = f"{region} - {plancode} - *.xlsx"
        else:
            xlsx_name = f"{plancode} - *.xlsx"
        self.lbl_excel_file.setText(f"\u2192  {xlsx_name}")

        # DB folder preview
        db_folder = f"{plancode}_DB/"
        self.lbl_db_folder.setText(f"\u2192  {db_folder}  (POINTER, COI Current, COI Guaranteed, Target CSVs)")

    def _start_conversion(self):
        input_path = self.input_edit.text().strip()
        if not input_path or not os.path.isfile(input_path):
            QMessageBox.warning(self, "No Input File",
                                "Please select a valid IAF text file.")
            return

        output_dir = self.output_edit.text().strip()
        if not output_dir:
            output_dir = os.path.dirname(input_path)
        os.makedirs(output_dir, exist_ok=True)

        self.log.clear()
        self.progress_bar.setValue(0)
        self.btn_run.setEnabled(False)
        self.btn_open.setEnabled(False)
        self._output_path = ""

        self._worker = ConversionWorker(input_path, output_dir)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, pct: float, msg: str):
        self.progress_bar.setValue(int(pct * 1000))
        if msg:
            self.log.append(msg)

    def _on_finished(self, output_path: str):
        self._output_path = output_path
        self.btn_run.setEnabled(True)
        self.btn_open.setEnabled(True)
        self.log.append(f"\n\u2713  Conversion complete!")
        self.log.append(f"   {output_path}")

    def _on_error(self, err: str):
        self.btn_run.setEnabled(True)
        self.log.append(f"\n✗  Error: {err}")
        QMessageBox.critical(self, "Conversion Error", err)

    # -- DB Reformat actions --

    def _start_reformat(self):
        input_path = self.input_edit.text().strip()
        if not input_path or not os.path.isfile(input_path):
            QMessageBox.warning(self, "No Input File",
                                "Please select a valid IAF text file.")
            return

        # Validate starting index
        idx_text = self.index_edit.text().strip()
        try:
            starting_index = int(idx_text)
        except ValueError:
            QMessageBox.warning(self, "Invalid Index",
                                "Starting index must be a whole number.")
            return

        output_dir = self.output_edit.text().strip()
        if not output_dir:
            output_dir = os.path.dirname(input_path)
        os.makedirs(output_dir, exist_ok=True)

        self.log.clear()
        self.progress_bar.setValue(0)
        self.btn_run.setEnabled(False)
        self.btn_open.setEnabled(False)
        self._output_path = ""

        self._reformat_worker = ReformatDBWorker(input_path, output_dir, starting_index)
        self._reformat_worker.progress.connect(self._on_progress)
        self._reformat_worker.finished.connect(self._on_reformat_finished)
        self._reformat_worker.error.connect(self._on_error)
        self._reformat_worker.start()

    def _on_reformat_finished(self, output_dir: str):
        self._output_path = output_dir
        self.btn_run.setEnabled(True)
        self.btn_open.setEnabled(True)

    def _open_output(self):
        path = self._output_path
        if not path:
            return
        if not (os.path.isfile(path) or os.path.isdir(path)):
            return
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
