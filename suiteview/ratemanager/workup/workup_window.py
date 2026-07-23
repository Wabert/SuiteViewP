"""
Rate Workup panel — single-pass, multi-file rate loading for one plancode.

Workflow:  pick files → Analyze → review the rate space / pick benefits &
plan ids → Build.  Output is a folder of UL_Rates-ready CSVs (POINT_PVSRB,
RATE_COI, RATE_TRGPREM, RATE_SCR, RATE_EPU, POINT_BENEFIT, RATE_BENCOI,
RATE_BENTRG + WORKUP_SUMMARY) or one review workbook.

``RateWorkupPanel`` is the main view of :class:`RateManagerWindow`; the
per-file converter tabs are reachable from its header toggle.
"""

from __future__ import annotations

import os
import subprocess
import sys

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog,
    QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QRadioButton, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from suiteview.polview.models.cl_polrec.policy_translations import (
    STATE_CODE_TO_ABBR,
)

from suiteview.ratemanager.rm_styles import (
    GOLD_TEXT, TEXT, TEXT_MID, body_stylesheet,
)
from suiteview.ratemanager.ui_helpers import (
    set_expanding_panel_visible, update_cease_age_field,
)
from suiteview.ratemanager.workup.builder import (
    WorkupAnalysis, WorkupResult, analyze, benefit_start_index, build,
)
from suiteview.ratemanager.workup.spec import BenefitSelection, WorkupSpec


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

class _AnalyzeWorker(QThread):
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(object)          # WorkupAnalysis
    error = pyqtSignal(str)

    def __init__(self, spec: WorkupSpec):
        super().__init__()
        self._spec = spec

    def run(self):
        try:
            ana = analyze(
                self._spec,
                progress_cb=lambda f, m: self.progress.emit(f, m))
            if ana.error:
                self.error.emit(ana.error)
            else:
                self.finished.emit(ana)
        except Exception as exc:
            self.error.emit(str(exc))


class _BuildWorker(QThread):
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(object)          # WorkupResult
    error = pyqtSignal(str)

    def __init__(self, spec: WorkupSpec, analysis: WorkupAnalysis):
        super().__init__()
        self._spec = spec
        self._analysis = analysis

    def run(self):
        try:
            res = build(
                self._spec, self._analysis,
                progress_cb=lambda f, m: self.progress.emit(f, m))
            if res.error:
                self.error.emit(res.error)
            else:
                self.finished.emit(res)
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# State-code confirmation dialog (CKULTB04)
# ---------------------------------------------------------------------------

class _StateMapDialog(QDialog):
    """Confirm the CKULTB04 numeric state codes → 2-letter abbreviations.

    Recommendations come from the CyberLife numeric state table
    (``STATE_CODE_TO_ABBR``); the user can correct any of them. '**' never
    appears here — it maps to 'AA' automatically.
    """

    _PAIRS_PER_ROW = 4

    def __init__(self, parent, codes: list, prefill: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Confirm State Codes")
        self.setObjectName("RateManagerBody")
        self.setStyleSheet(body_stylesheet())
        prefill = prefill or {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        intro = QLabel(
            "The CKULTB04 file uses CyberLife numeric state codes. Confirm "
            "the mapping for this plan (recommendations from the CyberLife "
            "state table):")
        intro.setObjectName("Subtitle")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        self._edits: dict = {}
        for i, code in enumerate(codes):
            row, col = divmod(i, self._PAIRS_PER_ROW)
            lbl = QLabel(f"{code} →")
            lbl.setStyleSheet(f"color: {TEXT_MID}; font-size: 12px;")
            try:
                rec = prefill.get(code) or STATE_CODE_TO_ABBR.get(int(code), "")
            except ValueError:
                rec = prefill.get(code, "")
            edit = QLineEdit(rec)
            edit.setObjectName("BenefitIndex")
            edit.setFixedWidth(42)
            edit.setMaxLength(2)
            edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(lbl, row, col * 2)
            grid.addWidget(edit, row, col * 2 + 1)
            self._edits[code] = edit
        layout.addLayout(grid)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("SecondaryBtn")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        ok = QPushButton("  Confirm  ")
        ok.setObjectName("PrimaryBtn")
        ok.clicked.connect(self._on_accept)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

    def _on_accept(self):
        blank = [c for c, e in self._edits.items() if not e.text().strip()]
        if blank:
            QMessageBox.warning(
                self, "Missing States",
                "Enter a 2-letter state for: " + ", ".join(blank))
            return
        self.accept()

    def mapping(self) -> dict:
        return {c: e.text().strip().upper() for c, e in self._edits.items()}

    @staticmethod
    def get_mapping(parent, codes: list, prefill: dict | None = None):
        """Show the dialog; return the confirmed mapping or None on cancel."""
        dlg = _StateMapDialog(parent, codes, prefill)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.mapping()
        return None


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

class RateWorkupPanel(QWidget):
    """Comprehensive per-plancode rate workup — all four files, one pass."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._analysis: WorkupAnalysis | None = None
        self._analyze_worker: _AnalyzeWorker | None = None
        self._build_worker: _BuildWorker | None = None
        self._output_path = ""
        self._state_map_cache: dict = {}   # (scr_path, plan) → confirmed map
        self.setObjectName("RateManagerBody")
        self.setStyleSheet(body_stylesheet())
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(8)

        subtitle = QLabel(
            "Load every rate file for one plancode in a single pass — the "
            "pointer varies by the same State/Sex/Class/Band space as the "
            "base COI rates.")
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        # ── Plan + output row ───────────────────────────────────────────
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
        plan_row.addWidget(self._dim_label("Maturity"))
        self.maturity_edit = QLineEdit("121")
        self.maturity_edit.setObjectName("BenefitIndex")
        self.maturity_edit.setFixedWidth(48)
        self.maturity_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plan_row.addWidget(self.maturity_edit)
        plan_row.addSpacing(8)
        plan_row.addWidget(self._dim_label("Base Index"))
        self.base_index_edit = QLineEdit()
        self.base_index_edit.setObjectName("BenefitIndex")
        self.base_index_edit.setFixedWidth(64)
        self.base_index_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.base_index_edit.setPlaceholderText("required")
        self.base_index_edit.setToolTip(
            "The plancode's base index — every rate table (COI, TRGPREM, SCR, "
            "EPU, benefits) allocates its indexes starting here.")
        plan_row.addWidget(self.base_index_edit)
        plan_row.addSpacing(14)
        self.fmt_db = QRadioButton("DB Format (CSV folder)")
        self.fmt_db.setChecked(True)
        self.fmt_excel = QRadioButton("Excel workbook")
        radio_style = (f"QRadioButton {{ color: {TEXT}; font-size: 12px; "
                       f"font-weight: bold; }}"
                       f"QRadioButton::indicator {{ width: 13px; height: 13px; }}")
        self.fmt_db.setStyleSheet(radio_style)
        self.fmt_excel.setStyleSheet(radio_style)
        plan_row.addWidget(self.fmt_db)
        plan_row.addWidget(self.fmt_excel)
        plan_row.addStretch()
        root.addLayout(plan_row)

        out_row = QHBoxLayout()
        out_row.setSpacing(6)
        out_row.addWidget(self._section_label("Output Folder"))
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Same folder as the IAF file")
        out_row.addWidget(self.output_edit, stretch=1)
        btn = self._small_btn("Browse…", self._browse_output)
        out_row.addWidget(btn)
        root.addLayout(out_row)

        # ── Source files ────────────────────────────────────────────────
        root.addWidget(self._section_label("Source Files"))
        self.iaf_edit, self.iaf_status = self._file_row(
            root, "IAF", required=True)
        self.mpf_edit, self.mpf_status = self._file_row(root, "MPF")
        # Same combo width on both CKULTB rows so the controls line up.
        self.scr_edit, self.scr_status = self._file_row(
            root, "CKULTB04", combo_label="Plan", combo_width=190)
        self.scr_combo = self._last_combo
        self.epu_edit, self.epu_status = self._file_row(
            root, "CKULTB01", combo_label="Plan/Rule", combo_width=190)
        self.epu_combo = self._last_combo

        analyze_row = QHBoxLayout()
        analyze_row.addStretch()
        self.space_lbl = QLabel("")
        self.space_lbl.setObjectName("FilePreview")
        analyze_row.addWidget(self.space_lbl, stretch=1)
        self.btn_analyze = self._small_btn("  Analyze Files  ", self._on_analyze)
        self.btn_analyze.setObjectName("PrimaryBtn")
        analyze_row.addWidget(self.btn_analyze)
        root.addLayout(analyze_row)

        # ── Warnings (collapsible) ──────────────────────────────────────
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

        # ── Benefits grid ───────────────────────────────────────────────
        ben_header = QHBoxLayout()
        ben_header.addWidget(self._section_label("Benefits & Supplementals"))
        ben_header.addStretch()
        for label, checked in (("Select All", True), ("Clear", False)):
            b = self._small_btn(label, lambda _=None, c=checked: self._set_all(c))
            ben_header.addWidget(b)
        root.addLayout(ben_header)

        headers = [
            "Benefit", "Renewable", "Cease Age", "MPF Code", "Start Index",
            "Detail",
        ]
        self.ben_table = QTableWidget(0, len(headers))
        self.ben_table.setObjectName("BenefitTable")
        self.ben_table.setHorizontalHeaderLabels(headers)
        self.ben_table.verticalHeader().setVisible(False)
        self.ben_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.ben_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # Fixed, readable column widths — no stretching to fill; empty space
        # can show at the right.
        hh = self.ben_table.horizontalHeader()
        for col, width in (
            (0, 105), (1, 75), (2, 110), (3, 165), (4, 90), (5, 220)
        ):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.ben_table.setColumnWidth(col, width)
        self.ben_table.setMinimumHeight(120)
        root.addWidget(self.ben_table, stretch=1)
        self._ben_rows: list = []
        self.base_index_edit.textChanged.connect(self._refresh_auto_indexes)

        # ── Build row + progress + log ──────────────────────────────────
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

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("SectionLabel")
        return lbl

    def _dim_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {TEXT_MID}; font-size: 12px;")
        return lbl

    def _small_btn(self, text: str, slot) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("SecondaryBtn")
        btn.clicked.connect(slot)
        return btn

    def _file_row(self, root: QVBoxLayout, kind: str,
                  required: bool = False, combo_label: str = "",
                  combo_width: int = 130):
        """One dense source-file row: label, path, Browse, [combo], status."""
        row = QHBoxLayout()
        row.setSpacing(6)
        lbl = QLabel(kind + (" *" if required else ""))
        lbl.setStyleSheet(
            f"color: {GOLD_TEXT if required else TEXT}; font-size: 12px; "
            f"font-weight: bold;")
        lbl.setFixedWidth(72)
        row.addWidget(lbl)

        edit = QLineEdit()
        edit.setPlaceholderText(
            f"{kind} print file…" + ("  (required)" if required else "  (optional)"))
        row.addWidget(edit, stretch=1)

        btn = self._small_btn("…", lambda: self._browse_file(edit, kind))
        btn.setFixedWidth(30)
        row.addWidget(btn)

        self._last_combo = None
        if combo_label:
            combo_lbl = self._dim_label(combo_label)
            combo_lbl.setFixedWidth(56)   # equal label width keeps rows aligned
            row.addWidget(combo_lbl)
            combo = QComboBox()
            combo.setFixedWidth(combo_width)
            # Let the popup list grow past the control width so long
            # plan/freq/rule entries stay readable.
            combo.view().setMinimumWidth(combo_width + 60)
            combo.setEnabled(False)
            row.addWidget(combo)
            self._last_combo = combo

        status = QLabel("")
        status.setObjectName("FilePreview")
        status.setFixedWidth(120)
        row.addWidget(status)
        root.addLayout(row)
        return edit, status

    def _toggle_warnings(self):
        shown = self.warn_toggle.isChecked()
        self.warn_area.setVisible(shown)
        self.warn_toggle.setText(
            ("▾" if shown else "▸") + self.warn_toggle.text()[1:])

    def _toggle_log(self):
        shown = self.log_toggle.isChecked()
        set_expanding_panel_visible(self, self.log, shown)
        self.log_toggle.setText(
            ("▾" if shown else "▸") + "  Processing output")

    # ------------------------------------------------------------------
    # Browse actions
    # ------------------------------------------------------------------

    def _browse_file(self, edit: QLineEdit, kind: str):
        path, _ = QFileDialog.getOpenFileName(
            self, f"Select {kind} File", "",
            "Text Files (*.txt *.TXT);;All Files (*)")
        if path:
            edit.setText(path)
            if edit is self.iaf_edit and not self.output_edit.text():
                self.output_edit.setText(os.path.dirname(path))

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_edit.setText(folder)

    # ------------------------------------------------------------------
    # Analyze
    # ------------------------------------------------------------------

    def _gather_paths_spec(self) -> WorkupSpec | None:
        spec = WorkupSpec(
            iaf_path=self.iaf_edit.text().strip(),
            mpf_path=self.mpf_edit.text().strip(),
            scr_path=self.scr_edit.text().strip(),
            epu_path=self.epu_edit.text().strip(),
        )
        if not spec.iaf_path or not os.path.isfile(spec.iaf_path):
            QMessageBox.warning(self, "No IAF File",
                                "Select a valid IAF file — it defines the "
                                "plancode and rate space.")
            return None
        for label, path in (("MPF", spec.mpf_path),
                            ("CKULTB04", spec.scr_path),
                            ("CKULTB01", spec.epu_path)):
            if path and not os.path.isfile(path):
                QMessageBox.warning(self, f"Bad {label} Path",
                                    f"The {label} file does not exist:\n{path}")
                return None
        return spec

    def _on_analyze(self):
        spec = self._gather_paths_spec()
        if spec is None:
            return
        self.log.clear()
        self.progress_bar.setValue(0)
        self.btn_analyze.setEnabled(False)
        self.btn_build.setEnabled(False)
        self.space_lbl.setText("Analyzing…")
        self._analyze_worker = _AnalyzeWorker(spec)
        self._analyze_worker.progress.connect(self._on_progress)
        self._analyze_worker.finished.connect(self._on_analyzed)
        self._analyze_worker.error.connect(self._on_error)
        self._analyze_worker.start()

    def _on_analyzed(self, ana: WorkupAnalysis):
        self._analysis = ana
        self.btn_analyze.setEnabled(True)
        self.btn_build.setEnabled(True)
        self.plancode_lbl.setText(ana.plancode)
        if ana.pay_age:
            self.maturity_edit.setText(str(ana.pay_age))
        self.space_lbl.setText(ana.rate_space_summary())
        self.space_lbl.setToolTip(ana.rate_space_summary())

        # Statuses
        self.iaf_status.setText(f"✓ {len(ana.combos)} combos")
        self.mpf_status.setText(
            f"✓ {len(ana.mpf_codes)} codes" if ana.mpf_codes else "")
        self.scr_status.setText(
            f"✓ {len(ana.scr_plans)} plans" if ana.scr_plans else "")
        self.epu_status.setText(
            f"✓ {len(ana.epu_groups)} groups" if ana.epu_groups else "")

        # CKULTB04 plan picker
        self.scr_combo.clear()
        self.scr_combo.setEnabled(bool(ana.scr_plans))
        for code, count in ana.scr_plans:
            self.scr_combo.addItem(f"{code}   ({count:,} recs)", code)

        # CKULTB01 plan/freq/rule picker
        self.epu_combo.clear()
        self.epu_combo.setEnabled(bool(ana.epu_groups))
        for plan, freq, rule, count in ana.epu_groups:
            self.epu_combo.addItem(
                f"{plan} / {freq} / {rule}   ({count:,} recs)",
                (plan, freq, rule))

        # Benefits grid — one row per IAF benefit code. The MPF Code column
        # links a benefit to the MPF premium code that carries its charges;
        # 0 COI rates in the IAF with target rates present is the telltale.
        self.ben_table.setRowCount(0)
        self._ben_rows = []
        for row, (code, coi_n, trg_n) in enumerate(ana.iaf_benefits):
            in_mpf = coi_n == 0 and trg_n > 0
            detail = f"coi {coi_n:,} · trg {trg_n:,}"
            if in_mpf:
                detail += "  →  COI in MPF?"
            self._add_benefit_row(
                row, code, detail, ana.mpf_codes,
                suggest_mpf=in_mpf, has_iaf_coi=coi_n > 0)

        # Warnings
        self._show_warnings(ana.warnings)
        self.log.append("Analysis complete — review the rate space, pick "
                        "benefits and plan ids, then Build Workup.")

    def _show_warnings(self, warnings: list):
        if warnings:
            self.warn_toggle.setText(f"▸  Warnings ({len(warnings)})")
            self.warn_toggle.setVisible(True)
            self.warn_area.setPlainText("\n".join(f"⚠ {w}" for w in warnings))
        else:
            self.warn_toggle.setVisible(False)
            self.warn_area.setVisible(False)
            self.warn_toggle.setChecked(False)

    def _add_benefit_row(self, row: int, code: str, detail: str,
                         mpf_codes: list, suggest_mpf: bool = False,
                         checked: bool = True, has_iaf_coi: bool = False):
        self.ben_table.insertRow(row)

        cell = QWidget()
        lay = QHBoxLayout(cell)
        lay.setContentsMargins(4, 0, 0, 0)
        lay.setSpacing(6)
        chk = QCheckBox()
        chk.setObjectName("BenefitCheck")
        chk.setChecked(checked)
        chk.setToolTip("Include in the workup.")
        lay.addWidget(chk)
        lbl = QLabel(code)
        lbl.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: bold;")
        lay.addWidget(lbl)
        lay.addStretch()
        self.ben_table.setCellWidget(row, 0, cell)

        ren_cell = QWidget()
        ren_lay = QHBoxLayout(ren_cell)
        ren_lay.setContentsMargins(0, 0, 0, 0)
        ren_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ren_chk = QCheckBox()
        ren_chk.setObjectName("BenefitCheck")
        ren_chk.setToolTip("Rate varies by attained age (renewable). "
                           "Unchecked = level rate set at issue.")
        ren_lay.addWidget(ren_chk)
        self.ben_table.setCellWidget(row, 1, ren_cell)

        cease_edit = QLineEdit()
        cease_edit.setObjectName("BenefitIndex")
        cease_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cease_edit.setToolTip(
            "Required for a non-renewing benefit. Charges stop at this age; "
            "cease age 65 produces rates through attained age 64.")
        self.ben_table.setCellWidget(row, 2, cease_edit)

        # MPF Code picker: blank = charges come from the IAF. Codes whose
        # MPF benefit type matches this benefit are listed first.
        mpf_combo = QComboBox()
        mpf_combo.setFixedWidth(168)
        mpf_combo.view().setMinimumWidth(210)
        mpf_combo.setToolTip(
            "MPF premium code carrying this benefit's charges. Leave blank "
            "when the COI rates are in the IAF itself.")
        mpf_combo.addItem("", "")
        matching = [
            (pc, ben) for pc, ben, _cn, _rn in mpf_codes
            if code in str(ben).split("/")
        ]
        others = [
            (pc, ben) for pc, ben, _cn, _rn in mpf_codes
            if code not in str(ben).split("/")
        ]
        for pc, ben in matching + others:
            mpf_combo.addItem(f"{pc} — {ben}", pc)
        mpf_combo.setEnabled(bool(mpf_codes))
        if suggest_mpf and len(matching) == 1:
            mpf_combo.setCurrentIndex(1)      # the single matching code
        self.ben_table.setCellWidget(row, 3, mpf_combo)

        def _sync_cease_age() -> None:
            update_cease_age_field(
                chk.isChecked(),
                ren_chk.isChecked(),
                has_iaf_coi or bool(mpf_combo.currentData()),
                cease_edit,
            )

        chk.toggled.connect(_sync_cease_age)
        ren_chk.toggled.connect(_sync_cease_age)
        mpf_combo.currentIndexChanged.connect(_sync_cease_age)
        _sync_cease_age()

        # Start Index — prefilled by the convention (base + type code,
        # two zeros appended); editable, and re-derived when the base index
        # changes unless the user typed their own value.
        idx_edit = QLineEdit()
        idx_edit.setObjectName("BenefitIndex")
        idx_edit.setToolTip(
            "First Index(BENCOI)/Index(BENTRG) for this benefit.\n"
            "Convention: base index with the 2-digit type code inserted and "
            "two zeros appended (13400 + benefit 12 → 1341200). Letters map "
            "via the subtype table; edit freely to override.")
        idx_edit.setProperty("auto", True)
        idx_edit.textEdited.connect(
            lambda _t, e=idx_edit: e.setProperty("auto", False))
        self._set_auto_index(code, idx_edit)
        self.ben_table.setCellWidget(row, 4, idx_edit)

        info_item = QTableWidgetItem(detail)
        info_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if suggest_mpf:
            info_item.setForeground(QColor(GOLD_TEXT))
        self.ben_table.setItem(row, 5, info_item)

        self._ben_rows.append(
            (code, chk, ren_chk, cease_edit, mpf_combo, idx_edit, has_iaf_coi))

    def _set_auto_index(self, code: str, idx_edit: QLineEdit) -> None:
        try:
            base = int(self.base_index_edit.text().strip())
        except ValueError:
            idx_edit.setText("")
            return
        auto = benefit_start_index(base, code)
        idx_edit.setText(str(auto) if auto else "")

    def _refresh_auto_indexes(self) -> None:
        """Base index changed — re-derive indexes the user hasn't overridden."""
        for code, _chk, _ren, _cease, _mpf, idx_edit, _has_coi in self._ben_rows:
            if idx_edit.property("auto"):
                self._set_auto_index(code, idx_edit)

    def _set_all(self, checked: bool):
        for _code, chk, _ren, _cease, _mpf, _idx, _has_coi in self._ben_rows:
            chk.setChecked(checked)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _on_build(self):
        if self._analysis is None:
            QMessageBox.warning(self, "Not Analyzed",
                                "Click 'Analyze Files' first.")
            return
        spec = self._gather_paths_spec()
        if spec is None:
            return

        spec.plancode = self._analysis.plancode
        spec.fmt = "excel" if self.fmt_excel.isChecked() else "db"

        try:
            spec.maturity_age = int(self.maturity_edit.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Invalid Maturity",
                                "Maturity age must be a whole number.")
            return
        base_index_text = self.base_index_edit.text().strip()
        if not base_index_text:
            QMessageBox.warning(
                self, "Missing Base Index",
                "Enter the Base Index before building rates.")
            return
        try:
            spec.base_index = int(base_index_text)
        except ValueError:
            QMessageBox.warning(
                self, "Invalid Base Index",
                "The Base Index must be a whole number.")
            return
        if spec.base_index <= 0:
            QMessageBox.warning(
                self, "Invalid Base Index",
                "The Base Index must be greater than 0.")
            return

        spec.output_dir = self.output_edit.text().strip() or os.path.dirname(
            spec.iaf_path)

        if spec.scr_path:
            data = self.scr_combo.currentData()
            if not data:
                QMessageBox.warning(
                    self, "No CKULTB04 Plan",
                    "Pick which internal plan code in the CKULTB04 file "
                    "belongs to this plancode.")
                return
            spec.scr_plan = data

            # Confirm how the plan's numeric state codes map to 2-letter
            # states ('**' → 'AA' automatically).
            raw_states = self._analysis.scr_states.get(spec.scr_plan, [])
            numeric = sorted(
                s for s in raw_states if s not in ("**", "AA", ""))
            if numeric:
                cache_key = (spec.scr_path, spec.scr_plan)
                mapping = _StateMapDialog.get_mapping(
                    self, numeric, self._state_map_cache.get(cache_key))
                if mapping is None:
                    return
                self._state_map_cache[cache_key] = mapping
                spec.state_map = mapping
        if spec.epu_path:
            data = self.epu_combo.currentData()
            if not data:
                QMessageBox.warning(
                    self, "No CKULTB01 Plan/Rule",
                    "Pick which plan/freq/rule group in the CKULTB01 file "
                    "belongs to this plancode.")
                return
            spec.epu_plan, spec.epu_freq, spec.epu_rule = data

        benefits = []
        for (
            code, chk, ren_chk, cease_edit, mpf_combo, idx_edit, has_iaf_coi
        ) in self._ben_rows:
            if not chk.isChecked():
                continue
            cease_age = None
            has_bencoi = has_iaf_coi or bool(mpf_combo.currentData())
            if not ren_chk.isChecked() and has_bencoi:
                cease_text = cease_edit.text().strip()
                if not cease_text:
                    QMessageBox.warning(
                        self, "Missing Cease Age",
                        f"Benefit {code}: enter the age when this "
                        "non-renewing benefit ceases.")
                    return
                try:
                    cease_age = int(cease_text)
                except ValueError:
                    QMessageBox.warning(
                        self, "Invalid Cease Age",
                        f"Benefit {code}: Cease Age must be a whole number.")
                    return
                if cease_age <= 0:
                    QMessageBox.warning(
                        self, "Invalid Cease Age",
                        f"Benefit {code}: Cease Age must be greater than 0.")
                    return
            try:
                start_index = int(idx_edit.text().strip())
            except ValueError:
                QMessageBox.warning(
                    self, "Invalid Start Index",
                    f"Benefit {code}: the Start Index must be a whole number "
                    "(its type code has no automatic mapping).")
                return
            benefits.append(BenefitSelection(
                code=code, renewable=ren_chk.isChecked(),
                cease_age=cease_age,
                mpf_code=mpf_combo.currentData() or "",
                start_index=start_index))
        spec.benefits = benefits
        if any(b.mpf_code for b in benefits) and not spec.mpf_path:
            QMessageBox.warning(
                self, "No MPF File",
                "Some benefits are linked to MPF codes but no MPF file is "
                "selected — their COI rates would be skipped.")
            return

        # Confirm before overwriting an existing workup output.
        if spec.fmt == "excel":
            target = os.path.join(
                spec.output_dir, f"{spec.plancode} - Workup DB.xlsx")
        else:
            target = os.path.join(spec.output_dir, f"{spec.plancode}_Workup")
        if os.path.exists(target):
            reply = QMessageBox.question(
                self, "Overwrite Existing Output?",
                f"The output already exists:\n{target}\n\nOverwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.log.clear()
        self.progress_bar.setValue(0)
        self.btn_build.setEnabled(False)
        self.btn_analyze.setEnabled(False)
        self.btn_open.setEnabled(False)
        self._output_path = ""

        self._build_worker = _BuildWorker(spec, self._analysis)
        self._build_worker.progress.connect(self._on_progress)
        self._build_worker.finished.connect(self._on_built)
        self._build_worker.error.connect(self._on_error)
        self._build_worker.start()

    def _on_built(self, res: WorkupResult):
        self._output_path = res.output_path
        self.btn_build.setEnabled(True)
        self.btn_analyze.setEnabled(True)
        self.btn_open.setEnabled(True)
        self.log.append("\n── Workup Summary ──")
        for name, count in res.table_counts.items():
            rng = res.index_ranges.get(name, "")
            line = f"  {name:<15} {count:>10,} rows"
            if rng and rng != "—":
                line += f"   indexes {rng}"
            self.log.append(line)
        self._show_warnings(res.warnings)
        if res.warnings:
            self.log.append(f"\n⚠ {len(res.warnings)} warning(s) — see the "
                            "Warnings section / WORKUP_SUMMARY.")
        self.log.append(f"\n✓  Saved to → {res.output_path}")
        self.log_toggle.setChecked(True)
        self._toggle_log()

    # ------------------------------------------------------------------
    # Progress / error / open
    # ------------------------------------------------------------------

    def _on_progress(self, pct: float, msg: str):
        self.progress_bar.setValue(int(pct * 1000))
        if msg:
            self.log.append(msg)

    def _on_error(self, err: str):
        self.btn_analyze.setEnabled(True)
        self.btn_build.setEnabled(self._analysis is not None)
        self.space_lbl.setText("")
        self.log.append(f"\n✗  Error: {err}")
        QMessageBox.critical(self, "Workup Error", err.split("\n")[0])

    def _open_output(self):
        path = self._output_path
        if not path or not (os.path.isfile(path) or os.path.isdir(path)):
            return
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
