"""
CL_POLREC_55_57_65 — Fund Records (Records 55, 57, 65)
=========================================================

DB2 tables
----------
Record 55 — Fund Values
    LH_POL_FND_VAL_TOT  Fund bucket values (CSV, units, interest rate)

Record 57 — Fund Allocations
    LH_FND_ALC           Fund allocation percentages

Record 65 — Fund Transfer Allocation Sets
    LH_FND_TRS_ALC_SET   Fund transfer/allocation set metadata
"""

from __future__ import annotations

from decimal import Decimal
from datetime import date
from typing import Dict, List, Optional

from .cyberlife_base import PolicyDataAccessor, parse_date
from .policy_data_classes import FundBucketInfo
from .policy_translations import translate_fund_id


class FundRecords:
    """System-layer access for fund-related Cyberlife policy records."""

    TABLES = (
        "LH_POL_FND_VAL_TOT",
        "LH_FND_ALC",
        "LH_FND_TRS_ALC_SET",
    )

    def __init__(self, policy: PolicyDataAccessor) -> None:
        self._policy = policy

    def invalidate(self) -> None:
        pass

    # =====================================================================
    # FUND VALUES (LH_POL_FND_VAL_TOT)
    # =====================================================================

    def get_fund_values_dict(self) -> Dict[str, Decimal]:
        """Current fund values by fund ID (MVRY_DT contains 9999)."""
        fund_values: Dict[str, Decimal] = {}
        for row in self._policy.fetch_table("LH_POL_FND_VAL_TOT"):
            mv_date = str(row.get("MVRY_DT", ""))
            if "9999" in mv_date:
                fund_id = str(row.get("FND_ID_CD", ""))
                value = Decimal(str(row.get("CSV_AMT", 0) or 0))
                fund_values[fund_id] = fund_values.get(fund_id, Decimal("0")) + value
        return fund_values

    def get_loan_values_dict(self) -> Dict[str, Decimal]:
        """Current loan values by fund ID."""
        loan_values: Dict[str, Decimal] = {}
        for row in self._policy.fetch_table("LH_FND_VAL_LOAN"):
            mv_date = str(row.get("MVRY_DT", ""))
            if "9999" in mv_date:
                fund_id = str(row.get("FND_ID_CD", ""))
                principal = Decimal(str(row.get("LN_PRI_AMT", 0) or 0))
                loan_values[fund_id] = loan_values.get(fund_id, Decimal("0")) + principal
        return loan_values

    @property
    def total_fund_value(self) -> Decimal:
        return sum(self.get_fund_values_dict().values(), Decimal("0"))

    # =====================================================================
    # FUND BUCKETS (LH_POL_FND_VAL_TOT detail)
    # =====================================================================

    def get_fund_buckets(self, current_only: bool = True) -> List[FundBucketInfo]:
        buckets: List[FundBucketInfo] = []
        for row in self._policy.fetch_table("LH_POL_FND_VAL_TOT"):
            mv_date_str = str(row.get("MVRY_DT", ""))
            is_current = "9999" in mv_date_str
            if current_only and not is_current:
                continue
            fund_id = str(row.get("FND_ID_CD", "") or "")
            bucket = FundBucketInfo(
                fund_id=fund_id,
                fund_name=translate_fund_id(fund_id),
                mv_date=parse_date(row.get("MVRY_DT")),
                csv_amount=Decimal(str(row["CSV_AMT"])) if row.get("CSV_AMT") else None,
                units=Decimal(str(row["FND_UNT_QTY"])) if row.get("FND_UNT_QTY") else None,
                interest_rate=Decimal(str(row["VAL_PHA_ITS_RT"])) if row.get("VAL_PHA_ITS_RT") else None,
                start_date=parse_date(row.get("ITS_PER_STR_DT")),
                phase=int(row.get("COV_PHA_NBR", 0) or 0),
                is_current=is_current,
                raw_data=row,
            )
            buckets.append(bucket)
        return buckets

    @property
    def fund_bucket_count(self) -> int:
        return self._policy.data_item_count("LH_POL_FND_VAL_TOT")

    def fund_bucket_id(self, index: int) -> str:
        return str(self._policy.data_item("LH_POL_FND_VAL_TOT", "FND_ID_CD", index) or "")

    def fund_bucket_mv_date(self, index: int) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_POL_FND_VAL_TOT", "MVRY_DT", index))

    def fund_bucket_csv(self, index: int) -> Optional[Decimal]:
        val = self._policy.data_item("LH_POL_FND_VAL_TOT", "CSV_AMT", index)
        return Decimal(str(val)) if val else None

    def fund_bucket_units(self, index: int) -> Optional[Decimal]:
        val = self._policy.data_item("LH_POL_FND_VAL_TOT", "FND_UNT_QTY", index)
        return Decimal(str(val)) if val else None

    def fund_bucket_interest_rate(self, index: int) -> Optional[Decimal]:
        val = self._policy.data_item("LH_POL_FND_VAL_TOT", "VAL_PHA_ITS_RT", index)
        return Decimal(str(val)) if val else None

    def fund_bucket_start_date(self, index: int) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_POL_FND_VAL_TOT", "ITS_PER_STR_DT", index))

    def fund_bucket_phase(self, index: int) -> int:
        val = self._policy.data_item("LH_POL_FND_VAL_TOT", "COV_PHA_NBR", index)
        return int(val) if val else 0

    def fund_bucket_is_current(self, index: int) -> bool:
        mv_date = str(self._policy.data_item("LH_POL_FND_VAL_TOT", "MVRY_DT", index) or "")
        return "9999" in mv_date

    # =====================================================================
    # PREMIUM ALLOCATION (LH_FND_ALC / LH_FND_TRS_ALC_SET)
    # =====================================================================

    def get_premium_allocation_dict(self) -> Dict[str, Decimal]:
        """Current premium allocation percentages by fund ID."""
        allocations: Dict[str, Decimal] = {}

        # Find latest premium allocation set
        alloc_sets = self._policy.fetch_table("LH_FND_TRS_ALC_SET")
        latest_seq = 0
        for row in alloc_sets:
            trs_type = str(row.get("FND_TRS_TYP_CD", ""))
            if trs_type == "P":
                seq = int(row.get("FND_ALC_SEQ_NBR", 0) or 0)
                if seq > latest_seq:
                    latest_seq = seq

        # Get allocations for that sequence
        for row in self._policy.fetch_table("LH_FND_ALC"):
            alloc_type = str(row.get("FND_ALC_TYP_CD", ""))
            seq_nbr = int(row.get("FND_ALC_SEQ_NBR", 0) or 0)
            if alloc_type == "P" and seq_nbr == latest_seq:
                fund_id = str(row.get("FND_ID_CD", ""))
                pct = Decimal(str(row.get("FND_ALC_PCT", 0) or 0))
                allocations[fund_id] = pct

        return allocations
