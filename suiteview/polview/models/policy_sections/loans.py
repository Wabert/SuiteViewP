"""PolicyInformation loans section."""

from __future__ import annotations

from .base import PolicySection
from ..cl_polrec.policy_data_classes import LoanInfo
from ..cl_polrec.policy_data_classes import LoanRepayInfo
from ..cl_polrec.policy_data_classes import TradLoanInfo
from ..cl_polrec.policy_translations import LOAN_TYPE_CODES
from datetime import date
from decimal import Decimal
from typing import Any
from typing import Dict
from typing import List
from typing import Optional


class LoansSection(PolicySection):
    """Cohesive PolicyInformation loans view."""

    TABLES = frozenset(('LH_FND_VAL_LOAN', 'LN_CRG_ITS_RT', 'LN_ITS_AMT_TYP_CD', 'LN_PRI_AMT', 'LN_TYP_CD', 'LOAN_INTEREST_RATE', 'POL_LN_ITS_AMT', 'PREFERRED_LOAN_INTEREST_RATE', 'PRF_LN_IND',))
    CACHE_ATTRS = ('_loans',)

    def get_loans(self) -> List[LoanInfo]:
        """Get all active loans."""
        if self._loans is not None:
            return self._loans

        self._loans = []

        for table_name in self.product.product_rules.loan_tables:
            for row in self._active_loan_rows(table_name):
                self._loans.append(self._loan_from_row(row, advanced=table_name == "LH_FND_VAL_LOAN"))

        return self._loans

    def _loan_from_row(self, row: Dict[str, Any], *, advanced: bool) -> LoanInfo:
        """Build a LoanInfo from the selected product family's loan table."""
        principal = Decimal(str(row.get("LN_PRI_AMT", 0) or 0))
        if principal <= 0:
            raise ValueError("inactive loan rows must be filtered before construction")

        if advanced:
            accrued = Decimal(str(row.get("POL_LN_ITS_AMT", 0) or 0))
        else:
            accrued = Decimal("0")
            if str(row.get("LN_ITS_AMT_TYP_CD")) == "2":
                accrued = Decimal(str(row.get("POL_LN_ITS_AMT", 0) or 0))

        return LoanInfo(
            loan_type=str(row.get("LN_TYP_CD", "")),
            loan_type_desc=LOAN_TYPE_CODES.get(str(row.get("LN_TYP_CD", "")), ""),
            principal=principal,
            accrued_interest=accrued,
            interest_rate=Decimal(str(row["LN_CRG_ITS_RT"])) if row.get("LN_CRG_ITS_RT") else None,
            preferred_loan=str(row.get("PRF_LN_IND")) == "1",
            raw_data=row,
        )

    def _active_loan_rows(self, table_name: str) -> List[Dict[str, Any]]:
        rows = []
        for row in self.fetch_table(table_name):
            principal = Decimal(str(row.get("LN_PRI_AMT", 0) or 0))
            if principal <= 0:
                continue
            rows.append(row)
        return rows

    @property
    def total_loan_balance(self) -> Decimal:
        """Total loan balance (principal + accrued interest)."""
        total = Decimal("0")
        for loan in self.get_loans():
            total += loan.principal + loan.accrued_interest
        return total

    @property
    def total_loan_principal(self) -> Decimal:
        """Total loan principal."""
        return sum((loan.principal for loan in self.get_loans()), Decimal("0"))

    @property
    def total_loan_interest(self) -> Decimal:
        """Total accrued loan interest."""
        return sum((loan.accrued_interest for loan in self.get_loans()), Decimal("0"))

    def get_trad_loans(self) -> List[TradLoanInfo]:
        """Get traditional loan detail records."""
        return self.policy.loan_records.get_trad_loans()

    @property
    def trad_loan_count(self) -> int:
        """Count of traditional loan records."""
        return self.policy.loan_records.trad_loan_count

    def trad_loan_mv_date(self, index: int) -> Optional[date]:
        """Get traditional loan MV date (0-based index)."""
        return self.policy.loan_records.trad_loan_mv_date(index)

    def trad_loan_principal(self, index: int) -> Optional[Decimal]:
        """Get traditional loan principal (0-based index)."""
        return self.policy.loan_records.trad_loan_principal(index)

    def trad_loan_accrued(self, index: int) -> Optional[Decimal]:
        """Get traditional loan accrued interest (0-based index)."""
        return self.policy.loan_records.trad_loan_accrued(index)

    def trad_loan_interest_rate(self, index: int) -> Optional[Decimal]:
        """Get traditional loan interest rate (0-based index)."""
        return self.policy.loan_records.trad_loan_interest_rate(index)

    def trad_loan_interest_type(self, index: int) -> str:
        """Get traditional loan interest type code (0-based index)."""
        return self.policy.loan_records.trad_loan_interest_type(index)

    def trad_loan_interest_status(self, index: int) -> str:
        """Get traditional loan interest status code (0-based index)."""
        return self.policy.loan_records.trad_loan_interest_status(index)

    def trad_loan_preferred(self, index: int) -> str:
        """Get traditional loan preferred indicator (0-based index)."""
        return self.policy.loan_records.trad_loan_preferred(index)

    @property
    def loan_fund_count(self) -> int:
        """Count of fund loan records."""
        return self.policy.loan_records.loan_fund_count

    def loan_fund_id(self, index: int) -> str:
        """Get loan fund ID (0-based index)."""
        return self.policy.loan_records.loan_fund_id(index)

    def loan_fund_mv_date(self, index: int) -> Optional[date]:
        """Get loan fund MV date (0-based index)."""
        return self.policy.loan_records.loan_fund_mv_date(index)

    def loan_fund_principal(self, index: int) -> Optional[Decimal]:
        """Get loan fund principal (0-based index)."""
        return self.policy.loan_records.loan_fund_principal(index)

    def loan_fund_accrued(self, index: int) -> Optional[Decimal]:
        """Get loan fund accrued interest (0-based index)."""
        return self.policy.loan_records.loan_fund_accrued(index)

    def loan_fund_interest_rate(self, index: int) -> Optional[Decimal]:
        """Get loan fund interest rate (0-based index)."""
        return self.policy.loan_records.loan_fund_interest_rate(index)

    def loan_fund_interest_status(self, index: int) -> str:
        """Get loan fund interest status code (0-based index)."""
        return self.policy.loan_records.loan_fund_interest_status(index)

    def loan_fund_preferred(self, index: int) -> str:
        """Get loan fund preferred indicator (0-based index)."""
        return self.policy.loan_records.loan_fund_preferred(index)

    def get_loan_repayments(self) -> List[LoanRepayInfo]:
        """Get loan repayment schedule records."""
        return self.policy.loan_records.get_loan_repayments()

    @property
    def loan_repay_count(self) -> int:
        """Count of loan repayment records."""
        return self.policy.loan_records.loan_repay_count

    def loan_repay_number(self, index: int) -> int:
        """Get loan repayment payment number (0-based index)."""
        return self.policy.loan_records.loan_repay_number(index)

    def loan_repay_date(self, index: int) -> Optional[date]:
        """Get loan repayment payment date (0-based index)."""
        return self.policy.loan_records.loan_repay_date(index)

    def loan_repay_amount(self, index: int) -> Optional[Decimal]:
        """Get loan repayment payment amount (0-based index)."""
        return self.policy.loan_records.loan_repay_amount(index)

    def loan_repay_principal(self, index: int) -> Optional[Decimal]:
        """Get loan repayment principal amount (0-based index)."""
        return self.policy.loan_records.loan_repay_principal(index)

    def loan_repay_interest(self, index: int) -> Optional[Decimal]:
        """Get loan repayment interest amount (0-based index)."""
        return self.policy.loan_records.loan_repay_interest(index)

    @property
    def policy_loan_charge_rate(self) -> Optional[Decimal]:
        """Policy loan charge interest rate."""
        val = self._field("loan_interest_rate")
        return Decimal(str(val)) if val is not None else None

    @property
    def total_regular_loan_principal(self) -> Decimal:
        """Total regular loan principal."""
        return self.policy.loan_records.total_regular_loan_principal

    @property
    def total_regular_loan_accrued(self) -> Decimal:
        """Total regular loan accrued interest."""
        return self.policy.loan_records.total_regular_loan_accrued

    @property
    def total_preferred_loan_principal(self) -> Decimal:
        """Total preferred loan principal."""
        return self.policy.loan_records.total_preferred_loan_principal

    @property
    def total_preferred_loan_accrued(self) -> Decimal:
        """Total preferred loan accrued interest."""
        return self.policy.loan_records.total_preferred_loan_accrued

    @property
    def total_variable_loan_principal(self) -> Decimal:
        """Total variable loan principal (UL only, fund LZ)."""
        return self.policy.loan_records.total_variable_loan_principal

    @property
    def total_variable_loan_accrued(self) -> Decimal:
        """Total variable loan accrued interest (UL only, fund LZ)."""
        return self.policy.loan_records.total_variable_loan_accrued

    @property
    def variable_loan_charge_rate(self) -> Optional[Decimal]:
        """Most recent variable loan charge rate, or None when not applicable."""
        return self.policy.loan_records.variable_loan_charge_rate

    @property
    def policy_debt(self) -> Decimal:
        """Total policy debt (all loans principal + interest)."""
        return self.policy.loan_records.policy_debt

    @property
    def preferred_loans_available(self) -> bool:
        """Whether preferred loans are available on this policy."""
        return self.policy.loan_records.preferred_loans_available

    @property
    def fixed_loan_interest_rate(self) -> Optional[Decimal]:
        """Fixed (regular) loan interest charge rate (LH_BAS_POL.LN_PLN_ITS_RT)."""
        val = self._field("loan_interest_rate")
        return Decimal(str(val)) if val is not None else None

    @property
    def preferred_loan_interest_rate(self) -> Optional[Decimal]:
        """Preferred loan interest charge rate (LH_NON_TRD_POL.PRF_LN_ITS_CRG_RT)."""
        val = self._field("preferred_loan_interest_rate")
        return Decimal(str(val)) if val is not None else None
