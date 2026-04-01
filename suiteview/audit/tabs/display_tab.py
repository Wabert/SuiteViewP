"""
Display tab — faithful replica of VBA frmAudit Display tab.

All checkboxes selecting additional data items to display in the results.
Organized in 5 columns matching the VBA layout.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QFrame,
)
from PyQt6.QtGui import QFont
from ._styles import make_checkbox

_FONT = QFont("Segoe UI", 9)
_V_SPACING = 2


def _cb(text: str) -> QCheckBox:
    return make_checkbox(text)


def _spacer() -> QWidget:
    """Small vertical gap."""
    w = QWidget()
    w.setFixedHeight(8)
    return w


def _vsep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.VLine)
    f.setFrameShadow(QFrame.Shadow.Sunken)
    return f


class DisplayTab(QWidget):
    """Display tab — checkboxes for additional result columns."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 4)
        root.setSpacing(4)

        # Header
        hdr = QLabel("Select additional data items to display in the results")
        hdr.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        hdr.setStyleSheet("color: #333;")
        root.addWidget(hdr)

        # Columns
        cols = QHBoxLayout()
        cols.setSpacing(8)

        # ── Column 1 ──────────────────────────────────────────────
        c1 = QVBoxLayout()
        c1.setSpacing(_V_SPACING)
        self.chk_paid_to_date = _cb("Paid To Date (01)")
        self.chk_bill_to_date = _cb("Bill To Date (01)")
        self.chk_gpe_date = _cb("GPE Date (51 or 66)")
        self.chk_current_duration = _cb("Current Duration (Calc)")
        self.chk_current_attained_age = _cb("Current Attained Age(Calc)")
        for w in (self.chk_paid_to_date, self.chk_bill_to_date,
                  self.chk_gpe_date, self.chk_current_duration,
                  self.chk_current_attained_age):
            c1.addWidget(w)
        c1.addWidget(_spacer())

        self.chk_last_acct_date = _cb("Last Accounting Date (01)")
        self.chk_last_fin_date = _cb("Last Financial Date (01)")
        self.chk_next_change_cov1 = _cb("Next Change - cov1  (02)")
        for w in (self.chk_last_acct_date, self.chk_last_fin_date,
                  self.chk_next_change_cov1):
            c1.addWidget(w)
        c1.addWidget(_spacer())

        self.chk_application_date = _cb("Application Date")
        self.chk_next_sched_notif = _cb("Next Scheduled Notification Date")
        self.chk_next_year_end = _cb("Next Year-End Date")
        self.chk_next_sched_stmt = _cb("Next Scheduled Statement Date")
        self.chk_next_sched_stmt2 = _cb("Next Scheduled Statement Date")
        self.chk_termination_date = _cb("Termination Date (69)")
        for w in (self.chk_application_date, self.chk_next_sched_notif,
                  self.chk_next_year_end, self.chk_next_sched_stmt,
                  self.chk_next_sched_stmt2, self.chk_termination_date):
            c1.addWidget(w)
        c1.addWidget(_spacer())

        self.chk_converted_pol = _cb("Converted policy info (52)")
        self.chk_conv_credit = _cb("Conversion Credit Info (52 - PDF)")
        self.chk_init_term_period = _cb("Initial Term Period (02)")
        self.chk_disp_conv_period = _cb("Display if within Conversion Period (Calc)")
        self.chk_disp_conv_period_calc = _cb("Display Conversion Period (Calc)")
        for w in (self.chk_converted_pol, self.chk_conv_credit,
                  self.chk_init_term_period, self.chk_disp_conv_period,
                  self.chk_disp_conv_period_calc):
            c1.addWidget(w)

        c1.addStretch()
        cols.addLayout(c1)
        cols.addWidget(_vsep())

        # ── Column 2 ──────────────────────────────────────────────
        c2 = QVBoxLayout()
        c2.setSpacing(_V_SPACING)
        self.chk_tch_pol_id = _cb("TCH_POL_ID")
        self.chk_mod_indicator = _cb("MOD Indicator")
        c2.addWidget(self.chk_tch_pol_id)
        c2.addWidget(self.chk_mod_indicator)
        c2.addWidget(_spacer())

        self.chk_prod_line_code = _cb("Product Line Code (02)")
        self.chk_billable_prem = _cb("Billable Premium (01)")
        self.chk_billable_mode = _cb("Billable Mode (01)")
        self.chk_billable_form = _cb("Billable Form (01)")
        self.chk_billable_ctrl_num = _cb("Billable Control Number (33)")
        self.chk_slr_bill_form = _cb("SLR Bill Form (20)")
        self.chk_short_pay = _cb("Short pay fields (52 and 58)")
        self.chk_accum_withdrawals = _cb("Accum Withdrawals (60)")
        self.chk_premiums_ptd = _cb("Premiums PTD (60)")
        self.chk_premiums_paid_ytd = _cb("Premiums Paid YTD (63)")
        self.chk_policy_debt = _cb("Policy Debt (77)")
        self.chk_cost_basis = _cb("Cost Basis (60)")
        for w in (self.chk_prod_line_code, self.chk_billable_prem,
                  self.chk_billable_mode, self.chk_billable_form,
                  self.chk_billable_ctrl_num, self.chk_slr_bill_form,
                  self.chk_short_pay, self.chk_accum_withdrawals,
                  self.chk_premiums_ptd, self.chk_premiums_paid_ytd,
                  self.chk_policy_debt, self.chk_cost_basis):
            c2.addWidget(w)
        c2.addWidget(_spacer())

        self.chk_prem_calc_rules = _cb("Prem Calc Rules (01)")
        c2.addWidget(self.chk_prem_calc_rules)

        c2.addStretch()
        cols.addLayout(c2)
        cols.addWidget(_vsep())

        # ── Column 3 ──────────────────────────────────────────────
        c3 = QVBoxLayout()
        c3.setSpacing(_V_SPACING)
        self.chk_disp_substandard = _cb("Display Substandard (03)")
        self.chk_disp_sex_rateclass = _cb("Display Sex and Rateclass (67)")
        self.chk_disp_sex_02 = _cb("Display Sex(02)")
        self.chk_subseries_code = _cb("Subseries Code(02)")
        self.chk_disp_mkt_org = _cb("Display Market Org Code (01)")
        self.chk_reinsured_code = _cb("Reinsured Code  (01)")
        self.chk_last_entry_code = _cb("Last Entry Code  (01)")
        self.chk_orig_entry_code = _cb("Original Entry Code  (01)")
        self.chk_mec_status = _cb("MEC Status (01)")
        self.chk_insured1_info = _cb("Insured1 Info (89)")
        self.chk_replacement_pol = _cb("Replacement Policy (52-R)")
        for w in (self.chk_disp_substandard, self.chk_disp_sex_rateclass,
                  self.chk_disp_sex_02, self.chk_subseries_code,
                  self.chk_disp_mkt_org, self.chk_reinsured_code,
                  self.chk_last_entry_code, self.chk_orig_entry_code,
                  self.chk_mec_status, self.chk_insured1_info,
                  self.chk_replacement_pol):
            c3.addWidget(w)

        c3.addStretch()
        cols.addLayout(c3)
        cols.addWidget(_vsep())

        # ── Column 4 ──────────────────────────────────────────────
        c4 = QVBoxLayout()
        c4.setSpacing(_V_SPACING)
        self.chk_commission_target = _cb("Commission Target (58)")
        self.chk_monthly_min_target = _cb("Monthly Min Target (58)")
        self.chk_accum_monthly_min = _cb("Accum Monthly Min Target (58)")
        self.chk_accum_glp = _cb("Accum GLP (58)")
        self.chk_nsp = _cb("NSP (58)")
        self.chk_gsp = _cb("GSP (67)")
        self.chk_glp = _cb("GLP (67)")
        self.chk_tamra = _cb("TAMRA (59)")
        for w in (self.chk_commission_target, self.chk_monthly_min_target,
                  self.chk_accum_monthly_min, self.chk_accum_glp,
                  self.chk_nsp, self.chk_gsp, self.chk_glp, self.chk_tamra):
            c4.addWidget(w)
        c4.addWidget(_spacer())

        self.chk_orig_face_rpu = _cb("Original face for RPU policies (68)")
        self.chk_accum_value = _cb("Accumulation Value (75)")
        self.chk_trad_cv_cov1 = _cb("Trad Cash Value Cov1 (02)")
        self.chk_account_value = _cb("Account Value  (02 & 75)")
        self.chk_shadow_av = _cb("Shadow AV (58)")
        self.chk_disp_orig_curr_sa = _cb("Display original and current specified amount (02)")
        self.chk_death_benefit_opt = _cb("Death Benefit Option (66)")
        self.chk_def_life_ins = _cb("Definition of Life Insurance (66)")
        for w in (self.chk_orig_face_rpu, self.chk_accum_value,
                  self.chk_trad_cv_cov1, self.chk_account_value,
                  self.chk_shadow_av, self.chk_disp_orig_curr_sa,
                  self.chk_death_benefit_opt, self.chk_def_life_ins):
            c4.addWidget(w)
        c4.addWidget(_spacer())

        self.chk_cirf_key = _cb("CIRF Key (55)")
        c4.addWidget(self.chk_cirf_key)

        c4.addStretch()
        cols.addLayout(c4)
        cols.addWidget(_vsep())

        # ── Column 5 ──────────────────────────────────────────────
        c5 = QVBoxLayout()
        c5.setSpacing(_V_SPACING)
        self.chk_trad_overloan = _cb("Trad Overloan Indicator  (01)")
        c5.addWidget(self.chk_trad_overloan)
        c5.addWidget(_spacer())
        self.Checkbox_DisplayTradRates = _cb(
            "Trad rates - cov 1\n"
            "   Poll Fee (01), Modal Factors (01),\n"
            "   Prem Rate (02), Premium (01)"
        )
        c5.addWidget(self.Checkbox_DisplayTradRates)
        c5.addStretch()
        cols.addLayout(c5)

        root.addLayout(cols, 1)

    # ── Profile save/load ────────────────────────────────────────────
    def _all_checkboxes(self) -> list[tuple[str, QCheckBox]]:
        """Return (attr_name, widget) for every QCheckBox on this tab."""
        results = []
        for attr in dir(self):
            if attr.startswith("chk_") or attr.startswith("Checkbox_"):
                w = getattr(self, attr, None)
                if isinstance(w, QCheckBox):
                    results.append((attr, w))
        return sorted(results)

    def get_state(self) -> dict:
        return {name: cb.isChecked() for name, cb in self._all_checkboxes()}

    def set_state(self, state: dict):
        for name, cb in self._all_checkboxes():
            cb.setChecked(state.get(name, False))
