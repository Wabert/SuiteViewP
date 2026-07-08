"""
Rate Manager Window — PyQt6 UI for IAF Rate File Conversion

Uses the SuiteView FramelessWindowBase with standard blue/gold theme.
Provides file browser, output directory picker, progress bar, log, and
Convert / Open buttons.
"""

import os
import subprocess
import sys

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QLineEdit, QTextEdit, QProgressBar,
    QMessageBox, QRadioButton, QTabWidget,
    QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
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
            coi_hi = self.starting_index + max(res.coi_index_count - 1, 0)
            trg_hi = self.starting_index + max(res.trg_index_count - 1, 0)
            self.progress.emit(0.97, f"  Index(COI):     {self.starting_index}–{coi_hi}  ({res.coi_index_count} tables)")
            self.progress.emit(0.97, f"  Index(TRGPREM): {self.starting_index}–{trg_hi}  ({res.trg_index_count} tables)")
            self.progress.emit(0.97, f"  Current COI:    {res.current_coi_rows:,} rows")
            # Display current COI scales and their dates
            if res.current_scales:
                self.progress.emit(0.97, f"  Current COI Scales:")
                for scale_num, date_str in res.current_scales:
                    label = " (most recent)" if scale_num == 1 else ""
                    self.progress.emit(0.97, f"    Scale {scale_num}: {date_str}{label}")
            self.progress.emit(0.98, f"  Guaranteed COI: {res.guaranteed_coi_rows:,} rows  (Scale 0)")
            self.progress.emit(0.98, f"  Target rows:    {res.target_rows:,} rows")
            self.progress.emit(1.0, f"\n✓  Saved to → {db_dir}")
            self.finished.emit(db_dir)

        except Exception as exc:
            self.error.emit(str(exc))


class CKULTB04Worker(QThread):
    """Parse a CKULTB04 report and export it to Excel in a background thread."""
    progress = pyqtSignal(float, str)      # (0-1, message)
    finished = pyqtSignal(str)             # output_path on success
    error = pyqtSignal(str)                # error message

    def __init__(self, input_path: str, output_path: str, table_kind: str,
                 plan_codes: list | None = None):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.table_kind = table_kind       # "raw" or "table"
        self.plan_codes = plan_codes       # None/empty = all plan codes

    def run(self):
        try:
            from suiteview.ratemanager.ckultb04_exporter import (
                export_raw, export_table,
            )

            label = "Excel Raw" if self.table_kind == "raw" else "Excel Table"
            self.progress.emit(0.0, f"Parsing CKULTB04 report → {label}…")

            def _cb(frac: float) -> None:
                self.progress.emit(frac, f"Processing… {frac:.0%}")

            exporter = export_raw if self.table_kind == "raw" else export_table
            rows = exporter(self.input_path, self.output_path,
                            progress_cb=_cb, plan_codes=self.plan_codes)

            self.progress.emit(1.0, f"Wrote {rows:,} rows → {self.output_path}")
            self.finished.emit(self.output_path)

        except Exception as exc:
            self.error.emit(str(exc))


class CKULTB04ListWorker(QThread):
    """Scan a CKULTB04 report and list the distinct plan codes it contains."""
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(list)            # list of (plan_code, record_count)
    error = pyqtSignal(str)

    def __init__(self, input_path: str):
        super().__init__()
        self.input_path = input_path

    def run(self):
        try:
            from suiteview.ratemanager.ckultb04_parser import list_plan_codes

            self.progress.emit(0.0, "Scanning CKULTB04 for plan codes…")
            summary = list_plan_codes(
                self.input_path,
                progress_cb=lambda p: self.progress.emit(p, f"Scanning… {p:.0%}"),
            )
            self.progress.emit(1.0, f"Found {len(summary)} plan code(s).")
            self.finished.emit(summary)
        except Exception as exc:
            self.error.emit(str(exc))


class CKULTB04DBWorker(QThread):
    """Build the CKULTB04 DB Format (SCR POINTER + RATE_SCR) in a thread."""
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(str)             # output_path on success
    error = pyqtSignal(str)

    def __init__(self, input_path: str, output_path: str, specs: list):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.specs = specs

    def run(self):
        try:
            from suiteview.ratemanager.ckultb04_db import build_ckultb04_db

            self.progress.emit(0.0, "Building CKULTB04 DB Format (RATE_SCR)…")

            def _cb(frac: float) -> None:
                self.progress.emit(frac, f"Processing… {frac:.0%}")

            counts = build_ckultb04_db(
                self.input_path, self.specs, self.output_path, progress_cb=_cb)
            totals = counts.get("_totals", {})
            self.progress.emit(
                1.0,
                f"Wrote {totals.get('pointer', 0):,} pointer rows and "
                f"{totals.get('scr', 0):,} RATE_SCR rows → {self.output_path}")
            self.finished.emit(self.output_path)
        except Exception as exc:
            self.error.emit(str(exc))


class BenefitListWorker(QThread):
    """Parse an IAF and list the benefit codes it contains."""
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(list)            # list of (code, coi_count, trg_count)
    error = pyqtSignal(str)

    def __init__(self, input_path: str):
        super().__init__()
        self.input_path = input_path

    def run(self):
        try:
            from suiteview.ratemanager.parser import IAFParser
            from suiteview.ratemanager.benefit_exporter import benefit_summary

            self.progress.emit(0.0, "Scanning IAF for benefits…")
            result = IAFParser().parse(
                self.input_path,
                progress_cb=lambda p: self.progress.emit(p, f"Scanning… {p:.0%}"),
            )
            if result.error:
                self.error.emit(result.error)
                return
            summary = benefit_summary(result)
            self.progress.emit(1.0, f"Found {len(summary)} benefit code(s).")
            self.finished.emit(summary)
        except Exception as exc:
            self.error.emit(str(exc))


class BenefitTableWorker(QThread):
    """Parse an IAF and export the selected benefits to an Excel Table workbook."""
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(str)             # output_path
    error = pyqtSignal(str)

    def __init__(self, input_path: str, output_path: str, codes: list):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.codes = codes

    def run(self):
        try:
            from suiteview.ratemanager.benefit_exporter import export_benefit_table

            self.progress.emit(0.0, f"Building benefit Excel Table ({len(self.codes)} selected)…")
            counts = export_benefit_table(
                self.input_path, self.output_path, self.codes,
                progress_cb=lambda p: self.progress.emit(p, f"Processing… {p:.0%}"),
            )
            for code, (coi, trg) in sorted(counts.items()):
                self.progress.emit(1.0, f"  {code}:  {coi:,} COI rows,  {trg:,} target rows")
            self.progress.emit(1.0, f"Saved → {self.output_path}")
            self.finished.emit(self.output_path)
        except Exception as exc:
            self.error.emit(str(exc))


class BenefitDBWorker(QThread):
    """Parse an IAF and build the combined benefit DB Format workbook."""
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(str)             # output_path
    error = pyqtSignal(str)

    def __init__(self, input_path: str, output_path: str, specs: list):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.specs = specs

    def run(self):
        try:
            from suiteview.ratemanager.benefit_db import export_benefit_db

            self.progress.emit(0.0, f"Building benefit DB Format ({len(self.specs)} selected)…")
            counts = export_benefit_db(
                self.input_path, self.output_path, self.specs,
                progress_cb=lambda p: self.progress.emit(p, f"Processing… {p:.0%}"),
            )
            for code, c in sorted(k for k in counts.items() if k[0] != "_totals"):
                self.progress.emit(
                    1.0,
                    f"  {code}:  {c['bencoi_groups']} COI index(es), "
                    f"{c['bentrg_groups']} target index(es)")
            tot = counts.get("_totals", {})
            self.progress.emit(
                1.0,
                f"Totals: {tot.get('pointer', 0):,} pointer rows, "
                f"{tot.get('bencoi', 0):,} BENCOI rows, {tot.get('bentrg', 0):,} BENTRG rows")
            self.progress.emit(1.0, f"Saved → {self.output_path}")
            self.finished.emit(self.output_path)
        except Exception as exc:
            self.error.emit(str(exc))


class MPFListWorker(QThread):
    """Parse an MPF and list its type-2 (Supplemental) premium codes."""
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(list)            # list of (premcode, benefit, combos, rows)
    error = pyqtSignal(str)

    def __init__(self, input_path: str):
        super().__init__()
        self.input_path = input_path

    def run(self):
        try:
            from suiteview.ratemanager.mpf_exporter import summarize

            self.progress.emit(0.0, "Scanning MPF for supplemental premium codes…")
            summary = summarize(
                self.input_path,
                progress_cb=lambda p: self.progress.emit(p, f"Scanning… {p:.0%}"),
            )
            self.progress.emit(1.0, f"Found {len(summary)} premium code(s).")
            self.finished.emit(summary)
        except Exception as exc:
            self.error.emit(str(exc))


class MPFExportWorker(QThread):
    """Export MPF supplemental data: raw dump, expanded table, or DB workbook."""
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(str)             # output_path
    error = pyqtSignal(str)

    def __init__(self, input_path: str, output_path: str, mode: str, specs: list):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.mode = mode                   # "raw" | "table" | "db"
        self.specs = specs

    def run(self):
        try:
            from suiteview.ratemanager import mpf_exporter as mx

            cb = lambda p: self.progress.emit(p, f"Processing… {p:.0%}")
            if self.mode == "raw":
                codes = [s[0] for s in self.specs]
                self.progress.emit(0.0, f"Building Excel Raw ({len(codes)} premium codes)…")
                rows = mx.export_raw(self.input_path, self.output_path, codes, progress_cb=cb)
                self.progress.emit(1.0, f"Wrote {rows:,} rows.")
            elif self.mode == "table":
                pairs = [(s[0], s[1]) for s in self.specs]
                self.progress.emit(0.0, f"Building Excel Table ({len(pairs)} premium codes)…")
                counts = mx.export_table(self.input_path, self.output_path, pairs, progress_cb=cb)
                for pc, n in sorted(counts.items()):
                    self.progress.emit(1.0, f"  {pc}:  {n:,} rows")
            else:  # db
                self.progress.emit(0.0, f"Building DB Reformat ({len(self.specs)} premium codes)…")
                counts = mx.build_db(self.input_path, self.output_path, self.specs, progress_cb=cb)
                for pc, c in sorted(k for k in counts.items() if k[0] != "_totals"):
                    self.progress.emit(1.0, f"  {pc}:  {c['combos']} combo(s), {c['indexes']} index(es)")
                tot = counts.get("_totals", {})
                self.progress.emit(
                    1.0,
                    f"Totals: {tot.get('pointer', 0):,} pointer rows, {tot.get('coi', 0):,} COI rows")
            self.progress.emit(1.0, f"Saved → {self.output_path}")
            self.finished.emit(self.output_path)
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Shared stylesheet
# ---------------------------------------------------------------------------

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

        #LogToggle {{
            background: transparent;
            color: {TEXT_MID};
            border: none;
            text-align: left;
            padding: 2px 2px;
            font-size: 12px;
            font-weight: bold;
        }}
        #LogToggle:hover {{
            color: {GOLD_TEXT};
        }}
        #LogToggle:checked {{
            color: {GOLD_TEXT};
        }}

        #BenefitTable {{
            background: {BG_INPUT};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 4px;
            font-size: 13px;
            gridline-color: {BORDER};
        }}
        #BenefitTable QHeaderView::section {{
            background: {BG_MID};
            color: {GOLD_TEXT};
            border: none;
            border-right: 1px solid {BORDER};
            border-bottom: 1px solid {BORDER};
            padding: 3px 6px;
            font-size: 12px;
            font-weight: bold;
        }}
        #BenefitTable::item {{
            padding: 2px 4px;
        }}
        #BenefitIndex {{
            background: {BG_DARK};
            color: {TEXT};
            border: 1px solid {GOLD};
            border-radius: 3px;
            padding: 2px 6px;
            font-size: 12px;
            min-width: 78px;
        }}

        QCheckBox#BenefitCheck::indicator {{
            width: 17px;
            height: 17px;
            border: 2px solid {GOLD};
            border-radius: 4px;
            background: {BG_DARK};
        }}
        QCheckBox#BenefitCheck::indicator:hover {{
            border-color: {GOLD_PRIMARY};
            background: {BG_MID};
        }}
        QCheckBox#BenefitCheck::indicator:checked {{
            background: {GOLD_PRIMARY};
            border-color: {GOLD};
            image: none;
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

        QTabWidget::pane {{
            border: 1px solid {BORDER};
            border-radius: 4px;
            top: -1px;
            background: {BG_DARK};
        }}
        QTabBar::tab {{
            background: {BG_MID};
            color: {TEXT_MID};
            border: 1px solid {BORDER};
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            padding: 6px 18px;
            margin-right: 2px;
            font-size: 13px;
            font-weight: bold;
        }}
        QTabBar::tab:selected {{
            background: {BLUE};
            color: {GOLD_TEXT};
            border-color: {GOLD};
        }}
        QTabBar::tab:hover:!selected {{
            background: {BLUE_LIGHT};
            color: {TEXT};
        }}
    """


# ---------------------------------------------------------------------------
# Converter panel — one file-type conversion UI (input/output/log/mode/run)
# ---------------------------------------------------------------------------

class _ConverterPanel(QWidget):
    """Reusable converter UI for a single file type.

    ``kind`` selects the parsing/reformat pipeline:
      * ``"IAF"``      — Cyberlife IAF rate flat files (fully wired).
      * ``"CKULTB04"`` — surrender-charge rates by Code, Rule, State,
        IssueAge, Duration.

    ``modes`` is an ordered list of ``(mode_id, label)`` output options; the
    first is selected by default.
    """

    def __init__(self, kind: str, subtitle: str, input_label: str,
                 file_filter: str, modes: list[tuple[str, str]],
                 select_mode: bool = False, select_kind: str = "", parent=None):
        super().__init__(parent)
        self.kind = kind
        self._file_filter = file_filter
        self.select_mode = select_mode
        self.select_kind = select_kind   # "benefit" or "mpf"
        self._output_path: str = ""
        self._worker: ConversionWorker | None = None
        self._reformat_worker: ReformatDBWorker | None = None
        self._ckultb04_worker: CKULTB04Worker | None = None
        self._ckultb04_db_worker: CKULTB04DBWorker | None = None
        self._benefit_list_worker: BenefitListWorker | None = None
        self._benefit_table_worker: BenefitTableWorker | None = None
        self._benefit_db_worker: BenefitDBWorker | None = None
        self._list_worker: QThread | None = None
        self._export_worker: QThread | None = None
        self._benefit_rows: list = []   # (code, include_chk, renewable_chk, index_edit)
        self._mode_radios: dict[str, QRadioButton] = {}
        self._mode_previews: dict[str, QLabel] = {}

        self.setObjectName("RateManagerBody")
        self._build_ui(subtitle, input_label, modes)

    def _build_ui(self, subtitle: str, input_label: str,
                  modes: list[tuple[str, str]]) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # ── Subtitle ────────────────────────────────────────────────
        subtitle_lbl = QLabel(subtitle)
        subtitle_lbl.setObjectName("Subtitle")
        subtitle_lbl.setWordWrap(True)
        layout.addWidget(subtitle_lbl)

        # ── Input file row ──────────────────────────────────────────
        lbl_in = QLabel(input_label)
        lbl_in.setObjectName("SectionLabel")
        layout.addWidget(lbl_in)

        row_in = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Select an input text file…")
        row_in.addWidget(self.input_edit)
        btn_browse = QPushButton("Browse…")
        btn_browse.setObjectName("SecondaryBtn")
        btn_browse.setFixedWidth(90)
        btn_browse.clicked.connect(self._browse_input)
        row_in.addWidget(btn_browse)
        if self.select_mode:
            if self.select_kind == "mpf":
                list_label = "List Premium Codes"
            elif self.select_kind == "ckultb04":
                list_label = "List Plan Codes"
            else:
                list_label = "List Benefits"
            self.btn_list = QPushButton(list_label)
            self.btn_list.setObjectName("SecondaryBtn")
            self.btn_list.clicked.connect(self._on_list_items)
            row_in.addWidget(self.btn_list)
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

        # ── Selection table (benefit / MPF modes) ───────────────────
        if self.select_mode:
            if self.select_kind == "mpf":
                sect_label = "Premium Codes:"
                headers = ["Premium Code", "Renewable", "Benefit Index",
                           "Benefit", "Combos", "Rows"]
            elif self.select_kind == "ckultb04":
                sect_label = "Plan Codes:"
                headers = ["Plan Code", "Records", "Maturity Age", "Starting Index"]
            else:
                sect_label = "Benefits:"
                headers = ["Benefit", "Renewable", "Benefit Index",
                           "COI rows", "Target rows"]
            self._info_headers = headers[3:]

            sel_header = QHBoxLayout()
            lbl_sel = QLabel(sect_label)
            lbl_sel.setObjectName("SectionLabel")
            sel_header.addWidget(lbl_sel)
            sel_header.addStretch()
            btn_all = QPushButton("Select All")
            btn_all.setObjectName("SecondaryBtn")
            btn_all.clicked.connect(lambda: self._set_all_benefits(True))
            sel_header.addWidget(btn_all)
            btn_none = QPushButton("Clear")
            btn_none.setObjectName("SecondaryBtn")
            btn_none.clicked.connect(lambda: self._set_all_benefits(False))
            sel_header.addWidget(btn_none)
            layout.addLayout(sel_header)

            self.benefit_table = QTableWidget(0, len(headers))
            self.benefit_table.setObjectName("BenefitTable")
            self.benefit_table.setHorizontalHeaderLabels(headers)
            self.benefit_table.verticalHeader().setVisible(False)
            self.benefit_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            self.benefit_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            hh = self.benefit_table.horizontalHeader()
            hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            for c in range(1, len(headers)):
                hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
            self.benefit_table.setMinimumHeight(130)
            layout.addWidget(self.benefit_table, stretch=1)
        else:
            # Non-select tabs: fill the gap so the controls sit lower.
            layout.addStretch(1)

        # ── Output Mode Selection ───────────────────────────────────
        lbl_mode = QLabel("Output Mode:")
        lbl_mode.setObjectName("SectionLabel")
        layout.addWidget(lbl_mode)

        radio_style = (f"QRadioButton {{ color: {TEXT}; font-size: 13px; font-weight: bold; }}"
                       f"QRadioButton::indicator {{ width: 14px; height: 14px; }}")
        for i, (mode_id, label) in enumerate(modes):
            opt_row = QHBoxLayout()
            radio = QRadioButton(label)
            radio.setChecked(i == 0)
            radio.setStyleSheet(radio_style)
            radio.toggled.connect(self._on_mode_changed)
            opt_row.addWidget(radio)
            preview = QLabel("")
            preview.setObjectName("FilePreview")
            opt_row.addWidget(preview, stretch=1)
            layout.addLayout(opt_row)
            self._mode_radios[mode_id] = radio
            self._mode_previews[mode_id] = preview

        # Starting index (only visible for IAF DB reformat mode)
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

        # ── Progress + collapsible processing output (bottom) ──────
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(20)
        layout.addWidget(self.progress_bar)

        self.log_toggle = QPushButton("\u25B8  Processing output")
        self.log_toggle.setObjectName("LogToggle")
        self.log_toggle.setCheckable(True)
        self.log_toggle.clicked.connect(self._toggle_log)
        layout.addWidget(self.log_toggle)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setObjectName("LogArea")
        self.log.setFixedHeight(150)
        self.log.setVisible(False)
        layout.addWidget(self.log)

        # Sync the run-button label / index row to the initial mode.
        self._on_mode_changed()

    def _toggle_log(self):
        shown = self.log_toggle.isChecked()
        self.log.setVisible(shown)
        self.log_toggle.setText(
            ("\u25BE" if shown else "\u25B8") + "  Processing output")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _browse_input(self):
        path, _ = QFileDialog.getOpenFileName(
            self, f"Select {self.kind} File", "", self._file_filter)
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

    def _selected_mode(self) -> str:
        for mode_id, radio in self._mode_radios.items():
            if radio.isChecked():
                return mode_id
        return ""

    def _on_mode_changed(self):
        mode = self._selected_mode()
        # The POINTER index only applies to the IAF DB reformat.
        self.idx_row_widget.setVisible(self.kind == "IAF" and mode == "db")
        if self.select_mode:
            if mode == "db":
                self.btn_run.setText("  Reformat to DB  ")
            elif mode == "raw":
                self.btn_run.setText("  Build Raw  ")
            else:
                self.btn_run.setText("  Build Table  ")
        elif mode == "db":
            self.btn_run.setText("  Reformat to DB  ")
        else:
            self.btn_run.setText("  Convert  ")

    def _on_run_clicked(self):
        mode = self._selected_mode()
        if self.select_mode and self.select_kind == "mpf":
            self._start_mpf_export(mode)
            return
        if self.select_mode and self.select_kind == "ckultb04":
            if mode in ("raw", "table"):
                self._start_ckultb04(mode)
            else:
                self._start_ckultb04_db()
            return
        if self.select_mode:
            if mode == "table":
                self._start_benefit_table()
            else:
                self._start_benefit_db()
            return
        if self.kind == "CKULTB04":
            if mode in ("raw", "table"):
                self._start_ckultb04(mode)
            else:
                self._start_ckultb04_db()
            return
        if mode == "db":
            self._start_reformat()
        else:
            self._start_conversion()

    def _update_file_previews(self):
        input_path = self.input_edit.text().strip()
        if not input_path:
            for preview in self._mode_previews.values():
                preview.setText("")
            return

        basename = os.path.basename(input_path)
        # Extract plancode/stem from filename (first part before '.')
        plancode = basename.split('.')[0] if '.' in basename else basename
        stem = os.path.splitext(basename)[0]

        if self.select_kind == "mpf":
            self._mode_previews["raw"].setText(f"\u2192  {stem} - MPF Raw.xlsx")
            self._mode_previews["table"].setText(f"\u2192  {stem} - MPF Table.xlsx")
            self._mode_previews["db"].setText(
                f"\u2192  {stem} - MPF DB.xlsx  (POINTER, RATE_BENCOI)")
        elif self.select_kind == "ckultb04":
            self._mode_previews["raw"].setText(f"\u2192  {stem} - Raw.xlsx")
            self._mode_previews["table"].setText(f"\u2192  {stem} - Table.xlsx")
            self._mode_previews["db"].setText(
                f"\u2192  {stem} - SCR DB.xlsx  (SCR POINTER, RATE_SCR)")
        elif self.select_mode:
            self._mode_previews["table"].setText(f"\u2192  {plancode} - Benefits.xlsx")
            self._mode_previews["db"].setText(
                f"\u2192  {plancode} - Benefits DB.xlsx  (POINTER, RATE_BENCOI, RATE_BENTRG)")
        elif self.kind == "IAF":
            region = extract_region_from_filename(input_path)
            if region:
                xlsx_name = f"{region} - {plancode} - *.xlsx"
            else:
                xlsx_name = f"{plancode} - *.xlsx"
            self._mode_previews["excel"].setText(f"\u2192  {xlsx_name}")
            self._mode_previews["db"].setText(
                f"\u2192  {plancode}_DB/  (POINTER, COI Current, COI Guaranteed, Target CSVs)")
        else:
            self._mode_previews["raw"].setText(f"\u2192  {stem} - Raw.xlsx")
            self._mode_previews["table"].setText(f"\u2192  {stem} - Table.xlsx")
            self._mode_previews["db"].setText("\u2192  UL_Rates CSV  (coming soon)")

    # -- Selection tabs (IAF Benefits / MPF Supplemental) --

    def _on_list_items(self):
        input_path = self.input_edit.text().strip()
        label = {"mpf": "MPF", "ckultb04": "CKULTB04"}.get(self.select_kind, "IAF")
        if not input_path or not os.path.isfile(input_path):
            QMessageBox.warning(self, "No Input File",
                                f"Please select a valid {label} text file.")
            return
        self.log.clear()
        self.progress_bar.setValue(0)
        self.benefit_table.setRowCount(0)
        self._benefit_rows = []
        self.btn_list.setEnabled(False)
        self.btn_run.setEnabled(False)
        if self.select_kind == "mpf":
            self._list_worker = MPFListWorker(input_path)
        elif self.select_kind == "ckultb04":
            self._list_worker = CKULTB04ListWorker(input_path)
        else:
            self._list_worker = BenefitListWorker(input_path)
        self._list_worker.progress.connect(self._on_progress)
        self._list_worker.finished.connect(self._on_items_listed)
        self._list_worker.error.connect(self._on_benefit_error)
        self._list_worker.start()

    def _make_check_cell(self, checked: bool, tooltip: str = "") -> tuple:
        """A centered, high-visibility checkbox wrapped in a table cell widget."""
        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chk = QCheckBox()
        chk.setObjectName("BenefitCheck")
        chk.setChecked(checked)
        if tooltip:
            chk.setToolTip(tooltip)
        lay.addWidget(chk)
        return container, chk

    def _on_items_listed(self, summary: list):
        self.btn_list.setEnabled(True)
        self.btn_run.setEnabled(True)
        self.benefit_table.setRowCount(0)
        self._benefit_rows = []

        if self.select_kind == "ckultb04":
            if not summary:
                self.log.append("No plan codes found in this file.")
                return
            for row, (code, count) in enumerate(summary):
                self.benefit_table.insertRow(row)
                inc_cell, inc_chk = self._make_check_cell(
                    True, "Include this plan code in the export.")
                self.benefit_table.setCellWidget(
                    row, 0, self._benefit_label_cell(code, inc_cell))
                item = QTableWidgetItem(f"{count:,}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.benefit_table.setItem(row, 1, item)

                mat_edit = QLineEdit("121")
                mat_edit.setObjectName("BenefitIndex")
                mat_edit.setToolTip(
                    "Maturity age — durations are filled with 0 out to this age "
                    "(DB Format only).")
                self.benefit_table.setCellWidget(row, 2, mat_edit)

                idx_edit = QLineEdit(str(14000 + row * 100))
                idx_edit.setObjectName("BenefitIndex")
                idx_edit.setToolTip("Starting Index(SCR) for DB Format.")
                self.benefit_table.setCellWidget(row, 3, idx_edit)

                self._benefit_rows.append((code, inc_chk, mat_edit, idx_edit))
            self.log.append(
                f"Found {len(summary)} plan code(s). Check the ones to print; "
                "set Maturity Age & Starting Index for DB Format, then run.")
            return

        unit = "premium code" if self.select_kind == "mpf" else "benefit"
        if not summary:
            self.log.append(f"No {unit}s found in this file.")
            return

        base_index = 200000 if self.select_kind == "mpf" else 141200
        for row, entry in enumerate(summary):
            code = entry[0]
            info_values = list(entry[1:])
            self.benefit_table.insertRow(row)

            inc_cell, inc_chk = self._make_check_cell(True, "Include this in the export.")
            self.benefit_table.setCellWidget(row, 0, self._benefit_label_cell(code, inc_cell))

            ren_cell, ren_chk = self._make_check_cell(
                False, "Rate varies by attained age (renewable). "
                       "Unchecked = level rate set at issue.")
            self.benefit_table.setCellWidget(row, 1, ren_cell)

            idx_edit = QLineEdit(str(base_index + row * 100))
            idx_edit.setObjectName("BenefitIndex")
            idx_edit.setToolTip("Starting index for DB Reformat.")
            self.benefit_table.setCellWidget(row, 2, idx_edit)

            for j, val in enumerate(info_values):
                text = f"{val:,}" if isinstance(val, int) else str(val)
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.benefit_table.setItem(row, 3 + j, item)

            self._benefit_rows.append((code, inc_chk, ren_chk, idx_edit))

        self.log.append(f"Found {len(summary)} {unit}(s). "
                        "Check the ones to load, set Renewable / Index, then run.")

    def _benefit_label_cell(self, code: str, check_container: QWidget) -> QWidget:
        """Combine the include checkbox and the benefit code into one cell."""
        cell = QWidget()
        lay = QHBoxLayout(cell)
        lay.setContentsMargins(4, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(check_container)
        lbl = QLabel(code)
        lbl.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: bold;")
        lay.addWidget(lbl)
        lay.addStretch()
        return cell

    def _on_benefit_error(self, err: str):
        self.btn_list.setEnabled(True)
        self.btn_run.setEnabled(True)
        self._on_error(err)

    def _set_all_benefits(self, checked: bool):
        for _code, inc_chk, _ren, _idx in self._benefit_rows:
            inc_chk.setChecked(checked)

    def _selected_benefit_codes(self) -> list:
        return [code for code, inc_chk, _ren, _idx in self._benefit_rows
                if inc_chk.isChecked()]

    def _start_mpf_export(self, mode: str):
        input_path = self.input_edit.text().strip()
        if not input_path or not os.path.isfile(input_path):
            QMessageBox.warning(self, "No Input File",
                                "Please select a valid MPF text file.")
            return
        specs = []   # (code, renewable, index)
        for code, inc_chk, ren_chk, idx_edit in self._benefit_rows:
            if not inc_chk.isChecked():
                continue
            index = 0
            if mode == "db":
                try:
                    index = int(idx_edit.text().strip())
                except ValueError:
                    QMessageBox.warning(
                        self, "Invalid Index",
                        f"Premium code {code}: the Benefit Index must be a whole number.")
                    return
            specs.append((code, ren_chk.isChecked(), index))
        if not specs:
            QMessageBox.warning(self, "No Premium Codes Selected",
                                "Check the premium codes to export.")
            return

        output_dir = self.output_edit.text().strip()
        if not output_dir:
            output_dir = os.path.dirname(input_path)
        os.makedirs(output_dir, exist_ok=True)

        stem = os.path.splitext(os.path.basename(input_path))[0]
        suffix = {"raw": "MPF Raw", "table": "MPF Table", "db": "MPF DB"}[mode]
        out_path = os.path.join(output_dir, f"{stem} - {suffix}.xlsx")

        self.log.clear()
        self.progress_bar.setValue(0)
        self.btn_run.setEnabled(False)
        self.btn_list.setEnabled(False)
        self.btn_open.setEnabled(False)
        self._output_path = ""

        self._export_worker = MPFExportWorker(input_path, out_path, mode, specs)
        self._export_worker.progress.connect(self._on_progress)
        self._export_worker.finished.connect(self._on_finished)
        self._export_worker.error.connect(self._on_benefit_error)
        self._export_worker.start()

    def _start_benefit_table(self):
        input_path = self.input_edit.text().strip()
        if not input_path or not os.path.isfile(input_path):
            QMessageBox.warning(self, "No Input File",
                                "Please select a valid IAF text file.")
            return
        codes = self._selected_benefit_codes()
        if not codes:
            QMessageBox.warning(self, "No Benefits Selected",
                                "Click 'List Benefits', then check the benefits to export.")
            return

        output_dir = self.output_edit.text().strip()
        if not output_dir:
            output_dir = os.path.dirname(input_path)
        os.makedirs(output_dir, exist_ok=True)

        basename = os.path.basename(input_path)
        plancode = basename.split('.')[0] if '.' in basename else basename
        out_path = os.path.join(output_dir, f"{plancode} - Benefits.xlsx")

        self.log.clear()
        self.progress_bar.setValue(0)
        self.btn_run.setEnabled(False)
        self.btn_list.setEnabled(False)
        self.btn_open.setEnabled(False)
        self._output_path = ""

        self._benefit_table_worker = BenefitTableWorker(input_path, out_path, codes)
        self._benefit_table_worker.progress.connect(self._on_progress)
        self._benefit_table_worker.finished.connect(self._on_finished)
        self._benefit_table_worker.error.connect(self._on_benefit_error)
        self._benefit_table_worker.start()

    def _start_benefit_db(self):
        from suiteview.ratemanager.benefit_db import BenefitDBSpec

        input_path = self.input_edit.text().strip()
        if not input_path or not os.path.isfile(input_path):
            QMessageBox.warning(self, "No Input File",
                                "Please select a valid IAF text file.")
            return

        specs = []
        for code, inc_chk, ren_chk, idx_edit in self._benefit_rows:
            if not inc_chk.isChecked():
                continue
            try:
                start_index = int(idx_edit.text().strip())
            except ValueError:
                QMessageBox.warning(
                    self, "Invalid Index",
                    f"Benefit {code}: the Benefit Index must be a whole number.")
                return
            specs.append(BenefitDBSpec(
                code=code,
                renewable=ren_chk.isChecked(),
                start_index=start_index,
            ))
        if not specs:
            QMessageBox.warning(self, "No Benefits Selected",
                                "Check the benefits to reformat, and set each Benefit Index.")
            return

        output_dir = self.output_edit.text().strip()
        if not output_dir:
            output_dir = os.path.dirname(input_path)
        os.makedirs(output_dir, exist_ok=True)

        basename = os.path.basename(input_path)
        plancode = basename.split('.')[0] if '.' in basename else basename
        out_path = os.path.join(output_dir, f"{plancode} - Benefits DB.xlsx")

        self.log.clear()
        self.progress_bar.setValue(0)
        self.btn_run.setEnabled(False)
        self.btn_list.setEnabled(False)
        self.btn_open.setEnabled(False)
        self._output_path = ""

        self._benefit_db_worker = BenefitDBWorker(input_path, out_path, specs)
        self._benefit_db_worker.progress.connect(self._on_progress)
        self._benefit_db_worker.finished.connect(self._on_finished)
        self._benefit_db_worker.error.connect(self._on_benefit_error)
        self._benefit_db_worker.start()


    # -- IAF: Excel conversion --

    def _start_conversion(self):
        input_path = self.input_edit.text().strip()
        if not input_path or not os.path.isfile(input_path):
            QMessageBox.warning(self, "No Input File",
                                "Please select a valid input text file.")
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
        if self.select_mode:
            self.btn_list.setEnabled(True)
        self.log.append(f"\n\u2713  Conversion complete!")
        self.log.append(f"   {output_path}")

    def _on_error(self, err: str):
        self.btn_run.setEnabled(True)
        self.log.append(f"\n✗  Error: {err}")
        QMessageBox.critical(self, "Conversion Error", err)

    # -- IAF: DB Reformat --

    def _start_reformat(self):
        input_path = self.input_edit.text().strip()
        if not input_path or not os.path.isfile(input_path):
            QMessageBox.warning(self, "No Input File",
                                "Please select a valid input text file.")
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

    # -- CKULTB04 (surrender charge rates) --

    def _start_ckultb04(self, table_kind: str):
        input_path = self.input_edit.text().strip()
        if not input_path or not os.path.isfile(input_path):
            QMessageBox.warning(self, "No Input File",
                                "Please select a valid CKULTB04 text file.")
            return

        # If plan codes have been listed, export only the checked ones. When no
        # list has been built yet, fall back to exporting every plan code.
        plan_codes = None
        if self._benefit_rows:
            plan_codes = self._selected_benefit_codes()
            if not plan_codes:
                QMessageBox.warning(
                    self, "No Plan Codes Selected",
                    "Check the plan codes to print, or click 'List Plan Codes' "
                    "again to reset.")
                return

        output_dir = self.output_edit.text().strip()
        if not output_dir:
            output_dir = os.path.dirname(input_path)
        os.makedirs(output_dir, exist_ok=True)

        from suiteview.ratemanager.ckultb04_exporter import default_output_name
        suffix = "Raw" if table_kind == "raw" else "Table"
        out_path = os.path.join(output_dir, default_output_name(input_path, suffix))

        self.log.clear()
        self.progress_bar.setValue(0)
        self.btn_run.setEnabled(False)
        if self.select_mode:
            self.btn_list.setEnabled(False)
        self.btn_open.setEnabled(False)
        self._output_path = ""

        self._ckultb04_worker = CKULTB04Worker(
            input_path, out_path, table_kind, plan_codes)
        self._ckultb04_worker.progress.connect(self._on_progress)
        self._ckultb04_worker.finished.connect(self._on_finished)
        self._ckultb04_worker.error.connect(self._on_benefit_error)
        self._ckultb04_worker.start()

    def _start_ckultb04_db(self):
        from suiteview.ratemanager.ckultb04_db import CKULTB04DBSpec

        input_path = self.input_edit.text().strip()
        if not input_path or not os.path.isfile(input_path):
            QMessageBox.warning(self, "No Input File",
                                "Please select a valid CKULTB04 text file.")
            return
        if not self._benefit_rows:
            QMessageBox.warning(
                self, "No Plan Codes Listed",
                "Click 'List Plan Codes', check the plan codes to export, and "
                "set each Maturity Age and Starting Index.")
            return

        specs = []
        for code, inc_chk, mat_edit, idx_edit in self._benefit_rows:
            if not inc_chk.isChecked():
                continue
            try:
                maturity = int(mat_edit.text().strip())
            except ValueError:
                QMessageBox.warning(
                    self, "Invalid Maturity Age",
                    f"Plan code {code}: Maturity Age must be a whole number.")
                return
            try:
                start_index = int(idx_edit.text().strip())
            except ValueError:
                QMessageBox.warning(
                    self, "Invalid Index",
                    f"Plan code {code}: Starting Index must be a whole number.")
                return
            specs.append(CKULTB04DBSpec(
                plan_code=code, maturity_age=maturity, start_index=start_index))
        if not specs:
            QMessageBox.warning(self, "No Plan Codes Selected",
                                "Check the plan codes to export.")
            return

        output_dir = self.output_edit.text().strip()
        if not output_dir:
            output_dir = os.path.dirname(input_path)
        os.makedirs(output_dir, exist_ok=True)

        from suiteview.ratemanager.ckultb04_exporter import default_output_name
        out_path = os.path.join(output_dir, default_output_name(input_path, "SCR DB"))

        self.log.clear()
        self.progress_bar.setValue(0)
        self.btn_run.setEnabled(False)
        self.btn_list.setEnabled(False)
        self.btn_open.setEnabled(False)
        self._output_path = ""

        self._ckultb04_db_worker = CKULTB04DBWorker(input_path, out_path, specs)
        self._ckultb04_db_worker.progress.connect(self._on_progress)
        self._ckultb04_db_worker.finished.connect(self._on_finished)
        self._ckultb04_db_worker.error.connect(self._on_benefit_error)
        self._ckultb04_db_worker.start()

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


# ---------------------------------------------------------------------------
# Main window (FramelessWindowBase subclass)
# ---------------------------------------------------------------------------

class RateManagerWindow(FramelessWindowBase):
    """SuiteView Rate File Converter — frameless blue/gold themed window."""

    def __init__(self, parent=None):
        super().__init__(
            title="SuiteView:  Rate File Converter",
            default_size=(760, 680),
            min_size=(580, 480),
            parent=parent,
            header_colors=HEADER_COLORS,
            border_color=BORDER_COLOR,
        )

    def build_content(self) -> QWidget:
        body = QWidget()
        body.setObjectName("RateManagerBody")
        body.setStyleSheet(_body_stylesheet())

        layout = QVBoxLayout(body)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(0)

        tabs = QTabWidget()
        tabs.setObjectName("ConverterTabs")

        self.iaf_panel = _ConverterPanel(
            kind="IAF",
            subtitle="Convert Cyberlife IAF rate flat files to Excel workbooks using the Danny method.",
            input_label="Input IAF File:",
            file_filter="Text Files (*.txt);;All Files (*)",
            modes=[
                ("excel", "Excel Workbook"),
                ("db", "DB Reformat  (UL_Rates CSV)"),
            ],
        )
        tabs.addTab(self.iaf_panel, "IAF")

        self.iaf_benefits_panel = _ConverterPanel(
            kind="IAF-BEN",
            subtitle="Extract benefit rider rates from an IAF. List the benefits, pick the ones to print, then export.",
            input_label="Input IAF File:",
            file_filter="Text Files (*.txt);;All Files (*)",
            modes=[
                ("table", "Excel Table  (COI + Targets per benefit)"),
                ("db", "DB Format  (BENEFIT POINTER, RATE_BENCOI, RATE_BENTRG)"),
            ],
            select_mode=True,
            select_kind="benefit",
        )
        tabs.addTab(self.iaf_benefits_panel, "IAF - Benefits")

        self.mpf_panel = _ConverterPanel(
            kind="MPF",
            subtitle="Parse the Misc Premium File. List the type-2 supplemental premium codes, pick the ones to load, then export.",
            input_label="Input MPF File:",
            file_filter="Text Files (*.txt);;All Files (*)",
            modes=[
                ("raw", "Excel Raw  (all rows for selected codes)"),
                ("table", "Excel Table  (rates built per renewal indicator)"),
                ("db", "DB Reformat  (POINTER, RATE_BENCOI)"),
            ],
            select_mode=True,
            select_kind="mpf",
        )
        tabs.addTab(self.mpf_panel, "MPF - Supplemental")

        self.ckultb04_panel = _ConverterPanel(
            kind="CKULTB04",
            subtitle="Convert CKULTB04 surrender-charge tables (rates by Code, Rule, State, IssueAge, Duration). List the plan codes, pick the ones to print, then export.",
            input_label="Input CKULTB04 File:",
            file_filter="Text Files (*.txt);;All Files (*)",
            modes=[
                ("raw", "Excel Raw  (all columns)"),
                ("table", "Excel Table  (Plan Code, State, Sex, Rate Class, Band, Issue Age, Duration, Rate)"),
                ("db", "DB Format  (SCR POINTER, RATE_SCR)"),
            ],
            select_mode=True,
            select_kind="ckultb04",
        )
        tabs.addTab(self.ckultb04_panel, "CKULTB04")

        layout.addWidget(tabs)
        return body
