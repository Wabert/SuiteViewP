"""
CL_POLREC_20_77 — Loan Records (Records 20, 77)
==================================================

DB2 tables
----------
Record 20 — Policy Loans
    LH_CSH_VAL_LOAN     Traditional cash value loans
    LH_FND_VAL_LOAN     Fund-based (UL/VUL) loans

Record 77 — Loan Repayment
    LH_LN_RPY_TRM       Loan repayment schedule
"""

from __future__ import annotations

from decimal import Decimal
from datetime import date
from typing import Dict, List, Optional

from .cyberlife_base import PolicyDataAccessor, parse_date
from .policy_data_classes import LoanInfo, TradLoanInfo, LoanRepayInfo
from .policy_translations import (
    LOAN_TYPE_CODES,
    translate_loan_interest_type_code,
    translate_loan_interest_status_code,
)


class LoanRecords:
    """System-layer access for loan Cyberlife policy records."""

    TABLES = (
        "LH_CSH_VAL_LOAN",
        "LH_FND_VAL_LOAN",
        "LH_LN_RPY_TRM",
    )

    def __init__(self, policy: PolicyDataAccessor) -> None:
        self._policy = policy
        self._loans: Optional[List[LoanInfo]] = None

    def invalidate(self) -> None:
        self._loans = None

    # =====================================================================
    # COMBINED LOANS (LH_CSH_VAL_LOAN + LH_FND_VAL_LOAN)
    # =====================================================================

    def get_loans(self) -> List[LoanInfo]:
        """Get all active loans (traditional + fund-based)."""
        if self._loans is not None:
            return self._loans

        self._loans = []

        # Traditional loans
        for row in self._policy.fetch_table("LH_CSH_VAL_LOAN"):
            principal = Decimal(str(row.get("LN_PRI_AMT", 0) or 0))
            if principal <= 0:
                continue
            accrued = Decimal("0")
            if str(row.get("LN_ITS_AMT_TYP_CD")) == "2":
                accrued = Decimal(str(row.get("POL_LN_ITS_AMT", 0) or 0))
            loan = LoanInfo(
                LN_TYP_CD=str(row.get("LN_TYP_CD", "")),
                loan_type_desc=LOAN_TYPE_CODES.get(str(row.get("LN_TYP_CD", "")), ""),
                LN_PRI_AMT=principal,
                accrued_interest=accrued,
                LN_ITS_RT=Decimal(str(row["LN_CRG_ITS_RT"])) if row.get("LN_CRG_ITS_RT") else None,
                PRF_LN_IND=str(row.get("PRF_LN_IND")) == "1",
                raw_data=row,
            )
            self._loans.append(loan)

        # Fund-based loans
        for row in self._policy.fetch_table("LH_FND_VAL_LOAN"):
            principal = Decimal(str(row.get("LN_PRI_AMT", 0) or 0))
            if principal <= 0:
                continue
            accrued = Decimal(str(row.get("POL_LN_ITS_AMT", 0) or 0))
            loan = LoanInfo(
                LN_TYP_CD=str(row.get("LN_TYP_CD", "")),
                loan_type_desc=LOAN_TYPE_CODES.get(str(row.get("LN_TYP_CD", "")), ""),
                LN_PRI_AMT=principal,
                accrued_interest=accrued,
                LN_ITS_RT=Decimal(str(row["LN_CRG_ITS_RT"])) if row.get("LN_CRG_ITS_RT") else None,
                PRF_LN_IND=str(row.get("PRF_LN_IND")) == "1",
                raw_data=row,
            )
            self._loans.append(loan)

        return self._loans

    @property
    def total_loan_balance(self) -> Decimal:
        return sum((l.LN_PRI_AMT + l.accrued_interest for l in self.get_loans()), Decimal("0"))

    @property
    def total_loan_principal(self) -> Decimal:
        return sum((l.LN_PRI_AMT for l in self.get_loans()), Decimal("0"))

    @property
    def total_loan_interest(self) -> Decimal:
        return sum((l.accrued_interest for l in self.get_loans()), Decimal("0"))

    # =====================================================================
    # TRADITIONAL LOAN DETAILS (LH_CSH_VAL_LOAN)
    # =====================================================================

    def get_trad_loans(self) -> List[TradLoanInfo]:
        loans: List[TradLoanInfo] = []
        for row in self._policy.fetch_table("LH_CSH_VAL_LOAN"):
            mv_date = str(row.get("MVRY_DT", ""))
            if "9999" not in mv_date:
                continue
            int_type = str(row.get("LN_ITS_AMT_TYP_CD", "") or "")
            int_status = str(row.get("LN_ITS_AMT_TYP_CD", "") or "")
            loan = TradLoanInfo(
                mv_date=parse_date(row.get("MVRY_DT")),
                principal=Decimal(str(row.get("LN_PRI_AMT", 0) or 0)),
                accrued_interest=Decimal(str(row.get("POL_LN_ITS_AMT", 0) or 0)),
                interest_rate=Decimal(str(row["LN_CRG_ITS_RT"])) if row.get("LN_CRG_ITS_RT") else None,
                interest_type=int_type,
                interest_type_desc=translate_loan_interest_type_code(int_type),
                interest_status=int_status,
                interest_status_desc=translate_loan_interest_status_code(int_status),
                preferred_indicator=str(row.get("PRF_LN_IND", "") or ""),
                raw_data=row,
            )
            loans.append(loan)
        return loans

    @property
    def trad_loan_count(self) -> int:
        return self._policy.data_item_count("LH_CSH_VAL_LOAN")

    def trad_loan_mv_date(self, index: int) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_CSH_VAL_LOAN", "MVRY_DT", index))

    def trad_loan_principal(self, index: int) -> Optional[Decimal]:
        val = self._policy.data_item("LH_CSH_VAL_LOAN", "LN_PRI_AMT", index)
        return Decimal(str(val)) if val else None

    def trad_loan_accrued(self, index: int) -> Optional[Decimal]:
        val = self._policy.data_item("LH_CSH_VAL_LOAN", "POL_LN_ITS_AMT", index)
        return Decimal(str(val)) if val else None

    def trad_loan_interest_rate(self, index: int) -> Optional[Decimal]:
        val = self._policy.data_item("LH_CSH_VAL_LOAN", "LN_CRG_ITS_RT", index)
        return Decimal(str(val)) if val else None

    def trad_loan_interest_type(self, index: int) -> str:
        return str(self._policy.data_item("LH_CSH_VAL_LOAN", "LN_ITS_AMT_TYP_CD", index) or "")

    def trad_loan_interest_status(self, index: int) -> str:
        return str(self._policy.data_item("LH_CSH_VAL_LOAN", "LN_ITS_AMT_TYP_CD", index) or "")

    def trad_loan_preferred(self, index: int) -> str:
        return str(self._policy.data_item("LH_CSH_VAL_LOAN", "PRF_LN_IND", index) or "")

    # =====================================================================
    # FUND LOAN DETAILS (LH_FND_VAL_LOAN)
    # =====================================================================

    @property
    def loan_fund_count(self) -> int:
        return self._policy.data_item_count("LH_FND_VAL_LOAN")

    def loan_fund_id(self, index: int) -> str:
        return str(self._policy.data_item("LH_FND_VAL_LOAN", "FUND_ID", index) or "")

    def loan_fund_mv_date(self, index: int) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_FND_VAL_LOAN", "MVRY_DT", index))

    def loan_fund_principal(self, index: int) -> Optional[Decimal]:
        val = self._policy.data_item("LH_FND_VAL_LOAN", "LN_PRI_AMT", index)
        return Decimal(str(val)) if val else None

    def loan_fund_accrued(self, index: int) -> Optional[Decimal]:
        val = self._policy.data_item("LH_FND_VAL_LOAN", "POL_LN_ITS_AMT", index)
        return Decimal(str(val)) if val else None

    def loan_fund_interest_rate(self, index: int) -> Optional[Decimal]:
        val = self._policy.data_item("LH_FND_VAL_LOAN", "LN_CRG_ITS_RT", index)
        return Decimal(str(val)) if val else None

    def loan_fund_interest_status(self, index: int) -> str:
        return str(self._policy.data_item("LH_FND_VAL_LOAN", "LN_ITS_AMT_TYP_CD", index) or "")

    def loan_fund_preferred(self, index: int) -> str:
        return str(self._policy.data_item("LH_FND_VAL_LOAN", "PRF_LN_IND", index) or "")

    # =====================================================================
    # DETAILED LOAN CALCULATIONS (trad vs fund, regular vs preferred)
    # =====================================================================

    def calc_fund_loan_total(self, loan_type: str, amount_type: str) -> Decimal:
        """Calculate fund loan totals. loan_type: regular/preferred/variable. amount_type: principal/accrued."""
        total = Decimal("0")
        for row in self._policy.fetch_table("LH_FND_VAL_LOAN"):
            mv_date = str(row.get("MVRY_DT", ""))
            if "9999" not in mv_date:
                continue
            fund_id = str(row.get("FUND_ID", ""))
            pref_ind = str(row.get("PRF_LN_IND", "0"))
            is_variable = (fund_id == "LZ")
            is_preferred = (pref_ind == "1" and not is_variable)
            is_regular = (pref_ind != "1" and not is_variable)
            if loan_type == "variable" and not is_variable:
                continue
            if loan_type == "preferred" and not is_preferred:
                continue
            if loan_type == "regular" and not is_regular:
                continue
            if amount_type == "principal":
                val = row.get("LN_PRI_AMT", 0)
            else:
                int_status = str(row.get("LN_ITS_AMT_TYP_CD", ""))
                if int_status == "1":
                    continue
                val = row.get("POL_LN_ITS_AMT", 0)
            total += Decimal(str(val or 0))
        return total

    def calc_trad_loan_total(self, loan_type: str, amount_type: str) -> Decimal:
        """Calculate traditional loan totals. loan_type: regular/preferred. amount_type: principal/accrued."""
        total = Decimal("0")
        for row in self._policy.fetch_table("LH_CSH_VAL_LOAN"):
            mv_date = str(row.get("MVRY_DT", ""))
            if "9999" not in mv_date:
                continue
            pref_ind = str(row.get("PRF_LN_IND", "0"))
            is_preferred = (pref_ind == "1")
            if loan_type == "preferred" and not is_preferred:
                continue
            if loan_type == "regular" and is_preferred:
                continue
            if amount_type == "principal":
                val = row.get("LN_PRI_AMT", 0)
            else:
                int_status = str(row.get("LN_ITS_AMT_TYP_CD", ""))
                if int_status == "1":
                    continue
                val = row.get("POL_LN_ITS_AMT", 0)
            total += Decimal(str(val or 0))
        return total

    # =====================================================================
    # LOAN REPAYMENT SCHEDULE (LH_LN_RPY_TRM)
    # =====================================================================

    def get_loan_repayments(self) -> List[LoanRepayInfo]:
        repayments: List[LoanRepayInfo] = []
        for row in self._policy.fetch_table("LH_LN_RPY_TRM"):
            repay = LoanRepayInfo(
                payment_number=0,   # PMT_NBR does not exist on LH_LN_RPY_TRM
                payment_date=None,  # PMT_DT does not exist on LH_LN_RPY_TRM
                payment_amount=None,  # PMT_AMT does not exist on LH_LN_RPY_TRM
                principal_amount=Decimal(str(row["LN_PRI_AMT"])) if row.get("LN_PRI_AMT") else None,
                interest_amount=Decimal(str(row["LN_RPY_AMT"])) if row.get("LN_RPY_AMT") else None,
                raw_data=row,
            )
            repayments.append(repay)
        return repayments

    @property
    def loan_repay_count(self) -> int:
        return self._policy.data_item_count("LH_LN_RPY_TRM")

    def loan_repay_number(self, index: int) -> int:
        """PMT_NBR does not exist on LH_LN_RPY_TRM."""
        return 0

    def loan_repay_date(self, index: int) -> Optional[date]:
        """PMT_DT does not exist on LH_LN_RPY_TRM."""
        return None

    def loan_repay_amount(self, index: int) -> Optional[Decimal]:
        """PMT_AMT does not exist on LH_LN_RPY_TRM."""
        return None

    def loan_repay_principal(self, index: int) -> Optional[Decimal]:
        val = self._policy.data_item("LH_LN_RPY_TRM", "LN_PRI_AMT", index)
        return Decimal(str(val)) if val else None

    def loan_repay_interest(self, index: int) -> Optional[Decimal]:
        val = self._policy.data_item("LH_LN_RPY_TRM", "LN_RPY_AMT", index)
        return Decimal(str(val)) if val else None

    # =====================================================================
    # HIGH-LEVEL LOAN PROPERTIES
    # =====================================================================

    @property
    def preferred_loans_available(self) -> bool:
        """Whether preferred loans are available on this policy."""
        opt_cd = self._policy.data_item("LH_NON_TRD_POL", "PRF_LN_OPT_CD")
        return opt_cd is not None and str(opt_cd) != "0"

    @property
    def total_regular_loan_principal(self) -> Decimal:
        """Total regular loan principal."""
        if self._policy.is_advanced_product:
            return self.calc_fund_loan_total("regular", "principal")
        else:
            return self.calc_trad_loan_total("regular", "principal")

    @property
    def total_regular_loan_accrued(self) -> Decimal:
        """Total regular loan accrued interest."""
        if self._policy.is_advanced_product:
            return self.calc_fund_loan_total("regular", "accrued")
        else:
            return self.calc_trad_loan_total("regular", "accrued")

    @property
    def total_preferred_loan_principal(self) -> Decimal:
        """Total preferred loan principal."""
        if self._policy.is_advanced_product:
            return self.calc_fund_loan_total("preferred", "principal")
        else:
            return self.calc_trad_loan_total("preferred", "principal")

    @property
    def total_preferred_loan_accrued(self) -> Decimal:
        """Total preferred loan accrued interest."""
        if self._policy.is_advanced_product:
            return self.calc_fund_loan_total("preferred", "accrued")
        else:
            return self.calc_trad_loan_total("preferred", "accrued")

    @property
    def total_variable_loan_principal(self) -> Decimal:
        """Total variable loan principal (UL only, fund LZ)."""
        if not self._policy.is_advanced_product:
            return Decimal("0")
        return self.calc_fund_loan_total("variable", "principal")

    @property
    def total_variable_loan_accrued(self) -> Decimal:
        """Total variable loan accrued interest (UL only, fund LZ)."""
        if not self._policy.is_advanced_product:
            return Decimal("0")
        return self.calc_fund_loan_total("variable", "accrued")

    @property
    def policy_debt(self) -> Decimal:
        """Total policy debt (all loans principal + interest)."""
        if self._policy.is_advanced_product:
            return (self.total_regular_loan_principal + self.total_regular_loan_accrued +
                    self.total_preferred_loan_principal + self.total_preferred_loan_accrued +
                    self.total_variable_loan_principal + self.total_variable_loan_accrued)
        else:
            return self.total_regular_loan_principal + self.total_regular_loan_accrued
