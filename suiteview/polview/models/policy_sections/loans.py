"""PolicyInformation loans section."""

from __future__ import annotations

from .base import PolicySection
from ..cl_polrec.policy_data_classes import LoanInfo
from ..cl_polrec.policy_data_classes import ScheduledLoanRepayment
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

    CACHE_ATTRS = ('_loans',)

    def get_loans(self) -> List[LoanInfo]:
        """Current loans (MVRY_DT 12/31/9999 rows) from the active loan table."""
        if self._loans is not None:
            return self._loans

        self._loans = []

        table_name = self.loan_table
        for row in self._active_loan_rows(table_name):
            self._loans.append(self._loan_from_row(row, advanced=table_name == "LH_FND_VAL_LOAN"))

        return self._loans

    @property
    def loan_table(self) -> str:
        """Loan table holding this policy's loans (ISWL on RPU uses LH_CSH_VAL_LOAN)."""
        return self.product.product_rules.active_loan_table(self.status.premium_pay_status_code)

    @property
    def uses_fund_loans(self) -> bool:
        """Whether current loans are fund loans (LH_FND_VAL_LOAN) rather than cash-value loans."""
        return self.loan_table == "LH_FND_VAL_LOAN"

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

    def get_fund_loan_history(self) -> List[LoanInfo]:
        """Every LH_FND_VAL_LOAN row with principal: the current (12/31/9999) row plus
        the monthliversary snapshots, each dated by its ``raw_data["MVRY_DT"]``.

        Not a debt total; ``get_loans`` holds only the current loans.
        """
        return [
            self._loan_from_row(row, advanced=True)
            for row in self.fetch_table("LH_FND_VAL_LOAN")
            if Decimal(str(row.get("LN_PRI_AMT", 0) or 0)) > 0
        ]

    def _active_loan_rows(self, table_name: str) -> List[Dict[str, Any]]:
        rows = []
        for row in self.fetch_table(table_name):
            principal = Decimal(str(row.get("LN_PRI_AMT", 0) or 0))
            if principal <= 0:
                continue
            # Loan rows dated at a monthliversary/anniversary are history snapshots;
            # only the MVRY_DT 12/31/9999 row is the current loan.
            if "9999" not in str(row.get("MVRY_DT", "9999")):
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

    @property
    def scheduled_loan_repayment(self) -> Optional[ScheduledLoanRepayment]:
        """Scheduled loan repayment (SLR) billing from LH_LN_RPY_TRM, or None."""
        return self.policy.loan_records.get_scheduled_loan_repayment()

    @property
    def has_scheduled_loan_repayment(self) -> bool:
        """Whether the policy bills a positive scheduled loan repayment."""
        slr = self.scheduled_loan_repayment
        return bool(slr and slr.is_active)

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
    def loan_type_code(self) -> str:
        """Policy loan interest type (LH_BAS_POL.LN_TYP_CD): 0/1 advance/arrears fixed, 6/7 variable."""
        return str(self._field("loan_type_code") or "").strip()

    @property
    def preferred_loan_interest_rate(self) -> Optional[Decimal]:
        """Preferred loan interest charge rate (LH_NON_TRD_POL.PRF_LN_ITS_CRG_RT)."""
        val = self._field("preferred_loan_interest_rate")
        return Decimal(str(val)) if val is not None else None
