"""RERUN workspace for participating whole life (par WL) policies.

RERUN swaps its UL/ISWL tabs for this workspace when the loaded policy is a
traditional participating whole life: a Policy page (the in-force snapshot), the par
WL Illustration Inputs, the monthly Values pages, the Report (the illustration pages,
printed to a landscape PDF like the UL report) and the
In-force Check page that reproduces CyberLife's current premium, cash values,
dividends and loan interest.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import List, Optional

import pandas as pd
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from suiteview.illustration.core.ledger_report import format_ledger_pages
from suiteview.illustration.core.parwl.report import build_parwl_report
from suiteview.illustration.core.parwl.service import ParWLBasis
from suiteview.illustration.models.parwl import (
    DIVIDEND_OPTION_LABELS,
    ROLE_BASE,
    ROLE_PUA_RIDER,
    ROLE_TERM_RIDER,
    ParWLBenefit,
    ParWLResult,
)
from suiteview.polview.ui.widgets import StyledInfoTableGroup

from .illustration_pages_view import IllustrationPagesView, InforceChecksView, ReportPages
from .parwl_inputs import ParWLInputError, ParWLInputsTab
from .parwl_values import ParWLValuesTab
from .policy_snapshot_widgets import BenefitButtonsGroup, CoverageTableGroup, money, short_date
from .styles import GROUP_STYLE, PURPLE_BG, TAB_WIDGET_STYLE

logger = logging.getLogger(__name__)

LEDGER_COLUMNS = (
    ("policy_year", "Year"), ("age", "Age"), ("end_date", "End of Year"),
    ("premium", "Premium Outlay"), ("rider_payments", "PUA Rider Payments"), ("new_loans", "New Loans"),
    ("loan_repayments", "Loan Repayments"), ("loan_interest_paid", "Loan Interest Paid"),
    ("guaranteed_cash_value", "Guar Cash Surrender Value"), ("guaranteed_death_benefit", "Guar Death Benefit"),
    ("dividend", "Annual Dividend"), ("dividend_cash", "Dividend Paid in Cash"), ("additions", "Paid-Up Additions"),
    ("additions_base", "Base Paid-Up Additions"), ("additions_rider", "Rider Paid-Up Additions"),
    ("additions_cv", "Additions Cash Value"), ("oyt_face", "One-Year Term"), ("deposits", "Dividends on Deposit"),
    ("loan_balance", "Loan Balance"), ("cash_value", "Total Cash Value"),
    ("surrender_value", "Non-Guar Cash Surrender Value"), ("death_benefit", "Non-Guar Death Benefit"),
)


def ledger_frame(result: ParWLResult) -> pd.DataFrame:
    """The annual illustration ledger as a DataFrame with display headers."""
    rows = []
    for year in result.years:
        record = {}
        for attr, header in LEDGER_COLUMNS:
            value = getattr(year, attr)
            record[header] = value.strftime("%m/%d/%Y") if attr == "end_date" else value
        rows.append(record)
    return pd.DataFrame(rows, columns=[header for _attr, header in LEDGER_COLUMNS])


def parwl_report_pages(result: ParWLResult, run_date: date) -> ReportPages:
    """The par WL illustration pages for the Report page."""
    report = build_parwl_report(result, run_date)
    pages = format_ledger_pages(report)
    guaranteed = "" if result.inputs.dividends else " Guaranteed values only (no dividends)."
    return ReportPages(pages, report.width, report.policy_number, report.plancode,
                       f"Par whole life illustration - {len(pages)} pages, landscape.{guaranteed}")


COVERAGE_COLUMNS = ["Phs", "Form", "Plancode", "Type", "IssueDate", "PayUpDate", "Mat Date", "Amount", "Units",
                    "IssAge", "Gender", "Class", "Tbl", "Prem/Unit", "Ann Prem", "Div Key", "NSP Basis"]
ROLE_LABELS = {ROLE_BASE: "Base", ROLE_PUA_RIDER: "PUA Rider", ROLE_TERM_RIDER: "Term Rider"}


def benefit_detail_rows(benefit: ParWLBenefit) -> List[tuple]:
    """The Benefit Detail card rows for a par WL supplemental benefit."""
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
        ("Amount:", money(benefit.units * benefit.value_per_unit)),
        ("Issue Age:", benefit.issue_age if benefit.issue_age is not None else ""),
        ("Rating:", f"{benefit.rate_factor:.0%}" if benefit.rate_factor != 1.0 else ""),
        ("Annual Rate:", f"{benefit.annual_premium_per_unit:,.2f}"),
        ("Annual Premium:", money(benefit.annual_premium)),
    ]


class ParWLPolicyView(QWidget):
    """The in-force snapshot the illustration starts from: policy facts, the coverages
    table (PolView's layout) and the supplemental benefits as RERUN's detail buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(8)
        self.info = StyledInfoTableGroup("Par Whole Life Policy", columns=3, show_table=False)
        self.info.setStyleSheet(GROUP_STYLE)
        for label, attr in (("Policy", "policy"), ("Plancode", "plancode"), ("Insured", "insured"),
                            ("Issue Date", "issue_date"), ("Issue Age", "issue_age"), ("Sex / Class", "sex_class"),
                            ("Status", "status"), ("Valuation Date", "valuation"), ("Last Anniversary", "anniversary"),
                            ("Paid To", "paid_to"), ("Mode / Form", "mode"), ("Billed Premium", "premium"),
                            ("Dividend Option", "option"), ("Secondary", "secondary"), ("Nonforfeiture", "nfo"),
                            ("Loan Type / Rate", "loan"), ("Deposit Rate", "deposit_rate"), ("Issue State", "state")):
            self.info.add_field(label, attr, 105, 170)
        layout.addWidget(self.info)

        self.coverages = CoverageTableGroup(COVERAGE_COLUMNS)
        layout.addWidget(self.coverages)
        self.benefit_group = BenefitButtonsGroup()
        layout.addWidget(self.benefit_group)
        layout.addStretch(1)

    def load(self, basis: ParWLBasis) -> None:
        p = basis.policy
        base = p.base
        self.info.set_value("policy", f"{p.company_code} {p.policy_number}")
        self.info.set_value("plancode", base.plancode)
        self.info.set_value("insured", p.insured_name)
        self.info.set_value("issue_date", f"{p.issue_date:%m/%d/%Y}")
        self.info.set_value("issue_age", str(base.issue_age))
        self.info.set_value("sex_class", f"{base.rate_sex} / {base.rate_class}")
        self.info.set_value("status", f"{p.premium_status} {p.premium_status_description}")
        self.info.set_value("valuation", f"{p.valuation_date:%m/%d/%Y}")
        self.info.set_value("anniversary", f"{p.last_anniversary:%m/%d/%Y}")
        self.info.set_value("paid_to", f"{p.paid_to_date:%m/%d/%Y}" if p.paid_to_date else "")
        self.info.set_value("mode", f"every {p.billing_frequency} months / form {p.bill_form}")
        self.info.set_value("premium", money(p.modal_premium) + (" (forced)" if p.forced_premium else ""))
        self.info.set_value("option", f"{p.dividend_option} {DIVIDEND_OPTION_LABELS.get(p.dividend_option, '')}")
        self.info.set_value("secondary", p.secondary_dividend_option or "(none)")
        self.info.set_value("nfo", p.nfo_option)
        self.info.set_value("loan", f"{p.loan_type_code} / {p.loan_rate:.3%}" if p.loan_rate is not None
                            else p.loan_type_code)
        self.info.set_value("deposit_rate", f"{p.deposit_rate:.3%}" if p.deposit_rate is not None else "not on record")
        self.info.set_value("state", p.issue_state)
        self._load_coverages(p)
        self._load_benefits(p)

    def _load_coverages(self, p) -> None:
        rows = []
        for c in p.coverages:
            rating = f"{c.table_rating}" if c.table_rating else ""
            if c.extra_premiums:
                rating = (rating + " + flat" if rating else "flat")
            rows.append([
                c.phase, c.form_number, c.plancode, ROLE_LABELS.get(c.role, c.role), short_date(c.issue_date),
                short_date(c.pay_up_date), short_date(c.maturity_date), money(c.face_amount), f"{c.units:,.3f}", c.issue_age,
                (c.sex_description or c.rate_sex)[:1], c.rate_class, rating, f"{c.annual_premium_per_unit:,.2f}",
                money(c.annual_premium), c.dividend_key,
                f"{c.nsp_table} {c.nsp_interest:.3%}" if c.nsp_interest is not None else c.nsp_table])
        self.coverages.load_rows(rows)

    def _load_benefits(self, p) -> None:
        self.benefit_group.load([
            (b.form_number or b.code or f"Benefit {b.phase}", b.description or b.code, benefit_detail_rows(b))
            for b in p.benefits])


class ParWLWorkspace(QWidget):
    """The par WL page RERUN shows in place of its UL tabs."""

    status_message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.basis: Optional[ParWLBasis] = None
        self.result: Optional[ParWLResult] = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget(self)
        self.tabs.setStyleSheet(TAB_WIDGET_STYLE)
        self.policy_view = ParWLPolicyView()
        self.inputs_tab = ParWLInputsTab()
        self.values_tab = ParWLValuesTab()
        self.report_view = IllustrationPagesView(parwl_report_pages, ledger_frame, "Par WL Ledger")
        self.checks_view = InforceChecksView()
        self.tabs.addTab(self.policy_view, "Policy")
        self.tabs.addTab(self.inputs_tab, "Illustration Inputs")
        self.tabs.addTab(self.values_tab, "Values")
        self.tabs.addTab(self.report_view, "Report")
        self.tabs.addTab(self.checks_view, "In-force Check")
        layout.addWidget(self.tabs)

    def load(self, basis: ParWLBasis) -> None:
        """Show a freshly loaded par WL policy with record-default inputs."""
        self.basis = basis
        self.result = None
        self.policy_view.load(basis)
        self.inputs_tab.load_policy(basis.policy)
        self.values_tab.clear()
        self.report_view.clear()
        try:
            checks, error = basis.checks(), ""
        except Exception as exc:  # the check page reports; loading still succeeds
            logger.exception("Par WL in-force checks failed")
            checks, error = [], f"The checks could not run: {exc}"
        self.checks_view.load(checks, error)
        self.tabs.setCurrentWidget(self.policy_view)

    def run(self) -> ParWLResult:
        """Project with the screen's inputs; raises ParWLInputError or engine errors loudly."""
        if self.basis is None:
            raise ParWLInputError("Load a par whole life policy first.")
        inputs = self.inputs_tab.read_inputs()
        result = self.basis.run(inputs)
        self.result = result
        self.values_tab.set_result(result)
        self.report_view.set_result(result)
        self.tabs.setCurrentWidget(self.report_view)
        return result


__all__ = ["ParWLWorkspace", "ledger_frame", "parwl_report_pages"]
