"""PolicyInformation values section."""

from __future__ import annotations

from .base import PolicySection
from ..cl_polrec.policy_data_classes import FundBucketInfo
from ..cl_polrec.policy_translations import translate_fund_id
from datetime import date
from decimal import Decimal
from typing import Dict
from typing import List
from typing import Optional


class ValuesSection(PolicySection):
    """Cohesive PolicyInformation values view."""

    CACHE_ATTRS = ('_mv_values',)

    @property
    def cash_surrender_value(self) -> Optional[Decimal]:
        """Current cash surrender value."""
        return self.policy.total_records.CSH_SUR_VAL_AMT

    @property
    def accumulation_value(self) -> Optional[Decimal]:
        """Current accumulation value (for UL products)."""
        return self.policy.total_records.ACC_VAL_AMT

    @property
    def death_benefit(self) -> Optional[Decimal]:
        """Current death benefit."""
        total_records_value = self.policy.total_records.DTH_BNF_AMT
        if total_records_value is not None:
            return total_records_value
        return self.coverages.total_death_benefit

    @property
    def net_amount_at_risk(self) -> Optional[Decimal]:
        """Net amount at risk."""
        return self.policy.total_records.NET_AMT_RSK

    @property
    def is_mec(self) -> bool:
        """Whether policy is a Modified Endowment Contract."""
        return self.policy.total_records.is_mec

    @property
    def seven_pay_premium(self) -> Optional[Decimal]:
        """7-Pay premium limit."""
        return self.policy.total_records.seven_pay_premium

    @property
    def accumulated_glp(self) -> Optional[Decimal]:
        """Accumulated Guideline Level Premium."""
        return self.policy.total_records.accumulated_glp

    @property
    def accumulated_mtp(self) -> Optional[Decimal]:
        """Accumulated 7-Pay Premium (MTP)."""
        return self.policy.total_records.accumulated_mtp

    @property
    def total_withdrawals(self) -> Decimal:
        """Total withdrawals lifetime (VBA: AccumWithdrawals from TOT_WTD_AMT)."""
        return self.policy.total_records.TOT_WTD_AMT

    @property
    def total_withdrawal_count(self) -> int:
        """Number of withdrawals lifetime (TOT_WTD_QTY)."""
        return self.policy.total_records.TOT_WTD_QTY

    @property
    def total_withdrawal_charges(self) -> Optional[Decimal]:
        """Withdrawal charges since issue, adjusted by reversals (TOT_WTD_CRG_AMT). Under the
        rule-6 target surrender charge only the target-based charges, not the flat fee (D202)."""
        value = self.policy.total_records.TOT_WTD_CRG_AMT
        if self.table_error("LH_POL_TOTALS"):
            return None
        return value

    @property
    def cost_basis(self) -> Decimal:
        """Tax cost basis (VBA: CostBasis from POL_CST_BSS_AMT)."""
        return self.policy.total_records.POL_CST_BSS_AMT

    @property
    def policy_totals_count(self) -> int:
        """Count of LH_POL_TOTALS rows (VBA: PolicyTotalsCount)."""
        return self.policy.total_records.policy_totals_count

    def traditional_valuation_date(self) -> Optional[date]:
        """Traditional valuation-date fallback: prior monthliversary, else financial date."""
        next_mv = self.activity.next_monthliversary_date
        if next_mv and next_mv.year < 9999:
            # Go back exactly one calendar month (same day)
            if next_mv.month == 1:
                prev_year, prev_month = next_mv.year - 1, 12
            else:
                prev_year, prev_month = next_mv.year, next_mv.month - 1
            # Handle day overflow (e.g. March 31 -> Feb 28)
            import calendar
            max_day = calendar.monthrange(prev_year, prev_month)[1]
            prev_day = min(next_mv.day, max_day)
            return date(prev_year, prev_month, prev_day)
        return self.activity.last_financial_date

    @property
    def valuation_date(self) -> Optional[date]:
        """
        Get valuation date - MV date for UL, last monthliversary for traditional.
        """
        return self.product.product_rules.valuation_date(self)

    @property
    def mv_count(self) -> int:
        """Count of monthliversary value records."""
        return self.data_item_count("LH_POL_MVRY_VAL")

    def mv_date(self, index: int = 0) -> Optional[date]:
        """Get monthliversary date at index."""
        return self._parse_date(self.data_item("LH_POL_MVRY_VAL", "MVRY_DT", index))

    def mv_av(self, index: int = 0) -> Optional[Decimal]:
        """Get MV accumulation value at index."""
        val = self.data_item("LH_POL_MVRY_VAL", "CSV_AMT", index)
        return Decimal(str(val)) if val is not None else None

    def mv_coi_charge(self, index: int = 0) -> Decimal:
        """Get MV COI charge at index."""
        val = self.data_item("LH_POL_MVRY_VAL", "CINS_AMT", index)
        return Decimal(str(val)) if val else Decimal("0")

    def mv_expense_charge(self, index: int = 0) -> Decimal:
        """Get MV expense charge at index."""
        val = self.data_item("LH_POL_MVRY_VAL", "EXP_CRG_AMT", index)
        return Decimal(str(val)) if val else Decimal("0")

    def mv_other_charge(self, index: int = 0) -> Decimal:
        """Get MV other charges at index."""
        val = self.data_item("LH_POL_MVRY_VAL", "OTH_PRM_AMT", index)
        return Decimal(str(val)) if val else Decimal("0")

    def mv_monthly_deduction(self, index: int = 0) -> Decimal:
        """Get total MV monthly deduction at index."""
        return self.mv_coi_charge(index) + self.mv_expense_charge(index) + self.mv_other_charge(index)

    def mv_nar(self, index: int = 0) -> Decimal:
        """Get MV net amount at risk at index."""
        val = self.data_item("LH_POL_MVRY_VAL", "NAR_AMT", index)
        return Decimal(str(val)) if val else Decimal("0")

    @property
    def mv_policy_year(self) -> Optional[int]:
        """Current policy year from MV record."""
        val = self.data_item("LH_POL_MVRY_VAL", "POL_DUR_NBR")
        return int(val) if val else None

    @property
    def tamra_7pay_level(self) -> Optional[Decimal]:
        """7-pay level premium."""
        val = self.data_item("LH_TAMRA_7_PY_PER", "SVPY_LVL_PRM_AMT")
        return Decimal(str(val)) if val else None

    @property
    def tamra_7pay_start_date(self) -> Optional[date]:
        """7-pay period start date."""
        dt = self._parse_date(self.data_item("LH_TAMRA_7_PY_PER", "SVPY_PER_STR_DT"))
        if dt and dt.year >= 9999:
            return None
        return dt

    @property
    def tamra_7pay_av(self) -> Optional[Decimal]:
        """7-pay beginning CSV amount."""
        val = self.data_item("LH_TAMRA_7_PY_PER", "SVPY_BEG_CSV_AMT")
        return Decimal(str(val)) if val else None

    @property
    def tamra_7pay_specified_amount(self) -> Optional[Decimal]:
        """7-pay beginning face amount."""
        val = self.data_item("LH_TAMRA_7_PY_PER", "SVPY_BEG_FCE_AMT")
        return Decimal(str(val)) if val else None

    @property
    def mec_indicator(self) -> str:
        """MEC status indicator code."""
        return str(self.data_item("LH_TAMRA_7_PY_PER", "MEC_STA_CD") or "")

    @property
    def count_1035_payments(self) -> int:
        """Number of 1035 exchange payments."""
        val = self.data_item("LH_TAMRA_7_PY_PER", "XCG_1035_PMT_QTY")
        return int(val) if val else 0

    def tamra_7pay_premium_paid(self, year: int) -> Optional[Decimal]:
        """Get 7-pay premium paid for specified year (1-7)."""
        if year < 1 or year > 7:
            return None
        val = self.data_item("LH_TAMRA_7_PY_YR", "SVPY_PRM_PAY_AMT", year - 1)
        return Decimal(str(val)) if val else None

    def tamra_7pay_withdrawals(self, year: int) -> Optional[Decimal]:
        """Get 7-pay withdrawals for specified year (1-7)."""
        if year < 1 or year > 7:
            return None
        val = self.data_item("LH_TAMRA_7_PY_YR", "SVPY_WTD_AMT", year - 1)
        return Decimal(str(val)) if val else None

    def get_fund_values_dict(self) -> Dict[str, Decimal]:
        """
        Get dictionary of current fund values by fund ID.
        Only includes buckets effective on valuation date (MVRY_DT = 12/31/9999).
        """
        fund_values: Dict[str, Decimal] = {}

        for row in self.fetch_table("LH_POL_FND_VAL_TOT"):
            mv_date = str(row.get("MVRY_DT", ""))
            # Check if bucket is current (ends on 12/31/9999)
            if "9999" in mv_date:
                fund_id = str(row.get("FND_ID_CD", ""))
                value = Decimal(str(row.get("CSV_AMT", 0) or 0))
                fund_values[fund_id] = fund_values.get(fund_id, Decimal("0")) + value

        return fund_values

    def get_loan_values_dict(self) -> Dict[str, Decimal]:
        """
        Get dictionary of current loan values by fund ID.
        Only includes buckets effective on valuation date.
        """
        loan_values: Dict[str, Decimal] = {}

        for row in self.fetch_table("LH_FND_VAL_LOAN"):
            mv_date = str(row.get("MVRY_DT", ""))
            if "9999" in mv_date:
                fund_id = str(row.get("FND_ID_CD", ""))
                principal = Decimal(str(row.get("LN_PRI_AMT", 0) or 0))
                loan_values[fund_id] = loan_values.get(fund_id, Decimal("0")) + principal

        return loan_values

    @property
    def total_fund_value(self) -> Decimal:
        """Total of all fund values."""
        return sum(self.get_fund_values_dict().values(), Decimal("0"))

    def get_fund_buckets(self, current_only: bool = True) -> List[FundBucketInfo]:
        """Get fund bucket detail records."""
        buckets = []
        for row in self.fetch_table("LH_POL_FND_VAL_TOT"):
            mv_date_str = str(row.get("MVRY_DT", ""))
            is_current = "9999" in mv_date_str

            if current_only and not is_current:
                continue

            fund_id = str(row.get("FND_ID_CD", "") or "")
            bucket = FundBucketInfo(
                fund_id=fund_id,
                fund_name=translate_fund_id(fund_id),
                mv_date=self._parse_date(row.get("MVRY_DT")),
                csv_amount=Decimal(str(row["CSV_AMT"])) if row.get("CSV_AMT") else None,
                units=Decimal(str(row["FND_UNT_QTY"])) if row.get("FND_UNT_QTY") else None,
                interest_rate=(
                    Decimal(str(row["VAL_PHA_ITS_RT"])) if row.get("VAL_PHA_ITS_RT") is not None else None
                ),
                start_date=self._parse_date(row.get("BKT_STR_DT")),
                phase=int(row.get("COV_PHA_NBR", 0) or 0),
                is_current=is_current,
                raw_data=row
            )
            buckets.append(bucket)
        return buckets

    @property
    def fund_bucket_count(self) -> int:
        """Count of fund bucket records."""
        return self.data_item_count("LH_POL_FND_VAL_TOT")

    def fund_bucket_id(self, index: int) -> str:
        """Get fund bucket ID (0-based index)."""
        return str(self.data_item("LH_POL_FND_VAL_TOT", "FND_ID_CD", index) or "")

    def fund_bucket_mv_date(self, index: int) -> Optional[date]:
        """Get fund bucket MV date (0-based index)."""
        return self._parse_date(self.data_item("LH_POL_FND_VAL_TOT", "MVRY_DT", index))

    def fund_bucket_csv(self, index: int) -> Optional[Decimal]:
        """Get fund bucket CSV amount (0-based index)."""
        val = self.data_item("LH_POL_FND_VAL_TOT", "CSV_AMT", index)
        return Decimal(str(val)) if val else None

    def fund_bucket_units(self, index: int) -> Optional[Decimal]:
        """Get fund bucket units (0-based index)."""
        val = self.data_item("LH_POL_FND_VAL_TOT", "FND_UNT_QTY", index)
        return Decimal(str(val)) if val else None

    def fund_bucket_interest_rate(self, index: int) -> Optional[Decimal]:
        """Get fund bucket credited interest rate (0-based index)."""
        val = self.data_item("LH_POL_FND_VAL_TOT", "VAL_PHA_ITS_RT", index)
        return Decimal(str(val)) if val is not None else None

    def fund_bucket_start_date(self, index: int) -> Optional[date]:
        """Get fund bucket start date (0-based index)."""
        return self._parse_date(self.data_item("LH_POL_FND_VAL_TOT", "BKT_STR_DT", index))

    def fund_bucket_phase(self, index: int) -> int:
        """Get fund bucket coverage phase (0-based index)."""
        val = self.data_item("LH_POL_FND_VAL_TOT", "COV_PHA_NBR", index)
        return int(val) if val else 0

    def fund_bucket_is_current(self, index: int) -> bool:
        """Check if fund bucket is current (MV date contains 9999)."""
        mv_date = str(self.data_item("LH_POL_FND_VAL_TOT", "MVRY_DT", index) or "")
        return "9999" in mv_date

    def get_premium_allocation_dict(self) -> Dict[str, Decimal]:
        """
        Get dictionary of current premium allocation percentages by fund ID.
        """
        allocations: Dict[str, Decimal] = {}

        # Find the most recent allocation set
        alloc_sets = self.fetch_table("LH_FND_TRS_ALC_SET")
        latest_seq = 0

        for row in alloc_sets:
            trs_type = str(row.get("FND_TRS_TYP_CD", ""))
            if trs_type == "P":  # Premium allocation
                seq = int(row.get("FND_ALC_SEQ_NBR", 0) or 0)
                if seq > latest_seq:
                    latest_seq = seq

        # Get allocations for that sequence
        for row in self.fetch_table("LH_FND_ALC"):
            alloc_type = str(row.get("FND_ALC_TYP_CD", ""))
            seq_nbr = int(row.get("FND_ALC_SEQ_NBR", 0) or 0)

            if alloc_type == "P" and seq_nbr == latest_seq:
                fund_id = str(row.get("FND_ID_CD", ""))
                pct = Decimal(str(row.get("FND_ALC_PCT", 0) or 0))
                allocations[fund_id] = pct

        return allocations
