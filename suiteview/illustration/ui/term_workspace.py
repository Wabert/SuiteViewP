"""RERUN workspace for indeterminate premium term (IPT) policies.

RERUN swaps its UL/ISWL tabs for this workspace when the loaded policy is a traditional
term policy with indeterminate premiums: a **Policy** page (the in-force snapshot:
coverages in PolView's columns, benefits as detail buttons), **Illustration Inputs**
(the premium mode to illustrate, riders and benefits to drop, illustrate to age),
**Values** (every premium due date and each element of it, current and guaranteed),
the **Report** (the illustration pages, printed to a landscape PDF like the UL report)
and the **In-force Check** (CyberLife's stored rates, renewal rate and billed premium
against SuiteView's).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Dict, List, Optional

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
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

from suiteview.illustration.core.ledger_report import format_ledger_pages
from suiteview.illustration.core.term.report import build_term_report
from suiteview.illustration.core.term.service import TermBasis
from suiteview.illustration.models.term import ROLE_BASE, TermBenefit, TermInputs, TermPolicy, TermResult
from suiteview.polview.ui.widgets import StyledInfoTableGroup
from suiteview.ui.widgets.filter_table_view import FilterTableView

from .illustration_pages_view import IllustrationPagesView, InforceChecksView, ReportPages
from .policy_snapshot_widgets import BenefitButtonsGroup, CoverageTableGroup, money, short_date
from .styles import GROUP_STYLE, PURPLE_BG, PURPLE_DARK, TAB_WIDGET_STYLE, apply_input_checkbox_style

logger = logging.getLogger(__name__)

MODE_CHOICES = (("As billed", None), ("Annual", 12), ("Semi-annual", 6), ("Quarterly", 3), ("Monthly", 1))
MODE_NAMES = {12: "Annual", 6: "Semi-annual", 3: "Quarterly", 1: "Monthly"}
COVERAGE_COLUMNS = ["Phs", "Form", "Plancode", "Type", "IssueDate", "Level To", "Mat Date", "Amount", "Units",
                    "IssAge", "Gender", "Class", "Tbl", "Prem/Unit", "Next Rate", "Level Yrs", "Renews"]
LEDGER_COLUMNS = (
    ("policy_year", "Year"), ("age", "Age"), ("end_date", "End of Year"), ("period", "Premium Period"),
    ("current_premium", "Non-Guar Contract Premium"), ("guaranteed_premium", "Guar Contract Premium"),
    ("death_benefit", "Death Benefit"), ("rider_death_benefit", "Rider Coverage"),
)


class TermInputError(ValueError):
    """An illustration input cannot be used (explains which)."""


def term_ledger_frame(result: TermResult) -> pd.DataFrame:
    rows = []
    for year in result.years:
        record = {}
        for attr, header in LEDGER_COLUMNS:
            value = getattr(year, attr)
            record[header] = value.strftime("%m/%d/%Y") if attr == "end_date" else value
        rows.append(record)
    return pd.DataFrame(rows, columns=[header for _attr, header in LEDGER_COLUMNS])


def term_report_pages(result: TermResult, run_date: date) -> ReportPages:
    report = build_term_report(result, run_date)
    pages = format_ledger_pages(report)
    return ReportPages(pages, report.width, report.policy_number, report.plancode,
                       f"Indeterminate premium term illustration - {len(pages)} pages, landscape.")


def benefit_detail_rows(benefit: TermBenefit) -> List[tuple]:
    return [
        ("Code:", benefit.code),
        ("Phase:", benefit.phase),
        ("Description:", benefit.description),
        ("Form:", benefit.form_number),
        ("Issue Date:", short_date(benefit.issue_date)),
        ("Pay Up Date:", short_date(benefit.pay_up_date)),
        ("Cease Date:", short_date(benefit.cease_date)),
        ("Units:", f"{benefit.units:,.3f}"),
        ("VPU:", f"{benefit.value_per_unit:,.2f}"),
        ("Issue Age:", benefit.issue_age if benefit.issue_age is not None else ""),
        ("Rating:", f"{benefit.rate_factor:.0%}" if benefit.rate_factor != 1.0 else ""),
        ("Annual Rate:", f"{benefit.annual_premium_per_unit:,.2f}"),
        ("Annual Premium:", money(benefit.annual_premium)),
        ("Renews:", "Yes" if benefit.renews else "No"),
    ]


class TermPolicyView(QWidget):
    """The in-force snapshot: policy facts, coverages (PolView's columns) and benefit buttons."""

    FIELDS = (("Policy", "policy"), ("Plancode / Form", "plancode"), ("Insured", "insured"),
              ("Issue Date", "issue_date"), ("Issue Age", "issue_age"), ("Sex / Class", "sex_class"),
              ("Status", "status"), ("Valuation Date", "valuation"), ("Last Anniversary", "anniversary"),
              ("Paid To", "paid_to"), ("Mode / Form", "mode"), ("Billed Premium", "premium"),
              ("Face Amount", "face"), ("Premium Structure", "structure"), ("Next Premium Change", "next_change"),
              ("Maturity", "maturity"), ("Indeterminate", "indeterminate"), ("Issue State", "state"))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(8)
        self.info = StyledInfoTableGroup("Indeterminate Premium Term Policy", columns=3, show_table=False)
        self.info.setStyleSheet(GROUP_STYLE)
        for label, attr in self.FIELDS:
            self.info.add_field(label, attr, 120, 170)
        layout.addWidget(self.info)
        self.coverages = CoverageTableGroup(COVERAGE_COLUMNS)
        layout.addWidget(self.coverages)
        self.benefit_group = BenefitButtonsGroup()
        layout.addWidget(self.benefit_group)
        layout.addStretch(1)

    def load(self, basis: TermBasis) -> None:
        p = basis.policy
        base = p.base
        engine = basis.engine()
        structure = (f"level {base.initial_renewal_period} yrs, then every {base.renewal_period} yr"
                     if base.renewal_period else f"level {base.initial_renewal_period} yrs")
        values = {
            "policy": f"{p.company_code} {p.policy_number}",
            "plancode": f"{base.plancode} / {base.form_number}",
            "insured": p.insured_name,
            "issue_date": short_date(p.issue_date),
            "issue_age": str(base.issue_age),
            "sex_class": f"{base.rate_sex} / {base.rate_class}",
            "status": f"{p.premium_status} {p.premium_status_description}",
            "valuation": short_date(p.valuation_date),
            "anniversary": short_date(p.last_anniversary),
            "paid_to": short_date(p.paid_to_date),
            "mode": f"{MODE_NAMES.get(p.billing_frequency, p.billing_frequency)} / form {p.bill_form}",
            "premium": money(p.modal_premium) + (" (forced)" if p.forced_premium else ""),
            "face": money(base.face_amount),
            "structure": structure,
            "next_change": short_date(engine.next_premium_change(base)),
            "maturity": short_date(base.maturity_date),
            "indeterminate": "Yes" if p.indeterminate else "No",
            "state": p.issue_state,
        }
        for attr, value in values.items():
            self.info.set_value(attr, value)
        rows = []
        for c in p.coverages:
            level_to = short_date(engine.next_premium_change(c)) if c.renewal_period or c.initial_renewal_period else ""
            rating = f"{c.table_rating}" if c.table_rating else ""
            if any(e.percent is None and e.per_unit for e in c.extras):
                rating = (rating + " + flat" if rating else "flat")
            rows.append([
                c.phase, c.form_number, c.plancode, "Base" if c.role == ROLE_BASE else "Rider", short_date(c.issue_date),
                level_to, short_date(c.maturity_date), money(c.face_amount), f"{c.units:,.3f}", c.issue_age,
                (c.sex_description or c.rate_sex)[:1], c.rate_class, rating, f"{c.annual_premium_per_unit:,.2f}",
                f"{c.next_renewal_rate:,.2f}" if c.next_renewal_rate is not None else "",
                c.initial_renewal_period or "", {"C": "Renewable", "E": "Select"}.get(c.renewable_code, "")])
        self.coverages.load_rows(rows)
        self.benefit_group.load([
            (b.form_number or b.code or f"Benefit {b.phase}", b.description or b.code, benefit_detail_rows(b))
            for b in p.benefits])


class TermInputsTab(QWidget):
    """Illustration choices: premium mode, riders and benefits to drop, illustrate to age."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy: Optional[TermPolicy] = None
        self._rider_checks: Dict[int, QCheckBox] = {}
        self._benefit_checks: Dict[str, QCheckBox] = {}
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(8)
        premiums = QGroupBox("Premiums")
        premiums.setStyleSheet(GROUP_STYLE)
        form = QHBoxLayout(premiums)
        form.setContentsMargins(10, 18, 10, 8)
        form.addWidget(self._label("Illustrate premiums"))
        self.mode_combo = QComboBox()
        for label, frequency in MODE_CHOICES:
            self.mode_combo.addItem(label, frequency)
        self.mode_combo.setToolTip("The premium mode the illustration uses; guaranteed premiums use the same mode.")
        form.addWidget(self.mode_combo)
        form.addSpacing(18)
        form.addWidget(self._label("Illustrate to age"))
        self.end_age = QSpinBox()
        self.end_age.setRange(0, 121)
        self.end_age.setSpecialValueText("maturity")
        self.end_age.setToolTip("Stop the illustration at this attained age (maturity when blank).")
        form.addWidget(self.end_age)
        form.addStretch(1)
        layout.addWidget(premiums)
        self.riders_group = QGroupBox("Riders")
        self.riders_group.setStyleSheet(GROUP_STYLE)
        self.riders_layout = QVBoxLayout(self.riders_group)
        self.riders_layout.setContentsMargins(10, 18, 10, 8)
        layout.addWidget(self.riders_group)
        self.benefits_group = QGroupBox("Benefits with premiums")
        self.benefits_group.setStyleSheet(GROUP_STYLE)
        self.benefits_layout = QVBoxLayout(self.benefits_group)
        self.benefits_layout.setContentsMargins(10, 18, 10, 8)
        layout.addWidget(self.benefits_group)
        layout.addStretch(1)

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(f"color: {PURPLE_DARK}; background: transparent; font-weight: bold; font-size: 11px;")
        return label

    @staticmethod
    def _clear(box: QVBoxLayout) -> None:
        while box.count():
            widget = box.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()

    def _note(self, box: QVBoxLayout, text: str) -> None:
        note = QLabel(text)
        note.setStyleSheet(f"color: {PURPLE_DARK}; background: transparent; font-size: 11px; font-style: italic;")
        box.addWidget(note)

    def load_policy(self, policy: TermPolicy) -> None:
        self._policy = policy
        self.mode_combo.setCurrentIndex(0)
        self.mode_combo.setItemText(0, f"As billed ({MODE_NAMES.get(policy.billing_frequency, 'modal')})")
        self.end_age.setValue(0)
        self._clear(self.riders_layout)
        self._clear(self.benefits_layout)
        self._rider_checks, self._benefit_checks = {}, {}
        for rider in policy.riders:
            check = QCheckBox(f"Keep {rider.plancode} {rider.form_number} - {money(rider.face_amount)} "
                              f"to {short_date(rider.maturity_date)}")
            apply_input_checkbox_style(check)
            check.setChecked(True)
            self._rider_checks[rider.phase] = check
            self.riders_layout.addWidget(check)
        if not policy.riders:
            self._note(self.riders_layout, "No riders on this policy.")
        for benefit in policy.benefits:
            if not benefit.annual_premium_per_unit:
                continue
            check = QCheckBox(f"Keep {benefit.form_number or benefit.code} - {benefit.description}")
            apply_input_checkbox_style(check)
            check.setChecked(True)
            self._benefit_checks[benefit.code] = check
            self.benefits_layout.addWidget(check)
        if not self._benefit_checks:
            self._note(self.benefits_layout, "No benefits with premiums on this policy.")

    def read_inputs(self) -> TermInputs:
        if self._policy is None:
            raise TermInputError("Load an indeterminate premium term policy first.")
        base = self._policy.base
        end_age = self.end_age.value() or None
        if end_age is not None and end_age <= base.issue_age:
            raise TermInputError(f"Illustrate to age must be after the issue age ({base.issue_age}).")
        return TermInputs(
            billing_frequency=self.mode_combo.currentData(),
            drop_riders=[phase for phase, check in self._rider_checks.items() if not check.isChecked()],
            drop_benefits=[code for code, check in self._benefit_checks.items() if not check.isChecked()],
            end_age=end_age,
        )


PREMIUM_PAGE = (("when", "Date"), ("policy_year", "Year"), ("month_of_year", "Month"), ("attained_age", "Age"),
                ("period", "Period"), ("current_premium", "Non-Guar Premium"),
                ("guaranteed_premium", "Guar Premium"), ("death_benefit", "Death Benefit"),
                ("rider_death_benefit", "Rider Coverage"), ("notes", "Notes"))
DETAIL_COLUMNS = ["Date", "Year", "Age", "Element", "Kind", "Annual Rate", "Non-Guar Modal", "Guar Modal"]


class TermValuesTab(QWidget):
    """Every month of the projection and each element of every premium due."""

    PAGES = ("Premiums", "Premium Detail")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: Optional[TermResult] = None
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        top = QHBoxLayout()
        self.caption = QLabel("Run Values to see the premiums.")
        self.caption.setStyleSheet(f"color: {PURPLE_DARK}; font-weight: bold; background: transparent;")
        top.addWidget(self.caption, 1)
        self.due_only = QCheckBox("Premium due dates only")
        apply_input_checkbox_style(self.due_only)
        self.due_only.setChecked(True)
        self.due_only.toggled.connect(self._refresh)
        top.addWidget(self.due_only)
        layout.addLayout(top)
        self.notes_label = QLabel("")
        self.notes_label.setWordWrap(True)
        self.notes_label.setStyleSheet(
            "background: #FFF6D6; color: #3A2A00; border: 1px solid #D9B44A; border-radius: 4px;"
            " padding: 3px 6px; font-size: 11px;")
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
        for title in self.PAGES:
            grid = FilterTableView(self.stack)
            grid.set_search_visible(False)
            grid.apply_ledger_style()
            grid.set_sort_enabled(False)
            grid.set_full_row_selection(True)
            self.grids[title] = grid
            self.stack.addWidget(grid)
        self.navigator.currentRowChanged.connect(lambda row: row >= 0 and self.stack.setCurrentIndex(row))
        body.addWidget(self.navigator)
        body.addWidget(self.stack)
        body.setStretchFactor(1, 1)
        body.setSizes([150, 900])
        layout.addWidget(body, 1)
        self.navigator.setCurrentRow(0)

    def clear(self, message: str = "Run Values to see the premiums.") -> None:
        self._result = None
        self.caption.setText(message)
        self.notes_label.setVisible(False)
        for grid in self.grids.values():
            grid.set_dataframe(pd.DataFrame())

    def set_result(self, result: TermResult) -> None:
        self._result = result
        policy = result.policy
        self.caption.setText(f"{policy.policy_number} {policy.base.plancode} - from "
                             f"{policy.valuation_date:%m/%d/%Y} ({len(result.months)} months)")
        self.notes_label.setText("\n".join(result.notes))
        self.notes_label.setVisible(bool(result.notes))
        self._refresh()

    def premium_frame(self) -> pd.DataFrame:
        months = self._result.months if self._result else []
        if self.due_only.isChecked():
            months = [m for m in months if m.premium_due]
        rows = [{header: (getattr(m, attr).strftime("%m/%d/%Y") if attr == "when" else getattr(m, attr))
                 for attr, header in PREMIUM_PAGE} for m in months]
        return pd.DataFrame(rows, columns=[header for _attr, header in PREMIUM_PAGE])

    def detail_frame(self) -> pd.DataFrame:
        rows = []
        for m in (self._result.months if self._result else []):
            for part in m.parts:
                rows.append([m.when.strftime("%m/%d/%Y"), m.policy_year, m.attained_age, part.label, part.kind,
                             part.rate, part.current, part.guaranteed])
        return pd.DataFrame(rows, columns=DETAIL_COLUMNS)

    def _refresh(self, *_args) -> None:
        for title, frame in (("Premiums", self.premium_frame()), ("Premium Detail", self.detail_frame())):
            grid = self.grids[title]
            grid.set_dataframe(frame, limit_rows=False)
            grid.set_numeric_formatting(default_decimals=2, column_decimals={"Year": 0, "Month": 0, "Age": 0})
            grid.autofit_columns_to_data()


class TermWorkspace(QWidget):
    """The indeterminate premium term page RERUN shows in place of its UL tabs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.basis: Optional[TermBasis] = None
        self.result: Optional[TermResult] = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget(self)
        self.tabs.setStyleSheet(TAB_WIDGET_STYLE)
        self.policy_view = TermPolicyView()
        self.inputs_tab = TermInputsTab()
        self.values_tab = TermValuesTab()
        self.report_view = IllustrationPagesView(term_report_pages, term_ledger_frame, "Term Ledger")
        self.checks_view = InforceChecksView()
        self.tabs.addTab(self.policy_view, "Policy")
        self.tabs.addTab(self.inputs_tab, "Illustration Inputs")
        self.tabs.addTab(self.values_tab, "Values")
        self.tabs.addTab(self.report_view, "Report")
        self.tabs.addTab(self.checks_view, "In-force Check")
        layout.addWidget(self.tabs)

    def load(self, basis: TermBasis) -> None:
        """Show a freshly loaded term policy with record-default inputs."""
        self.basis = basis
        self.result = None
        self.policy_view.load(basis)
        self.inputs_tab.load_policy(basis.policy)
        self.values_tab.clear()
        self.report_view.clear()
        try:
            checks, error = basis.checks(), ""
        except Exception as exc:  # the check page reports; loading still succeeds
            logger.exception("Term in-force checks failed")
            checks, error = [], f"The checks could not run: {exc}"
        self.checks_view.load(checks, error)
        self.tabs.setCurrentWidget(self.policy_view)

    def run(self) -> TermResult:
        """Project with the screen's inputs; raises TermInputError or engine errors loudly."""
        if self.basis is None:
            raise TermInputError("Load an indeterminate premium term policy first.")
        result = self.basis.run(self.inputs_tab.read_inputs())
        self.result = result
        self.values_tab.set_result(result)
        self.report_view.set_result(result)
        self.tabs.setCurrentWidget(self.report_view)
        return result


__all__ = ["TermInputError", "TermWorkspace", "term_ledger_frame", "term_report_pages"]
