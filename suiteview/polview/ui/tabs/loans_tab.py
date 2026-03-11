"""
Loans tab – Displays loan detail for policies that have outstanding loans.

Based on VBA frmPolicyMasterTV PopulateTradLoanDetail / PopulateLoanDetail.

Layout (mirrors VBA):
  Left column:
    - Loan Summary group     (Total Policy Debt, Loan Type)
    - Fixed Loan (Regular)   (Principal, Accrued Interest, Impaired Crediting Rate, Loan Charge Rate)
    - Fixed Loan (Preferred) (same fields, hidden if no preferred loans)
    - Variable Loan          (Principal, Accrued Interest — IUL only)
  Right column:
    - Loan Detail table      (Eff Date, Pref, Fund, Phs, Principal, Accru Int, Chrg Rt, Credit Rt, Int Status)
"""

from decimal import Decimal
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame,
    QTableWidgetItem,
)
from PyQt6.QtCore import Qt

from ..formatting import format_currency, format_date, format_rate, US_DATE_FMT
from ..widgets import StyledInfoTableGroup, StyledTableGroup


class LoansTab(QWidget):
    """Tab displaying policy loan details — shown only when a policy has loans."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    # ── UI construction ──────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        # ── Left column: summary panels using StyledInfoTableGroup ───────
        left = QVBoxLayout()
        left.setSpacing(6)

        # Loan Summary group — Total Policy Debt + Loan Type
        self._summary_group = StyledInfoTableGroup(
            "Loan Summary", columns=1, show_table=False
        )
        self._summary_group.add_field("Total Policy Debt", "debt_value", 130, 100)
        self._summary_group.add_field("Loan Type", "loan_type_value", 130, 100)
        left.addWidget(self._summary_group)

        # Fixed Loan (Regular) group
        self._reg_group = StyledInfoTableGroup(
            "Fixed Loan (Regular)", columns=1, show_table=False
        )
        self._reg_group.add_field("Principal", "reg_principal", 140, 100)
        self._reg_group.add_field("Accrued Interest", "reg_accrued", 140, 100)
        self._reg_group.add_field("Impaired Crediting Rate", "reg_impaired", 140, 100)
        self._reg_group.add_field("Loan Charge Rate", "reg_charge", 140, 100)
        left.addWidget(self._reg_group)

        # Fixed Loan (Preferred) group
        self._pref_group = StyledInfoTableGroup(
            "Fixed Loan (Preferred)", columns=1, show_table=False
        )
        self._pref_group.add_field("Principal", "pref_principal", 140, 100)
        self._pref_group.add_field("Accrued Interest", "pref_accrued", 140, 100)
        self._pref_group.add_field("Impaired Crediting Rate", "pref_impaired", 140, 100)
        self._pref_group.add_field("Loan Charge Rate", "pref_charge", 140, 100)
        left.addWidget(self._pref_group)

        # Variable Loan group (IUL only)
        self._var_group = StyledInfoTableGroup(
            "Variable Loan", columns=1, show_table=False
        )
        self._var_group.add_field("Principal", "var_principal", 140, 100)
        self._var_group.add_field("Accrued Interest", "var_accrued", 140, 100)
        left.addWidget(self._var_group)

        left.addStretch()

        left_widget = QWidget()
        left_widget.setLayout(left)
        left_widget.setFixedWidth(310)
        content_layout.addWidget(left_widget)

        # ── Right column: loan detail table ──────────────────────────────
        self.loan_detail_group = StyledTableGroup("Loan Detail")
        self.loan_detail_group.table.setColumnCount(9)
        self.loan_detail_group.table.setHorizontalHeaderLabels([
            "Eff Date", "Pref", "Fund", "Phs",
            "Principal", "Accru Int", "Chrg Rt",
            "Credit Rt", "Int Status",
        ])
        content_layout.addWidget(self.loan_detail_group, 1)

        scroll.setWidget(content)
        root.addWidget(scroll)

    # ── public API ───────────────────────────────────────────────────────

    @staticmethod
    def has_loan_data(policy) -> bool:
        """Return True if the policy has any active loan rows."""
        if not policy:
            return False
        try:
            trad = policy.data_item_count("LH_CSH_VAL_LOAN")
            fund = policy.data_item_count("LH_FND_VAL_LOAN")
            return (trad > 0) or (fund > 0)
        except Exception:
            return False

    # ── data loading ─────────────────────────────────────────────────────

    def load_data_from_policy(self, policy):
        """Load loan information from a PolicyInformation object."""
        if not policy:
            return

        try:
            is_advanced = policy.is_advanced_product
            product_type = getattr(policy, "product_type", "")
            status_code = getattr(policy, "status_code", "")

            # Determine whether to use trad or fund loans
            # VBA rule: advanced products use fund loans except ISWL in RPU (status 45)
            use_trad = (
                not is_advanced
                or (product_type == "ISWL" and status_code == "45")
            )

            if use_trad:
                self._load_trad_loans(policy)
            else:
                self._load_fund_loans(policy)

        except Exception:
            import traceback, sys
            print(f"[LoansTab] Error loading data", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    # ── private loaders ──────────────────────────────────────────────────

    def _load_trad_loans(self, policy):
        """Populate for traditional (cash-value) loans — LH_CSH_VAL_LOAN."""
        lr = policy.loan_records
        table = self.loan_detail_group.table
        table.setRowCount(0)

        rows = policy.fetch_table("LH_CSH_VAL_LOAN")
        if not rows:
            return

        # Build detail table
        detail_rows = []
        for row in rows:
            mv_date = row.get("MVRY_DT")
            pref = str(row.get("PRF_LN_IND", "0") or "0")
            principal = row.get("LN_PRI_AMT", 0) or 0
            accrued = row.get("POL_LN_ITS_AMT", 0) or 0
            charge_rt = row.get("LN_CRG_ITS_RT")
            int_status = str(row.get("LN_ITS_AMT_TYP_CD", "") or "")
            detail_rows.append({
                "date": mv_date,
                "pref": pref,
                "fund": "",
                "phs": "",
                "principal": principal,
                "accrued": accrued,
                "charge_rt": charge_rt,
                "credit_rt": "",
                "int_status": self._translate_int_status(int_status),
            })

        self._fill_detail_table(detail_rows)

        # Summary panels
        reg_pri = lr.total_regular_loan_principal
        reg_acc = lr.total_regular_loan_accrued
        pref_pri = lr.total_preferred_loan_principal
        pref_acc = lr.total_preferred_loan_accrued

        self._reg_group.set_value("reg_principal", format_currency(reg_pri))
        self._reg_group.set_value("reg_accrued", format_currency(reg_acc))

        # Loan type from base policy
        ln_typ = str(policy.data_item("LH_BAS_POL", "LN_TYP_CD") or "")
        from suiteview.polview.models.cl_polrec.policy_translations import (
            translate_loan_type_code,
        )
        self._summary_group.set_value("loan_type_value", translate_loan_type_code(ln_typ))

        # For trad: charge rate from LH_BAS_POL
        is_variable = ln_typ in ("6", "7")
        if not is_variable:
            chrg = policy.data_item("LH_BAS_POL", "LN_PLN_ITS_RT")
            self._reg_group.set_value("reg_charge", f"{float(chrg):.2f}%" if chrg else "")
        else:
            self._reg_group.set_value("reg_charge", "")

        # No impaired crediting for trad
        self._reg_group.set_value("reg_impaired", "")

        # Preferred group visibility
        if pref_pri > 0:
            self._pref_group.setVisible(True)
            self._pref_group.set_value("pref_principal", format_currency(pref_pri))
            self._pref_group.set_value("pref_accrued", format_currency(pref_acc))
            self._pref_group.set_value("pref_charge", "")
            self._pref_group.set_value("pref_impaired", "")
        else:
            self._pref_group.setVisible(False)

        # Variable group — hidden for trad
        self._var_group.setVisible(False)

        # Policy debt
        debt = lr.policy_debt
        self._summary_group.set_value("debt_value", format_currency(debt))

    def _load_fund_loans(self, policy):
        """Populate for fund-based (UL/IUL/VUL) loans — LH_FND_VAL_LOAN."""
        lr = policy.loan_records
        table = self.loan_detail_group.table
        table.setRowCount(0)

        rows = policy.fetch_table("LH_FND_VAL_LOAN")
        if not rows:
            return

        detail_rows = []
        for row in rows:
            mv_date = row.get("MVRY_DT")
            pref = str(row.get("PRF_LN_IND", "0") or "0")
            fund = str(row.get("FUND_ID", "") or "")
            phs = str(row.get("COV_PHA_NBR", "") or "")
            principal = row.get("LN_PRI_AMT", 0) or 0
            accrued = row.get("POL_LN_ITS_AMT", 0) or 0
            charge_rt = row.get("LN_CRG_ITS_RT")
            credit_rt = row.get("LN_CRE_ITS_RT")
            int_status = str(row.get("LN_ITS_AMT_TYP_CD", "") or "")
            detail_rows.append({
                "date": mv_date,
                "pref": pref,
                "fund": fund,
                "phs": phs,
                "principal": principal,
                "accrued": accrued,
                "charge_rt": charge_rt,
                "credit_rt": credit_rt,
                "int_status": self._translate_int_status(int_status),
            })

        self._fill_detail_table(detail_rows)

        # ── Summary panels ──
        reg_pri = lr.total_regular_loan_principal
        reg_acc = lr.total_regular_loan_accrued
        pref_pri = lr.total_preferred_loan_principal
        pref_acc = lr.total_preferred_loan_accrued
        var_pri = lr.total_variable_loan_principal
        var_acc = lr.total_variable_loan_accrued

        # Regular
        self._reg_group.set_value("reg_principal", format_currency(reg_pri))
        self._reg_group.set_value("reg_accrued", format_currency(reg_acc))

        # Impaired crediting rate & charge rate from LH_NON_TRD_POL
        reg_credit = policy.data_item("LH_NON_TRD_POL", "LN_CRE_ITS_RT")
        reg_charge = policy.data_item("LH_NON_TRD_POL", "LN_ITS_CRG_RT")
        self._reg_group.set_value("reg_impaired", f"{float(reg_credit):.2f}%" if reg_credit else "")
        self._reg_group.set_value("reg_charge", f"{float(reg_charge):.2f}%" if reg_charge else "")

        # Loan type
        ln_typ = str(policy.data_item("LH_BAS_POL", "LN_TYP_CD") or "")
        from suiteview.polview.models.cl_polrec.policy_translations import (
            translate_loan_type_code,
        )
        self._summary_group.set_value("loan_type_value", translate_loan_type_code(ln_typ))

        # Preferred
        if lr.preferred_loans_available and pref_pri > 0:
            self._pref_group.setVisible(True)
            self._pref_group.set_value("pref_principal", format_currency(pref_pri))
            self._pref_group.set_value("pref_accrued", format_currency(pref_acc))
            pref_credit = policy.data_item("LH_NON_TRD_POL", "PRF_LN_ITS_CRE_RT")
            pref_charge = policy.data_item("LH_NON_TRD_POL", "PRF_LN_ITS_CRG_RT")
            self._pref_group.set_value("pref_impaired", f"{float(pref_credit):.2f}%" if pref_credit else "")
            self._pref_group.set_value("pref_charge", f"{float(pref_charge):.2f}%" if pref_charge else "")
        else:
            self._pref_group.setVisible(False)

        # Variable (IUL only)
        product_type = getattr(policy, "product_type", "")
        if product_type == "IUL" and (var_pri > 0 or var_acc > 0):
            self._var_group.setVisible(True)
            self._var_group.set_value("var_principal", format_currency(var_pri))
            self._var_group.set_value("var_accrued", format_currency(var_acc))
        else:
            self._var_group.setVisible(False)

        # Policy debt
        debt = lr.policy_debt
        self._summary_group.set_value("debt_value", format_currency(debt))

    # ── shared helpers ───────────────────────────────────────────────────

    def _fill_detail_table(self, detail_rows: list):
        """Populate the detail table from a list of row dicts."""
        table = self.loan_detail_group.table
        table.setRowCount(len(detail_rows))

        for idx, d in enumerate(detail_rows):
            table.setItem(idx, 0, QTableWidgetItem(format_date(d["date"], US_DATE_FMT)))
            table.setItem(idx, 1, QTableWidgetItem(d["pref"]))
            table.setItem(idx, 2, QTableWidgetItem(d["fund"]))
            table.setItem(idx, 3, QTableWidgetItem(str(d["phs"])))

            # Principal — right-aligned
            pri_item = QTableWidgetItem(format_currency(d["principal"]))
            pri_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(idx, 4, pri_item)

            # Accrued Interest — right-aligned
            acc_item = QTableWidgetItem(format_currency(d["accrued"]))
            acc_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(idx, 5, acc_item)

            # Charge Rate
            cr = d["charge_rt"]
            cr_text = f"{float(cr):.2f}%" if cr else ""
            table.setItem(idx, 6, QTableWidgetItem(cr_text))

            # Credit Rate
            cred = d.get("credit_rt")
            cred_text = f"{float(cred):.2f}%" if cred else ""
            table.setItem(idx, 7, QTableWidgetItem(cred_text))

            # Interest Status
            table.setItem(idx, 8, QTableWidgetItem(d.get("int_status", "")))

        table.autoFitAllColumns()

    @staticmethod
    def _translate_int_status(code: str) -> str:
        """Translate loan interest status code to text."""
        try:
            from suiteview.polview.models.cl_polrec.policy_translations import (
                translate_loan_interest_status_code,
            )
            return translate_loan_interest_status_code(code)
        except Exception:
            return code
