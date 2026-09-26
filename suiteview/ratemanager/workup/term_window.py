"""Term Rate Workup panel — one IAF in, a folder of TERM_* CSVs out.

Mirrors :class:`~suiteview.ratemanager.workup.workup_window.RateWorkupPanel`
but for the Term product line: there is no MPF, CKULTB04 or CKULTB01 input,
and instead the user supplies what the IAF cannot say — the premium schedule
shape (FIRSTLEVEL / RENLEVEL), the policy fee, and which modal-factor and
band-structure rows the plancode points at.

Maturity is shown read-only because it is derived from the IAF plan header.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from suiteview.ratemanager.rm_styles import GOLD_TEXT, TEXT, body_stylesheet
from suiteview.ratemanager.workup import term_reference
from suiteview.ratemanager.workup.term_builder import (
    TermWorkupAnalysis, TermWorkupResult, analyze, build,
)
from suiteview.ratemanager.workup.base import BaseWorkupPanel
from suiteview.ratemanager.workup.term_spec import (
    BandSpecRow, BandStructureSelection, ModeFactorSelection,
    TermBenefitSelection, TermWorkupSpec,
)
from suiteview.ratemanager.worker_helpers import start_workup_worker
from suiteview.ui.workers import CallableWorker, WorkerController

_NEW_ENTRY = "__new__"


# ---------------------------------------------------------------------------
# New-reference dialogs
# ---------------------------------------------------------------------------

class _ModeFactorDialog(QDialog):
    """Define a new TERM_RATE_MODEFACT row.

    Six premium factors (PAC/DIR × semi-annual/quarterly/monthly) plus the
    matching policy-fee factors, which usually mirror them.
    """

    def __init__(self, parent, index: str):
        super().__init__(parent)
        self.setWindowTitle("New Modal Factors")
        self.setObjectName("RateManagerBody")
        self.setStyleSheet(body_stylesheet())
        self._index = index

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        intro = QLabel(
            f"These factors are shared by every plancode that points at "
            f"Index(MODEFACT) {index}. Fee factors usually match the premium "
            f"factors — fill the premium row and use Copy to Fees.")
        intro.setObjectName("Subtitle")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(5)
        self._edits: dict = {}
        for column, header in enumerate(("Semi-Annual", "Quarterly", "Monthly"), 1):
            label = QLabel(header)
            label.setStyleSheet(f"color: {GOLD_TEXT}; font-size: 12px; "
                                f"font-weight: bold;")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(label, 0, column)

        rows = (
            ("PAC (premium)", ("PACS", "PACQ", "PACM")),
            ("DIR (premium)", ("DIRS", "DIRQ", "DIRM")),
            ("PAC (fee)", ("PACS_FEE", "PACQ_FEE", "PACM_FEE")),
            ("DIR (fee)", ("DIRS_FEE", "DIRQ_FEE", "DIRM_FEE")),
        )
        for row_number, (label_text, names) in enumerate(rows, 1):
            label = QLabel(label_text)
            label.setStyleSheet(f"color: {TEXT}; font-size: 12px;")
            grid.addWidget(label, row_number, 0)
            for column, name in enumerate(names, 1):
                edit = QLineEdit("0")
                edit.setObjectName("BenefitIndex")
                edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
                grid.addWidget(edit, row_number, column)
                self._edits[name] = edit
        layout.addLayout(grid)

        copy_row = QHBoxLayout()
        copy_row.addStretch()
        copy_btn = QPushButton("Copy Premium → Fees")
        copy_btn.setObjectName("SecondaryBtn")
        copy_btn.clicked.connect(self._copy_to_fees)
        copy_row.addWidget(copy_btn)
        layout.addLayout(copy_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _copy_to_fees(self):
        for premium, fee in (("PACS", "PACS_FEE"), ("PACQ", "PACQ_FEE"),
                             ("PACM", "PACM_FEE"), ("DIRS", "DIRS_FEE"),
                             ("DIRQ", "DIRQ_FEE"), ("DIRM", "DIRM_FEE")):
            self._edits[fee].setText(self._edits[premium].text())

    def _on_accept(self):
        try:
            self._values = {
                name: float(edit.text().strip() or "0")
                for name, edit in self._edits.items()
            }
        except ValueError:
            QMessageBox.warning(self, "Modal Factors",
                                "Every factor must be a number.")
            return
        self.accept()

    def selection(self) -> ModeFactorSelection:
        return ModeFactorSelection(index=self._index, values=self._values)


class _BandStructureDialog(QDialog):
    """Define a new TERM_RATE_BANDSPECS structure.

    One row per face-amount breakpoint; the amount is the *lowest* specified
    amount that falls in the band, so the first band starts at 0.
    """

    _DEFAULT_DATE = "1900-01-01"

    def __init__(self, parent, index: str):
        super().__init__(parent)
        self.setWindowTitle("New Band Structure")
        self.setObjectName("RateManagerBody")
        self.setStyleSheet(body_stylesheet())
        self.resize(520, 340)
        self._index = index
        self._rows: list = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        intro = QLabel(
            f"Index(BANDSPEC) {index}. Each row is the lowest specified "
            f"amount in that band, so the first band starts at 0. Band codes "
            f"must match the band letters in the IAF rate idents.")
        intro.setObjectName("Subtitle")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.table = QTableWidget(0, 4)
        self.table.setObjectName("BenefitTable")
        self.table.setHorizontalHeaderLabels(
            ["Issue Date", "Specified Amount", "Band", "Band Code"])
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        for column, width in ((0, 110), (1, 150), (2, 60), (3, 90)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table, stretch=1)

        button_row = QHBoxLayout()
        for text, slot in (("Add Band", self._add_row),
                           ("Remove Selected", self._remove_row)):
            button = QPushButton(text)
            button.setObjectName("SecondaryBtn")
            button.clicked.connect(slot)
            button_row.addWidget(button)
        button_row.addStretch()
        layout.addLayout(button_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._add_row()

    def _add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        defaults = (self._DEFAULT_DATE, "0", str(row + 1),
                    chr(ord("A") + row) if row < 26 else "")
        for column, value in enumerate(defaults):
            self.table.setItem(row, column, QTableWidgetItem(value))

    def _remove_row(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def _on_accept(self):
        rows = []
        for row in range(self.table.rowCount()):
            def cell(column: int) -> str:
                item = self.table.item(row, column)
                return item.text().strip() if item else ""

            try:
                rows.append(BandSpecRow(
                    issue_date=cell(0) or self._DEFAULT_DATE,
                    specified_amount=float(cell(1).replace(",", "") or "0"),
                    band=int(cell(2)),
                    band_code=cell(3),
                ))
            except ValueError:
                QMessageBox.warning(
                    self, "Band Structure",
                    f"Row {row + 1} has a non-numeric amount or band number.")
                return
        if not rows:
            QMessageBox.warning(self, "Band Structure",
                                "Add at least one band.")
            return
        self._rows = rows
        self.accept()

    def selection(self) -> BandStructureSelection:
        return BandStructureSelection(index=self._index, rows=self._rows)


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

class TermWorkupPanel(BaseWorkupPanel):
    """Per-plancode Term rate workup — one IAF, seven TERM_* CSVs."""

    workup_built = pyqtSignal(str)
    error_title = "Term Workup Error"

    _BENEFIT_COLUMNS = ("Benefit", "Renewable", "Cease Age", "Max Dur", "Detail")

    def __init__(self, parent=None):
        from suiteview.core.access_control import guard_app_access

        guard_app_access("RATEMANAGER")
        super().__init__(parent)
        self._analysis: TermWorkupAnalysis | None = None
        self._analyze_worker: WorkerController | None = None
        self._build_worker: WorkerController | None = None
        self._reference_worker: WorkerController | None = None
        self._reference = term_reference.TermReferenceData()
        self._output_path = ""
        self._ben_rows: list = []
        self._new_modefact: ModeFactorSelection | None = None
        self._new_bandspec: BandStructureSelection | None = None
        self._reference_load_started = False
        self.setObjectName("RateManagerBody")
        self.setStyleSheet(body_stylesheet())
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if not self._reference_load_started:
            self._reference_load_started = True
            self._load_reference_data()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(8)

        subtitle = QLabel(
            "Compile one Term plancode's IAF into pre-compiled premium and "
            "benefit rates. Maturity comes from the IAF; the premium schedule "
            "shape and the modal/band pointers come from you.")
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        # ── Plan identity row ───────────────────────────────────────────
        plan_row = QHBoxLayout()
        plan_row.setSpacing(6)
        plan_row.addWidget(self._section_label("Plancode"))
        self.plancode_lbl = QLineEdit()
        self.plancode_lbl.setReadOnly(True)
        self.plancode_lbl.setPlaceholderText("from IAF")
        self.plancode_lbl.setFixedWidth(96)
        self.plancode_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plan_row.addWidget(self.plancode_lbl)

        plan_row.addSpacing(8)
        plan_row.addWidget(self._dim_label("Issue Ver"))
        self.version_edit = QLineEdit("1")
        self.version_edit.setObjectName("BenefitIndex")
        self.version_edit.setFixedWidth(44)
        self.version_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plan_row.addWidget(self.version_edit)

        plan_row.addSpacing(8)
        plan_row.addWidget(self._dim_label("Base Index"))
        self.base_index_edit = QLineEdit()
        self.base_index_edit.setObjectName("BenefitIndex")
        self.base_index_edit.setFixedWidth(72)
        self.base_index_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.base_index_edit.setPlaceholderText("required")
        self.base_index_edit.setToolTip(
            "A free multiple of 1000. Rate combos allocate from base + 1, so "
            "each plancode owns up to 999 indexes.")
        plan_row.addWidget(self.base_index_edit)

        plan_row.addSpacing(8)
        plan_row.addWidget(self._dim_label("Maturity"))
        self.maturity_lbl = QLineEdit()
        self.maturity_lbl.setReadOnly(True)
        self.maturity_lbl.setFixedWidth(84)
        self.maturity_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.maturity_lbl.setPlaceholderText("from IAF")
        self.maturity_lbl.setToolTip(
            "Derived from the IAF plan header ME-AGE and its use code "
            "(1 = attained age, 0 = duration).")
        plan_row.addWidget(self.maturity_lbl)
        plan_row.addStretch()
        root.addLayout(plan_row)

        # ── Output + source ─────────────────────────────────────────────
        out_row = QHBoxLayout()
        out_row.setSpacing(6)
        out_row.addWidget(self._section_label("Output Folder"))
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Same folder as the IAF file")
        out_row.addWidget(self.output_edit, stretch=1)
        out_row.addWidget(self._small_btn("Browse…", self._browse_output))
        root.addLayout(out_row)

        root.addWidget(self._section_label("Source File"))
        iaf_row = QHBoxLayout()
        iaf_row.setSpacing(6)
        iaf_lbl = QLabel("IAF *")
        iaf_lbl.setStyleSheet(
            f"color: {GOLD_TEXT}; font-size: 12px; font-weight: bold;")
        iaf_lbl.setFixedWidth(72)
        iaf_row.addWidget(iaf_lbl)
        self.iaf_edit = QLineEdit()
        self.iaf_edit.setPlaceholderText("IAF print file…  (required)")
        iaf_row.addWidget(self.iaf_edit, stretch=1)
        browse = self._small_btn("…", self._browse_iaf)
        browse.setFixedWidth(30)
        iaf_row.addWidget(browse)
        self.iaf_status = QLabel("")
        self.iaf_status.setObjectName("FilePreview")
        self.iaf_status.setFixedWidth(120)
        iaf_row.addWidget(self.iaf_status)
        root.addLayout(iaf_row)

        analyze_row = QHBoxLayout()
        self.space_lbl = QLabel("")
        self.space_lbl.setObjectName("FilePreview")
        analyze_row.addWidget(self.space_lbl, stretch=1)
        self.btn_analyze = self._small_btn("  Analyze IAF  ", self._on_analyze)
        self.btn_analyze.setObjectName("PrimaryBtn")
        analyze_row.addWidget(self.btn_analyze)
        root.addLayout(analyze_row)

        # ── Plan settings ───────────────────────────────────────────────
        root.addWidget(self._section_label("Plan Settings"))
        settings_row = QHBoxLayout()
        settings_row.setSpacing(6)

        settings_row.addWidget(self._dim_label("FIRSTLEVEL"))
        self.first_level_edit = QLineEdit("1")
        self.first_level_edit.setObjectName("BenefitIndex")
        self.first_level_edit.setFixedWidth(52)
        self.first_level_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.first_level_edit.setToolTip(
            "Policy years the first select rate is held. 999 = the issue-age "
            "rate never changes. Ignored when the IAF already carries one "
            "select rate per policy year.")
        settings_row.addWidget(self.first_level_edit)

        settings_row.addSpacing(6)
        settings_row.addWidget(self._dim_label("RENLEVEL"))
        self.ren_level_edit = QLineEdit("1")
        self.ren_level_edit.setObjectName("BenefitIndex")
        self.ren_level_edit.setFixedWidth(52)
        self.ren_level_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ren_level_edit.setToolTip(
            "Policy years each later select rate is held.")
        settings_row.addWidget(self.ren_level_edit)

        settings_row.addSpacing(6)
        settings_row.addWidget(self._dim_label("Policy Fee"))
        self.fee_edit = QLineEdit("0")
        self.fee_edit.setObjectName("BenefitIndex")
        self.fee_edit.setFixedWidth(60)
        self.fee_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        settings_row.addWidget(self.fee_edit)
        settings_row.addStretch()
        root.addLayout(settings_row)

        pointer_row = QHBoxLayout()
        pointer_row.setSpacing(6)
        pointer_row.addWidget(self._dim_label("Modal Factors"))
        self.modefact_combo = QComboBox()
        self.modefact_combo.setFixedWidth(300)
        self.modefact_combo.view().setMinimumWidth(360)
        self.modefact_combo.currentIndexChanged.connect(self._on_modefact_changed)
        pointer_row.addWidget(self.modefact_combo)

        pointer_row.addSpacing(10)
        pointer_row.addWidget(self._dim_label("Band Structure"))
        self.bandspec_combo = QComboBox()
        self.bandspec_combo.setFixedWidth(320)
        self.bandspec_combo.view().setMinimumWidth(380)
        self.bandspec_combo.currentIndexChanged.connect(self._on_bandspec_changed)
        pointer_row.addWidget(self.bandspec_combo)
        pointer_row.addStretch()
        root.addLayout(pointer_row)

        # ── Warnings ────────────────────────────────────────────────────
        self.warn_toggle = QPushButton("▸  Warnings")
        self.warn_toggle.setObjectName("LogToggle")
        self.warn_toggle.setCheckable(True)
        self.warn_toggle.clicked.connect(self._toggle_warnings)
        self.warn_toggle.setVisible(False)
        root.addWidget(self.warn_toggle)
        self.warn_area = QTextEdit()
        self.warn_area.setReadOnly(True)
        self.warn_area.setObjectName("LogArea")
        self.warn_area.setFixedHeight(84)
        self.warn_area.setVisible(False)
        root.addWidget(self.warn_area)

        # ── Benefits ────────────────────────────────────────────────────
        ben_header = QHBoxLayout()
        ben_header.addWidget(self._section_label("Benefits"))
        ben_header.addStretch()
        for label, checked in (("Select All", True), ("Clear", False)):
            ben_header.addWidget(
                self._small_btn(label, lambda _=None, c=checked: self._set_all(c)))
        root.addLayout(ben_header)

        self.ben_table = QTableWidget(0, len(self._BENEFIT_COLUMNS))
        self.ben_table.setObjectName("BenefitTable")
        self.ben_table.setHorizontalHeaderLabels(list(self._BENEFIT_COLUMNS))
        self.ben_table.verticalHeader().setVisible(False)
        self.ben_table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self.ben_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.ben_table.horizontalHeader()
        for column, width in ((0, 150), (1, 80), (2, 90), (3, 80)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.ben_table.setColumnWidth(column, width)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.ben_table.setMinimumHeight(110)
        root.addWidget(self.ben_table, stretch=1)

        # ── Build + progress + log ──────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_open = self._small_btn("Open Output", self._open_output)
        self.btn_open.setEnabled(False)
        btn_row.addWidget(self.btn_open)
        self.btn_build = QPushButton("  Build Workup  ")
        self.btn_build.setObjectName("PrimaryBtn")
        self.btn_build.setEnabled(False)
        self.btn_build.clicked.connect(self._on_build)
        btn_row.addWidget(self.btn_build)
        root.addLayout(btn_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        root.addWidget(self.progress_bar)

        self.log_toggle = QPushButton("▸  Processing output")
        self.log_toggle.setObjectName("LogToggle")
        self.log_toggle.setCheckable(True)
        self.log_toggle.clicked.connect(self._toggle_log)
        root.addWidget(self.log_toggle)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setObjectName("LogArea")
        self.log.setFixedHeight(150)
        self.log.setVisible(False)
        root.addWidget(self.log)

    # ------------------------------------------------------------------
    # Small UI helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Reference data
    # ------------------------------------------------------------------

    def _load_reference_data(self):
        worker = CallableWorker(
            lambda: term_reference.load_reference_data(term_reference.DEFAULT_DSN)
        )
        self._reference_worker = WorkerController(self, worker)
        self._reference_worker.result.connect(self._on_reference_loaded)
        self._reference_worker.error.connect(
            lambda message: self._on_reference_loaded(
                term_reference.TermReferenceData(error=message)
            )
        )
        self._reference_worker.start()

    def _on_reference_loaded(self, data):
        self._reference = data
        self._populate_reference_combos()
        if not self._reference.available:
            self.log.append(
                "Could not read the shared reference tables — enter the "
                f"Index(MODEFACT), Index(BANDSPEC) and base index by hand.\n"
                f"  {self._reference.error}")
        elif not self.base_index_edit.text().strip():
            self.base_index_edit.setText(str(data.next_base_index()))

    def _populate_reference_combos(self):
        for combo, choices, new_label in (
            (self.modefact_combo,
             term_reference.modefact_choices(self._reference),
             "New modal factors…"),
            (self.bandspec_combo,
             term_reference.bandspec_choices(self._reference),
             "New band structure…"),
        ):
            combo.blockSignals(True)
            combo.clear()
            for label, index in choices:
                combo.addItem(label, index)
            combo.addItem(new_label, _NEW_ENTRY)
            combo.setCurrentIndex(0 if choices else combo.count() - 1)
            combo.blockSignals(False)

    def _on_modefact_changed(self, _row: int):
        if self.modefact_combo.currentData() != _NEW_ENTRY:
            self._new_modefact = None
            return
        index = self._reference.next_index(self._reference.modefact)
        dialog = _ModeFactorDialog(self, index)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._new_modefact = dialog.selection()
            self.modefact_combo.setItemText(
                self.modefact_combo.currentIndex(),
                f"NEW → {term_reference.describe_modefact(index, self._new_modefact.values)}")
        else:
            self._new_modefact = None
            self.modefact_combo.setCurrentIndex(0)

    def _on_bandspec_changed(self, _row: int):
        if self.bandspec_combo.currentData() != _NEW_ENTRY:
            self._new_bandspec = None
            return
        index = self._reference.next_index(self._reference.bandspecs)
        dialog = _BandStructureDialog(self, index)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._new_bandspec = dialog.selection()
            self.bandspec_combo.setItemText(
                self.bandspec_combo.currentIndex(),
                f"NEW → {term_reference.describe_bandspec(index, self._new_bandspec.rows)}")
        else:
            self._new_bandspec = None
            self.bandspec_combo.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # Browse
    # ------------------------------------------------------------------

    def _browse_iaf(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select IAF File", "", "Text Files (*.txt *.TXT);;All Files (*)")
        if path:
            self.iaf_edit.setText(path)
            if not self.output_edit.text():
                self.output_edit.setText(os.path.dirname(path))

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_edit.setText(folder)

    # ------------------------------------------------------------------
    # Analyze
    # ------------------------------------------------------------------

    def _on_analyze(self):
        iaf_path = self.iaf_edit.text().strip()
        if not iaf_path or not os.path.isfile(iaf_path):
            QMessageBox.warning(self, "Term Workup",
                                "Select an IAF file to analyze.")
            return
        self.log.clear()
        self.progress_bar.setValue(0)
        self.btn_analyze.setEnabled(False)
        self.btn_build.setEnabled(False)
        self.space_lbl.setText("Analyzing…")
        self._analyze_worker = start_workup_worker(
            self,
            analyze,
            (TermWorkupSpec(iaf_path=iaf_path),),
            on_progress=self._on_progress,
            on_result=self._on_analyzed,
            on_error=self._on_error,
        )

    def _on_analyzed(self, ana: TermWorkupAnalysis):
        self._analysis = ana
        self.btn_analyze.setEnabled(True)
        self.btn_build.setEnabled(True)
        self.plancode_lbl.setText(ana.plancode)
        self.version_edit.setText(str(ana.issue_version))
        self.maturity_lbl.setText(ana.maturity_label)
        self.space_lbl.setText(ana.rate_space_summary())
        self.space_lbl.setToolTip(ana.rate_space_summary())
        self.iaf_status.setText(f"✓ {len(ana.combos)} combos")

        self.ben_table.setRowCount(0)
        self._ben_rows = []
        for row, (code, label, combos, durations, count) in enumerate(ana.benefits):
            detail = (f"{label} · {combos} combos · "
                      f"{durations or 'no'} select dur · {count:,} rates")
            self._add_benefit_row(row, code, label, detail)

        self._show_warnings(ana.warnings)
        self.log.append(
            "Analysis complete — set FIRSTLEVEL/RENLEVEL, confirm the modal "
            "and band pointers, then Build Workup.")

    def _add_benefit_row(self, row: int, code: str, label: str, detail: str):
        self.ben_table.insertRow(row)

        cell = QWidget()
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(4, 0, 0, 0)
        layout.setSpacing(6)
        include = QCheckBox()
        include.setObjectName("BenefitCheck")
        include.setChecked(True)
        include.setToolTip("Include this benefit in the workup.")
        layout.addWidget(include)
        name = QLabel(f"{code}  {label}")
        name.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: bold;")
        layout.addWidget(name)
        layout.addStretch()
        self.ben_table.setCellWidget(row, 0, cell)

        renew_cell = QWidget()
        renew_layout = QHBoxLayout(renew_cell)
        renew_layout.setContentsMargins(0, 0, 0, 0)
        renew_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        renewable = QCheckBox()
        renewable.setObjectName("BenefitCheck")
        renewable.setChecked(True)
        renewable.setToolTip(
            "Rate follows attained age (renewable). Unchecked holds the "
            "issue-age rate for every duration.")
        renew_layout.addWidget(renewable)
        self.ben_table.setCellWidget(row, 1, renew_cell)

        cease = QLineEdit()
        cease.setObjectName("BenefitIndex")
        cease.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cease.setPlaceholderText("plan")
        cease.setToolTip(
            "Attained age the charge stops before. Blank uses the plan "
            "maturity; the IAF's own rates stop earlier when they run out.")
        self.ben_table.setCellWidget(row, 2, cease)

        max_dur = QLineEdit()
        max_dur.setObjectName("BenefitIndex")
        max_dur.setAlignment(Qt.AlignmentFlag.AlignCenter)
        max_dur.setPlaceholderText("none")
        max_dur.setToolTip(
            "Cap on policy years. Combines with Cease Age as 'whichever "
            "comes first' — e.g. 20 years or age 60.")
        self.ben_table.setCellWidget(row, 3, max_dur)

        detail_item = QTableWidgetItem(detail)
        detail_item.setToolTip(detail)
        self.ben_table.setItem(row, 4, detail_item)

        self._ben_rows.append({
            "code": code, "label": label, "include": include,
            "renewable": renewable, "cease": cease, "max_dur": max_dur,
        })

    def _set_all(self, checked: bool):
        for entry in self._ben_rows:
            entry["include"].setChecked(checked)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _optional_int(self, edit: QLineEdit, label: str) -> tuple:
        """Parse an optional whole number: (ok, value-or-None)."""
        text = edit.text().strip()
        if not text:
            return True, None
        try:
            return True, int(text)
        except ValueError:
            QMessageBox.warning(self, "Term Workup",
                                f"{label} must be a whole number.")
            return False, None

    def _gather_spec(self) -> TermWorkupSpec | None:
        if self._analysis is None:
            return None
        try:
            base_index = int(self.base_index_edit.text().strip())
        except ValueError:
            QMessageBox.warning(
                self, "Term Workup",
                "Enter the plancode's base index (a free multiple of 1000).")
            return None
        try:
            first_level = int(self.first_level_edit.text().strip() or "1")
            ren_level = int(self.ren_level_edit.text().strip() or "1")
            issue_version = int(self.version_edit.text().strip() or "1")
        except ValueError:
            QMessageBox.warning(
                self, "Term Workup",
                "FIRSTLEVEL, RENLEVEL and Issue Version must be whole numbers.")
            return None
        try:
            fee = float(self.fee_edit.text().strip() or "0")
        except ValueError:
            QMessageBox.warning(self, "Term Workup",
                                "Policy Fee must be a number.")
            return None

        modefact = self._new_modefact or ModeFactorSelection(
            index=str(self.modefact_combo.currentData() or "0"))
        bandspec = self._new_bandspec or BandStructureSelection(
            index=str(self.bandspec_combo.currentData() or "0"))
        if modefact.index == _NEW_ENTRY or bandspec.index == _NEW_ENTRY:
            QMessageBox.warning(
                self, "Term Workup",
                "Finish defining the new modal factors / band structure, or "
                "pick an existing index.")
            return None

        benefits = []
        for entry in self._ben_rows:
            ok, cease_age = self._optional_int(
                entry["cease"], f"Benefit {entry['code']} cease age")
            if not ok:
                return None
            ok, max_duration = self._optional_int(
                entry["max_dur"], f"Benefit {entry['code']} max duration")
            if not ok:
                return None
            benefits.append(TermBenefitSelection(
                code=entry["code"],
                label=entry["label"],
                include=entry["include"].isChecked(),
                renewable=entry["renewable"].isChecked(),
                cease_age=cease_age,
                max_duration=max_duration,
            ))

        output_dir = (self.output_edit.text().strip()
                      or os.path.dirname(self.iaf_edit.text().strip()))
        return TermWorkupSpec(
            plancode=self._analysis.plancode,
            output_dir=output_dir,
            iaf_path=self.iaf_edit.text().strip(),
            issue_version=issue_version,
            base_index=base_index,
            first_level=first_level,
            ren_level=ren_level,
            fee=fee,
            modefact=modefact,
            bandspec=bandspec,
            benefits=benefits,
        )

    def _on_build(self):
        spec = self._gather_spec()
        if spec is None:
            return
        self.progress_bar.setValue(0)
        self.btn_build.setEnabled(False)
        self.btn_analyze.setEnabled(False)
        self._build_worker = start_workup_worker(
            self,
            build,
            (spec, self._analysis),
            on_progress=self._on_progress,
            on_result=self._on_built,
            on_error=self._on_error,
        )

    def _on_built(self, res: TermWorkupResult):
        self._output_path = res.output_path
        self.btn_build.setEnabled(True)
        self.btn_analyze.setEnabled(True)
        self.btn_open.setEnabled(True)
        self.log.append("\n── Term Workup Summary ──")
        for name, count in res.table_counts.items():
            line = f"  {name:<22} {count:>10,} rows"
            self.log.append(line)
        for name, span in res.index_ranges.items():
            self.log.append(f"  {name:<22} indexes {span}")
        self._show_warnings(res.warnings)
        if res.warnings:
            self.log.append(f"\n⚠ {len(res.warnings)} warning(s) — see the "
                            "Warnings section / WORKUP_SUMMARY.")
        self.log.append(f"\n✓  Saved to → {res.output_path}")
        self.log_toggle.setChecked(True)
        self._toggle_log()
        self.workup_built.emit(res.output_path)
