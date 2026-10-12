"""RERUN workspace for interest sensitive whole life on reduced paid-up (ISWL RPU).

RERUN swaps its UL/ISWL tabs for this workspace when the loaded policy is an ISWL
(advanced product, base product line I) on premium pay status 45. A paid-up policy has
no premiums, withdrawals, death benefit options or face changes, so the inputs are only
the illustrate-to age. Pages: **Policy** (the snapshot, the NSP basis and the three
stored NSPs, loans and any reason Run is refused), **Illustration Inputs**, **Values**
(monthly and annual values on CyberLife's basis beside the endowment NSP, the NSP
schedule and the **NSP Workup** of a selected anniversary's roll-forward), the **Report**
(the illustration pages, landscape PDF) and the **In-force Check** (SuiteView's
roll-forward against the stored NSPs and its starting cash value against PolView's).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Dict, List, Optional

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from suiteview.illustration.core.inforce_check import rate_check_notice
from suiteview.illustration.core.iswl_rpu.report import build_iswl_rpu_report
from suiteview.illustration.core.iswl_rpu.service import ISWLRPUBasis
from suiteview.illustration.core.iswl_rpu.workup import RollWorkup, roll_workup, workup_durations
from suiteview.illustration.core.ledger_report import format_ledger_pages
from suiteview.illustration.core.parwl.nsp import NSPError
from suiteview.illustration.models.iswl_rpu import ISWLRPUBenefit, ISWLRPUInputs, ISWLRPUPolicy, ISWLRPUResult
from suiteview.polview.ui.widgets import StyledInfoTableGroup
from suiteview.ui.widgets.filter_table_view import FilterTableView

from .illustration_pages_view import IllustrationPagesView, InforceChecksView, ReportPages
from .policy_snapshot_widgets import BenefitButtonsGroup, money, short_date
from .policy_tab import RATE_WARNING_STYLE
from .styles import GROUP_STYLE, INPUT_COMBO_STYLE, PURPLE_BG, PURPLE_DARK, TAB_WIDGET_STYLE

logger = logging.getLogger(__name__)

LEDGER_COLUMNS = (
    ("policy_year", "Year"), ("age", "Age"), ("end_date", "End of Year"), ("nsp", "NSP per $1,000 (CyberLife)"),
    ("cash_value", "Cash Value (CyberLife basis)"), ("comparison_nsp", "Endowment NSP per $1,000"),
    ("comparison_cash_value", "Comparison NSP Value"), ("difference", "Difference"),
    ("death_benefit", "Death Benefit"), ("loan", "Loan"), ("frozen", "Frozen (unverified)"), ("notes", "Notes"),
)
MONTH_COLUMNS = (
    ("when", "Date"), ("policy_year", "Year"), ("month_of_year", "Month"), ("attained_age", "Age"),
    ("boy_nsp", "BOY NSP"), ("eoy_nsp", "EOY NSP"), ("nsp", "NSP per $1,000"), ("cash_value", "Cash Value"),
    ("comparison_nsp", "Endowment NSP"), ("comparison_cash_value", "Comparison Value"),
    ("death_benefit", "Death Benefit"), ("loan", "Loan"), ("frozen", "Frozen"), ("notes", "Notes"),
)
SCHEDULE_COLUMNS = ["Duration", "Anniversary", "Age", "Source", "Carried NSP", "NSP Used", "Endowment NSP",
                    "Difference"]
STEP_COLUMNS = ["Step", "Item", "Formula / Source", "Value", "Check"]
LEFT_ALIGNED_STEP_COLUMNS = ("Item", "Formula / Source", "Value", "Check")
MATCH_BG, DIFFER_BG = "#DFF3E4", "#F9D6D5"
NOTICE_STYLE = ("background: #FFF6D6; color: #3A2A00; border: 1px solid #D9B44A; border-radius: 4px;"
                " padding: 3px 6px; font-size: 11px;")


class ISWLRPUInputError(ValueError):
    """An illustration input cannot be used (explains which)."""


def _cell(attr: str, value):
    if isinstance(value, date):
        return value.strftime("%m/%d/%Y")
    if attr == "frozen":
        return "Yes" if value else ""
    return value


def iswl_rpu_ledger_frame(result: ISWLRPUResult) -> pd.DataFrame:
    rows = [{header: _cell(attr, getattr(year, attr)) for attr, header in LEDGER_COLUMNS} for year in result.years]
    return pd.DataFrame(rows, columns=[header for _attr, header in LEDGER_COLUMNS])


def iswl_rpu_report_pages(result: ISWLRPUResult, run_date: date) -> ReportPages:
    report = build_iswl_rpu_report(result, run_date)
    pages = format_ledger_pages(report)
    return ReportPages(pages, report.width, report.policy_number, report.plancode,
                       f"ISWL reduced paid-up illustration - {len(pages)} pages, landscape.")


def benefit_detail_rows(benefit: ISWLRPUBenefit) -> List[tuple]:
    return [
        ("Code:", benefit.code),
        ("Phase:", benefit.phase),
        ("Description:", benefit.description),
        ("Form:", benefit.form_number),
        ("Issue Date:", short_date(benefit.issue_date)),
        ("Cease Date:", short_date(benefit.cease_date)),
        ("Units:", f"{benefit.units:,.3f}"),
        ("VPU:", f"{benefit.value_per_unit:,.2f}"),
        ("Annual Rate:", f"{benefit.annual_premium_per_unit:,.2f}"),
        ("On RPU:", "Not valued (B20 p.62: processed as ceased)"),
    ]


class ISWLRPUPolicyView(QWidget):
    """The snapshot: policy facts, the NSP basis and stored values, notes and benefit buttons."""

    FIELDS = (("Policy", "policy"), ("Plancode / Form", "plancode"), ("Insured", "insured"),
              ("Issue Date", "issue_date"), ("Issue Age", "issue_age"), ("Sex / Class", "sex_class"),
              ("Status", "status"), ("Valuation Date", "valuation"), ("Last Anniversary", "anniversary"),
              ("Paid-Up Face", "face"), ("Units / VPU", "units"), ("Maturity", "maturity"),
              ("NSP Basis", "nsp_basis"), ("ETI Table", "eti"), ("RPU Benefit Code", "rpu_code"),
              ("Low Duration", "low"), ("Stored NSPs", "stored"), ("PolView NSP CV", "polview"),
              ("Last Account Value", "last_av"), ("Current Loan", "loan"), ("Issue State", "state"))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(8)
        self.check_notice = QLabel("")
        self.check_notice.setStyleSheet(RATE_WARNING_STYLE)
        self.check_notice.setWordWrap(True)
        self.check_notice.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.check_notice.setVisible(False)
        layout.addWidget(self.check_notice)
        self.info = StyledInfoTableGroup("Interest Sensitive Whole Life - Reduced Paid-Up", columns=3,
                                         show_table=False)
        self.info.setStyleSheet(GROUP_STYLE)
        for label, attr in self.FIELDS:
            self.info.add_field(label, attr, 115, 175)
        layout.addWidget(self.info)
        self.notes_group = QGroupBox("Notes")
        self.notes_group.setStyleSheet(GROUP_STYLE)
        notes_layout = QVBoxLayout(self.notes_group)
        notes_layout.setContentsMargins(10, 18, 10, 8)
        self.notes = QLabel("")
        self.notes.setWordWrap(True)
        self.notes.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.notes.setStyleSheet(f"color: {PURPLE_DARK}; background: transparent; font-size: 11px;")
        notes_layout.addWidget(self.notes)
        layout.addWidget(self.notes_group)
        self.benefit_group = BenefitButtonsGroup()
        layout.addWidget(self.benefit_group)
        layout.addStretch(1)

    def set_check_notice(self, text: str) -> None:
        self.check_notice.setText(text)
        self.check_notice.setVisible(bool(text))

    def load(self, basis: ISWLRPUBasis) -> None:
        p = basis.policy
        values = {
            "policy": f"{p.company_code} {p.policy_number}",
            "plancode": f"{p.plancode} / {p.form_number}",
            "insured": p.insured_name,
            "issue_date": short_date(p.issue_date),
            "issue_age": str(p.issue_age),
            "sex_class": f"{p.sex_description or p.rate_sex} / {p.rate_class}",
            "status": f"{p.premium_status} {p.premium_status_description}",
            "valuation": short_date(p.valuation_date),
            "anniversary": short_date(p.last_anniversary),
            "face": money(p.face_amount),
            "units": f"{p.units:,.3f} / {p.value_per_unit:,.2f}",
            "maturity": f"{short_date(p.maturity_date)} (age {p.maturity_age})",
            "nsp_basis": f"{p.nsp_table} {p.nsp_interest:.3%}",
            "eti": p.eti_table,
            "rpu_code": p.rpu_benefit_code,
            "low": str(p.low_duration),
            "stored": " / ".join(f"{v:,.6f}".rstrip("0").rstrip(".") for v in p.stored_nsp),
            "polview": money(p.polview_cash_value) if p.polview_cash_value is not None else p.polview_reason,
            "last_av": short_date(p.last_account_value_date),
            "loan": money(p.loan_balance) if p.current_loans else "None",
            "state": p.issue_state,
        }
        for attr, value in values.items():
            self.info.set_value(attr, value)
        lines = list(p.notes) + [f"Other coverage: {text}" for text in p.other_coverages]
        if p.run_block:
            lines.insert(0, "Run Values is refused: " + p.run_block)
        self.notes.setText("\n".join(lines) or "None.")
        self.benefit_group.load([
            (b.form_number or b.code or f"Benefit {b.phase}", b.description or b.code, benefit_detail_rows(b))
            for b in p.benefits])


class ISWLRPUInputsTab(QWidget):
    """The only choice a paid-up policy has: how far to illustrate."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy: Optional[ISWLRPUPolicy] = None
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(8)
        group = QGroupBox("Reduced Paid-Up Illustration")
        group.setStyleSheet(GROUP_STYLE)
        form = QVBoxLayout(group)
        form.setContentsMargins(10, 18, 10, 8)
        row = QHBoxLayout()
        row.addWidget(self._label("Illustrate to age"))
        self.end_age = QSpinBox()
        self.end_age.setRange(0, 121)
        self.end_age.setSpecialValueText("maturity")
        self.end_age.setToolTip("Stop the illustration at this attained age (the coverage maturity when blank).")
        row.addWidget(self.end_age)
        row.addStretch(1)
        form.addLayout(row)
        self.loan_note = self._note("")
        form.addWidget(self.loan_note)
        form.addWidget(self._note(
            "The policy is paid up: no premiums, withdrawals, death benefit options or face changes apply. "
            "Cash values follow CyberLife's stored NSP roll-forward; the paid-up endowment's NSP is shown beside them."))
        layout.addWidget(group)
        layout.addStretch(1)

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(f"color: {PURPLE_DARK}; background: transparent; font-weight: bold; font-size: 11px;")
        return label

    @staticmethod
    def _note(text: str) -> QLabel:
        note = QLabel(text)
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {PURPLE_DARK}; background: transparent; font-size: 11px; font-style: italic;")
        return note

    def load_policy(self, policy: ISWLRPUPolicy) -> None:
        self._policy = policy
        self.end_age.setValue(0)
        self.end_age.setMaximum(policy.maturity_age)
        self.loan_note.setText(
            f"Loan: {money(policy.loan_balance)} on the record - the illustration is refused (see Policy)."
            if policy.current_loans else "Loans: no current loan on the record.")

    def read_inputs(self) -> ISWLRPUInputs:
        if self._policy is None:
            raise ISWLRPUInputError("Load an ISWL reduced paid-up policy first.")
        end_age = self.end_age.value() or None
        if end_age is not None and end_age <= self._policy.issue_age:
            raise ISWLRPUInputError(f"Illustrate to age must be after the issue age ({self._policy.issue_age}).")
        return ISWLRPUInputs(end_age=end_age)


def _grid(parent) -> FilterTableView:
    grid = FilterTableView(parent)
    grid.set_search_visible(False)
    grid.apply_ledger_style()
    grid.set_sort_enabled(False)
    grid.set_full_row_selection(True)
    return grid


class NSPWorkupPage(QWidget):
    """One anniversary's NSP rebuilt from the previous one, step by step."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: Optional[ISWLRPUResult] = None
        self._durations: List[int] = []
        self.workup: Optional[RollWorkup] = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        top = QHBoxLayout()
        caption = QLabel("Anniversary:")
        caption.setStyleSheet(f"color: {PURPLE_DARK}; background: transparent; font-size: 11px; font-weight: bold;")
        top.addWidget(caption)
        self.combo = QComboBox()
        self.combo.setStyleSheet(INPUT_COMBO_STYLE)
        self.combo.setMinimumWidth(280)
        self.combo.currentIndexChanged.connect(self._show)
        top.addWidget(self.combo)
        top.addStretch(1)
        layout.addLayout(top)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setStyleSheet(NOTICE_STYLE)
        self.note.setVisible(False)
        layout.addWidget(self.note)
        self.grid = _grid(self)
        self.grid.show_cell_highlights()
        layout.addWidget(self.grid, 1)

    def clear(self) -> None:
        self._result, self._durations, self.workup = None, [], None
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.blockSignals(False)
        self.grid.set_dataframe(pd.DataFrame())
        self.note.setVisible(False)

    def set_result(self, result: ISWLRPUResult) -> None:
        self._result = result
        self._durations = workup_durations(result.policy, result.schedule)
        by_duration = {v.duration: v for v in result.schedule}
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItems([f"{by_duration[d].anniversary:%m/%d/%Y}   duration {d}  age {by_duration[d].age}"
                             f"  ({by_duration[d].source})" for d in self._durations])
        self.combo.setCurrentIndex(0 if self._durations else -1)
        self.combo.blockSignals(False)
        self._show(0)

    def _show(self, index: int) -> None:
        if self._result is None or not 0 <= index < len(self._durations):
            return
        try:
            workup = roll_workup(self._result.policy, self._result.schedule, self._durations[index])
        except (NSPError, ValueError) as exc:
            self.workup = None
            self.grid.set_dataframe(pd.DataFrame())
            self.note.setText(f"The workup could not be calculated: {exc}")
            self.note.setVisible(True)
            return
        self.workup = workup
        self.note.setVisible(not workup.matches)
        self.note.setText("" if workup.matches else "The rebuilt value differs from the record or the schedule.")
        frame = self.frame()
        self.grid.set_dataframe(frame, limit_rows=False)
        self.grid.model._left_align_columns = {STEP_COLUMNS.index(c) for c in LEFT_ALIGNED_STEP_COLUMNS}
        self.grid.set_numeric_formatting(default_decimals=0)
        self.grid.set_highlighted_cells({
            (row, "Check"): QColor(MATCH_BG if text.startswith("Match") else DIFFER_BG)
            for row, text in enumerate(frame["Check"]) if text})
        self.grid.autofit_columns_to_data(max_width=560)

    def frame(self) -> pd.DataFrame:
        if self.workup is None:
            return pd.DataFrame(columns=STEP_COLUMNS)
        rows = [[n, s.item, s.formula, s.value, s.check] for n, s in enumerate(self.workup.steps, start=1)]
        return pd.DataFrame(rows, columns=STEP_COLUMNS)


class ISWLRPUValuesTab(QWidget):
    """Monthly and annual values, the NSP schedule and the NSP workup."""

    PAGES = ("Annual Values", "Monthly Values", "NSP Schedule", "NSP Workup")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: Optional[ISWLRPUResult] = None
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        self.caption = QLabel("Run Values to see the values.")
        self.caption.setStyleSheet(f"color: {PURPLE_DARK}; font-weight: bold; background: transparent;")
        layout.addWidget(self.caption)
        self.notes_label = QLabel("")
        self.notes_label.setWordWrap(True)
        self.notes_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.notes_label.setStyleSheet(NOTICE_STYLE)
        self.notes_label.setVisible(False)
        layout.addWidget(self.notes_label)
        body = QSplitter(Qt.Orientation.Horizontal, self)
        self.navigator = QListWidget(body)
        self.navigator.setStyleSheet(
            "QListWidget { background: white; border: 1px solid #B79CDE; font-size: 11px; }"
            "QListWidget::item { height: 18px; }"
            "QListWidget::item:selected { background: #E8DDF8; color: #2A1458; }")
        self.navigator.addItems(list(self.PAGES))
        self.stack = QStackedWidget(body)
        self.grids: Dict[str, FilterTableView] = {}
        for title in self.PAGES[:3]:
            grid = _grid(self.stack)
            self.grids[title] = grid
            self.stack.addWidget(grid)
        self.workup_page = NSPWorkupPage(self.stack)
        self.stack.addWidget(self.workup_page)
        self.navigator.currentRowChanged.connect(lambda row: row >= 0 and self.stack.setCurrentIndex(row))
        body.addWidget(self.navigator)
        body.addWidget(self.stack)
        body.setStretchFactor(1, 1)
        body.setSizes([150, 900])
        layout.addWidget(body, 1)
        self.navigator.setCurrentRow(0)

    def clear(self, message: str = "Run Values to see the values.") -> None:
        self._result = None
        self.caption.setText(message)
        self.notes_label.setVisible(False)
        for grid in self.grids.values():
            grid.set_dataframe(pd.DataFrame())
        self.workup_page.clear()

    def set_result(self, result: ISWLRPUResult) -> None:
        self._result = result
        policy = result.policy
        self.caption.setText(f"{policy.policy_number} {policy.plancode} reduced paid-up - from "
                             f"{policy.valuation_date:%m/%d/%Y} ({len(result.months)} months)")
        lines = [f"WARNING: {w}" for w in result.warnings] + result.notes
        self.notes_label.setText("\n".join(lines))
        self.notes_label.setVisible(bool(lines))
        frames = {"Annual Values": iswl_rpu_ledger_frame(result), "Monthly Values": self.month_frame(),
                  "NSP Schedule": self.schedule_frame()}
        for title, frame in frames.items():
            grid = self.grids[title]
            grid.set_dataframe(frame, limit_rows=False)
            grid.set_numeric_formatting(default_decimals=2, column_decimals={
                "Year": 0, "Month": 0, "Age": 0, "Duration": 0, "Carried NSP": 6})
            grid.autofit_columns_to_data(max_width=420)
        self.workup_page.set_result(result)

    def month_frame(self) -> pd.DataFrame:
        months = self._result.months if self._result else []
        rows = [{header: _cell(attr, getattr(m, attr)) for attr, header in MONTH_COLUMNS} for m in months]
        return pd.DataFrame(rows, columns=[header for _attr, header in MONTH_COLUMNS])

    def schedule_frame(self) -> pd.DataFrame:
        rows = [[v.duration, v.anniversary.strftime("%m/%d/%Y"), v.age, v.column or v.source, v.carry, v.per_unit,
                 v.comparison, v.difference] for v in (self._result.schedule if self._result else [])]
        return pd.DataFrame(rows, columns=SCHEDULE_COLUMNS)


class ISWLRPUWorkspace(QWidget):
    """The ISWL reduced paid-up page RERUN shows in place of its UL tabs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.basis: Optional[ISWLRPUBasis] = None
        self.result: Optional[ISWLRPUResult] = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget(self)
        self.tabs.setStyleSheet(TAB_WIDGET_STYLE)
        self.policy_view = ISWLRPUPolicyView()
        self.inputs_tab = ISWLRPUInputsTab()
        self.values_tab = ISWLRPUValuesTab()
        self.report_view = IllustrationPagesView(iswl_rpu_report_pages, iswl_rpu_ledger_frame, "ISWL RPU Ledger")
        self.checks_view = InforceChecksView()
        self.tabs.addTab(self.policy_view, "Policy")
        self.tabs.addTab(self.inputs_tab, "Illustration Inputs")
        self.tabs.addTab(self.values_tab, "Values")
        self.tabs.addTab(self.report_view, "Report")
        self.tabs.addTab(self.checks_view, "In-force Check")
        layout.addWidget(self.tabs)

    def load(self, basis: ISWLRPUBasis) -> None:
        """Show a freshly loaded ISWL RPU policy with default inputs."""
        self.basis = basis
        self.result = None
        self.policy_view.load(basis)
        self.inputs_tab.load_policy(basis.policy)
        self.values_tab.clear()
        self.report_view.clear()
        try:
            checks, error = basis.checks(), ""
        except Exception as exc:  # the check page reports; loading still succeeds
            logger.exception("ISWL RPU in-force checks failed")
            checks, error = [], f"The checks could not run: {exc}"
        self.checks_view.load(checks, error)
        notice = rate_check_notice(checks, error)
        if basis.policy.run_block:
            notice = "\n".join(filter(None, ["Run Values is refused: " + basis.policy.run_block, notice]))
        self.policy_view.set_check_notice(notice)
        self.tabs.setCurrentWidget(self.policy_view)

    def run(self) -> ISWLRPUResult:
        """Project with the screen's inputs; raises ISWLRPUInputError or engine errors loudly."""
        if self.basis is None:
            raise ISWLRPUInputError("Load an ISWL reduced paid-up policy first.")
        if self.basis.policy.run_block:
            raise ISWLRPUInputError(self.basis.policy.run_block)
        result = self.basis.run(self.inputs_tab.read_inputs())
        self.result = result
        self.values_tab.set_result(result)
        self.report_view.set_result(result)
        self.tabs.setCurrentWidget(self.report_view)
        return result


__all__ = ["ISWLRPUInputError", "ISWLRPUWorkspace", "iswl_rpu_ledger_frame", "iswl_rpu_report_pages"]
