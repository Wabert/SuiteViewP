"""
CL_POLREC_12_13_14_15_18_19_74 — Dividend Records
====================================================

DB2 tables
----------
Record 12 — Applied Dividends
    LH_APPLIED_PTP      Applied participation records

Record 13 — Unapplied Dividends
    LH_UNAPPLIED_PTP    Unapplied participation records

Record 14 — One Year Term Additions
    LH_ONE_YR_TRM_ADD   Dividend OYT additions

Record 15 — Paid-Up Additions
    LH_PAID_UP_ADD      Dividend PUA additions

Record 18/19 — Dividends on Deposit
    LH_PTP_ON_DEP       Dividend deposit records

Record 74 — (Additional dividend sub-records)
"""

from __future__ import annotations

from decimal import Decimal
from datetime import date
from typing import List, Optional

from .cyberlife_base import PolicyDataAccessor, parse_date
from .policy_data_classes import (
    AppliedDividendInfo,
    UnappliedDividendInfo,
    DivOYTInfo,
    DivPUAInfo,
    DivDepositInfo,
)
from .policy_translations import translate_div_type_code


class DividendRecords:
    """System-layer access for dividend-related Cyberlife policy records."""

    TABLES = (
        "LH_APPLIED_PTP",
        "LH_UNAPPLIED_PTP",
        "LH_ONE_YR_TRM_ADD",
        "LH_PAID_UP_ADD",
        "LH_PTP_ON_DEP",
    )

    def __init__(self, policy: PolicyDataAccessor) -> None:
        self._policy = policy

    def invalidate(self) -> None:
        pass

    # =====================================================================
    # APPLIED DIVIDENDS (LH_APPLIED_PTP)
    # =====================================================================

    def get_applied_dividends(self) -> List[AppliedDividendInfo]:
        dividends: List[AppliedDividendInfo] = []
        for row in self._policy.fetch_table("LH_APPLIED_PTP"):
            div_type = str(row.get("CK_PTP_TYP_CD", "") or "")
            div = AppliedDividendInfo(
                dividend_date=None,    # PTP_APL_DT does not exist on LH_APPLIED_PTP
                dividend_type=div_type,
                dividend_type_desc=translate_div_type_code(div_type),
                gross_amount=None,     # PTP_GRS_AMT does not exist on LH_APPLIED_PTP
                net_amount=None,       # PTP_NET_AMT does not exist on LH_APPLIED_PTP
                year=int(row["POL_DUR_NBR"]) if row.get("POL_DUR_NBR") else None,
                raw_data=row,
            )
            dividends.append(div)
        return dividends

    @property
    def applied_div_count(self) -> int:
        return self._policy.data_item_count("LH_APPLIED_PTP")

    def applied_div_date(self, index: int) -> Optional[date]:
        """PTP_APL_DT does not exist on LH_APPLIED_PTP."""
        return None

    def applied_div_type(self, index: int) -> str:
        return str(self._policy.data_item("LH_APPLIED_PTP", "CK_PTP_TYP_CD", index) or "")

    def applied_div_gross_amount(self, index: int) -> Optional[Decimal]:
        """PTP_GRS_AMT does not exist on LH_APPLIED_PTP."""
        return None

    def applied_div_net_amount(self, index: int) -> Optional[Decimal]:
        """PTP_NET_AMT does not exist on LH_APPLIED_PTP."""
        return None

    def applied_div_year(self, index: int) -> Optional[int]:
        val = self._policy.data_item("LH_APPLIED_PTP", "POL_DUR_NBR", index)
        return int(val) if val else None

    # =====================================================================
    # UNAPPLIED DIVIDENDS (LH_UNAPPLIED_PTP)
    # =====================================================================

    def get_unapplied_dividends(self) -> List[UnappliedDividendInfo]:
        dividends: List[UnappliedDividendInfo] = []
        for row in self._policy.fetch_table("LH_UNAPPLIED_PTP"):
            div_type = str(row.get("CK_PTP_TYP_CD", "") or "")
            div = UnappliedDividendInfo(
                dividend_date=None,    # PTP_PRO_DT does not exist on LH_UNAPPLIED_PTP
                dividend_type=div_type,
                dividend_type_desc=translate_div_type_code(div_type),
                gross_amount=None,     # PTP_GRS_AMT does not exist on LH_UNAPPLIED_PTP
                net_amount=None,       # PTP_NET_AMT does not exist on LH_UNAPPLIED_PTP
                year=int(row["POL_DUR_NBR"]) if row.get("POL_DUR_NBR") else None,
                raw_data=row,
            )
            dividends.append(div)
        return dividends

    @property
    def unapplied_div_count(self) -> int:
        return self._policy.data_item_count("LH_UNAPPLIED_PTP")

    def unapplied_div_date(self, index: int) -> Optional[date]:
        """PTP_PRO_DT does not exist on LH_UNAPPLIED_PTP."""
        return None

    def unapplied_div_type(self, index: int) -> str:
        return str(self._policy.data_item("LH_UNAPPLIED_PTP", "CK_PTP_TYP_CD", index) or "")

    def unapplied_div_gross_amount(self, index: int) -> Optional[Decimal]:
        """PTP_GRS_AMT does not exist on LH_UNAPPLIED_PTP."""
        return None

    def unapplied_div_net_amount(self, index: int) -> Optional[Decimal]:
        """PTP_NET_AMT does not exist on LH_UNAPPLIED_PTP."""
        return None

    def unapplied_div_year(self, index: int) -> Optional[int]:
        val = self._policy.data_item("LH_UNAPPLIED_PTP", "POL_DUR_NBR", index)
        return int(val) if val else None

    # =====================================================================
    # ONE YEAR TERM ADDITIONS (LH_ONE_YR_TRM_ADD)
    # =====================================================================

    def get_div_oyt(self) -> List[DivOYTInfo]:
        oyts: List[DivOYTInfo] = []
        for row in self._policy.fetch_table("LH_ONE_YR_TRM_ADD"):
            oyt = DivOYTInfo(
                coverage_phase=int(row.get("COV_PHA_NBR", 0) or 0),
                issue_date=None,  # OYT_ISS_DT does not exist on LH_ONE_YR_TRM_ADD
                face_amount=Decimal(str(row["OYT_ADD_AMT"])) if row.get("OYT_ADD_AMT") else None,
                csv_amount=Decimal(str(row["OYT_ADD_AMT"])) if row.get("OYT_ADD_AMT") else None,
                raw_data=row,
            )
            oyts.append(oyt)
        return oyts

    @property
    def div_oyt_count(self) -> int:
        return self._policy.data_item_count("LH_ONE_YR_TRM_ADD")

    def div_oyt_cov_phase(self, index: int) -> int:
        val = self._policy.data_item("LH_ONE_YR_TRM_ADD", "COV_PHA_NBR", index)
        return int(val) if val else 0

    def div_oyt_issue_date(self, index: int) -> Optional[date]:
        """OYT_ISS_DT does not exist on LH_ONE_YR_TRM_ADD."""
        return None

    def div_oyt_face_amount(self, index: int) -> Optional[Decimal]:
        val = self._policy.data_item("LH_ONE_YR_TRM_ADD", "OYT_ADD_AMT", index)
        return Decimal(str(val)) if val else None

    def div_oyt_csv(self, index: int) -> Optional[Decimal]:
        val = self._policy.data_item("LH_ONE_YR_TRM_ADD", "OYT_ADD_AMT", index)
        return Decimal(str(val)) if val else None

    @property
    def total_oyt_face(self) -> Decimal:
        total = Decimal("0")
        for i in range(self.div_oyt_count):
            val = self.div_oyt_face_amount(i)
            if val:
                total += val
        return total

    @property
    def total_oyt_csv(self) -> Decimal:
        total = Decimal("0")
        for i in range(self.div_oyt_count):
            val = self.div_oyt_csv(i)
            if val:
                total += val
        return total

    # =====================================================================
    # PAID-UP ADDITIONS (LH_PAID_UP_ADD)
    # =====================================================================

    def get_div_pua(self) -> List[DivPUAInfo]:
        puas: List[DivPUAInfo] = []
        for row in self._policy.fetch_table("LH_PAID_UP_ADD"):
            pua = DivPUAInfo(
                coverage_phase=int(row.get("COV_PHA_NBR", 0) or 0),
                issue_date=None,  # PUA_ISS_DT does not exist on LH_PAID_UP_ADD
                face_amount=Decimal(str(row["PUA_AMT"])) if row.get("PUA_AMT") else None,
                csv_amount=Decimal(str(row["PUA_AMT"])) if row.get("PUA_AMT") else None,
                raw_data=row,
            )
            puas.append(pua)
        return puas

    @property
    def div_pua_count(self) -> int:
        return self._policy.data_item_count("LH_PAID_UP_ADD")

    def div_pua_cov_phase(self, index: int) -> int:
        val = self._policy.data_item("LH_PAID_UP_ADD", "COV_PHA_NBR", index)
        return int(val) if val else 0

    def div_pua_issue_date(self, index: int) -> Optional[date]:
        """PUA_ISS_DT does not exist on LH_PAID_UP_ADD."""
        return None

    def div_pua_face_amount(self, index: int) -> Optional[Decimal]:
        val = self._policy.data_item("LH_PAID_UP_ADD", "PUA_AMT", index)
        return Decimal(str(val)) if val else None

    def div_pua_csv(self, index: int) -> Optional[Decimal]:
        val = self._policy.data_item("LH_PAID_UP_ADD", "PUA_AMT", index)
        return Decimal(str(val)) if val else None

    @property
    def total_pua_face(self) -> Decimal:
        total = Decimal("0")
        for i in range(self.div_pua_count):
            val = self.div_pua_face_amount(i)
            if val:
                total += val
        return total

    @property
    def total_pua_csv(self) -> Decimal:
        total = Decimal("0")
        for i in range(self.div_pua_count):
            val = self.div_pua_csv(i)
            if val:
                total += val
        return total

    # =====================================================================
    # DIVIDENDS ON DEPOSIT (LH_PTP_ON_DEP)
    # =====================================================================

    def get_div_deposits(self) -> List[DivDepositInfo]:
        deposits: List[DivDepositInfo] = []
        for row in self._policy.fetch_table("LH_PTP_ON_DEP"):
            dep_type = str(row.get("CK_PTP_TYP_CD", "") or "")
            dep = DivDepositInfo(
                deposit_date=None,    # DEP_DT does not exist on LH_PTP_ON_DEP
                deposit_type=dep_type,
                deposit_type_desc=translate_div_type_code(dep_type),
                deposit_amount=Decimal(str(row["PTP_DEP_AMT"])) if row.get("PTP_DEP_AMT") else None,
                interest_amount=Decimal(str(row["DEP_ITS_AMT"])) if row.get("DEP_ITS_AMT") else None,
                raw_data=row,
            )
            deposits.append(dep)
        return deposits

    @property
    def div_deposit_count(self) -> int:
        return self._policy.data_item_count("LH_PTP_ON_DEP")

    def div_deposit_date(self, index: int) -> Optional[date]:
        """DEP_DT does not exist on LH_PTP_ON_DEP."""
        return None

    def div_deposit_type(self, index: int) -> str:
        return str(self._policy.data_item("LH_PTP_ON_DEP", "CK_PTP_TYP_CD", index) or "")

    def div_deposit_amount(self, index: int) -> Optional[Decimal]:
        val = self._policy.data_item("LH_PTP_ON_DEP", "PTP_DEP_AMT", index)
        return Decimal(str(val)) if val else None

    def div_deposit_interest(self, index: int) -> Optional[Decimal]:
        val = self._policy.data_item("LH_PTP_ON_DEP", "DEP_ITS_AMT", index)
        return Decimal(str(val)) if val else None

    @property
    def total_div_deposit(self) -> Decimal:
        total = Decimal("0")
        for i in range(self.div_deposit_count):
            val = self.div_deposit_amount(i)
            if val:
                total += val
        return total

    @property
    def total_div_interest(self) -> Decimal:
        total = Decimal("0")
        for i in range(self.div_deposit_count):
            val = self.div_deposit_interest(i)
            if val:
                total += val
        return total
