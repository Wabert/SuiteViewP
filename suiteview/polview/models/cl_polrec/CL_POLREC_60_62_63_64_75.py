"""
CL_POLREC_60_62_63_64_75 — Total / MV Records (Records 60, 62-64, 75)
========================================================================

DB2 tables
----------
Record 60 — Policy Totals
    LH_POL_TOTALS        Lifetime totals (premiums, withdrawals, cost basis)
    LH_POL_YR_TOT        Year-to-date totals

Record 62 — Monthliversary Values (Traditional)
    LH_POL_MVRY_VAL      Traditional MV values (CSV, DB, NAR)

Record 63 — Monthliversary Values (Advanced)
    TH_POL_MVRY_VAL      Advanced (UL/VUL) MV values (AV, CSV, DB)

Record 64 — TAMRA/MEC
    LH_TAMRA_MEC_PRM     MEC indicator
    LH_TAMRA_7_PY_PER    7-pay period info
    LH_TAMRA_7_PY_YR     7-pay year details

Record 75 — Policy Year Totals
    LH_POL_YR_TOT        Year-to-date premium totals
"""

from __future__ import annotations

from decimal import Decimal
from datetime import date
from typing import List, Optional

from .cyberlife_base import PolicyDataAccessor, parse_date
from .policy_data_classes import MVValueInfo


class TotalRecords:
    """System-layer access for totals, MV values, and TAMRA/MEC records."""

    TABLES = (
        "LH_POL_TOTALS",
        "LH_POL_YR_TOT",
        "LH_POL_MVRY_VAL",
        "TH_POL_MVRY_VAL",
        "LH_TAMRA_MEC_PRM",
        "LH_TAMRA_7_PY_PER",
        "LH_TAMRA_7_PY_YR",
    )

    def __init__(self, policy: PolicyDataAccessor) -> None:
        self._policy = policy

    def invalidate(self) -> None:
        pass

    # =====================================================================
    # ACCUMULATOR PROPERTIES (LH_POL_TOTALS)
    # =====================================================================

    @property
    def TOT_REG_PRM_AMT(self) -> Decimal:
        val = self._policy.data_item("LH_POL_TOTALS", "TOT_REG_PRM_AMT")
        return Decimal(str(val)) if val is not None else Decimal("0")

    @property
    def TOT_ADD_PRM_AMT(self) -> Decimal:
        val = self._policy.data_item("LH_POL_TOTALS", "TOT_ADD_PRM_AMT")
        return Decimal(str(val)) if val is not None else Decimal("0")

    @property
    def premium_td(self) -> Decimal:
        return self.TOT_REG_PRM_AMT + self.TOT_ADD_PRM_AMT

    @property
    def TOT_WTD_AMT(self) -> Decimal:
        val = self._policy.data_item("LH_POL_TOTALS", "TOT_WTD_AMT")
        return Decimal(str(val)) if val is not None else Decimal("0")

    @property
    def POL_CST_BSS_AMT(self) -> Decimal:
        val = self._policy.data_item("LH_POL_TOTALS", "POL_CST_BSS_AMT")
        return Decimal(str(val)) if val is not None else Decimal("0")

    @property
    def policy_totals_count(self) -> int:
        return self._policy.data_item_count("LH_POL_TOTALS")

    # Year-to-date from LH_POL_YR_TOT
    @property
    def total_regular_premium_ytd(self) -> Decimal:
        count = self._policy.data_item_count("LH_POL_YR_TOT")
        if count == 0:
            return Decimal("0")
        val = self._policy.data_item("LH_POL_YR_TOT", "YTD_TOT_PMT_AMT", count - 1)
        return Decimal(str(val)) if val is not None else Decimal("0")

    @property
    def total_additional_premium_ytd(self) -> Decimal:
        count = self._policy.data_item_count("LH_POL_YR_TOT")
        if count == 0:
            return Decimal("0")
        val = self._policy.data_item("LH_POL_YR_TOT", "YTD_ADD_PRM_AMT", count - 1)
        return Decimal(str(val)) if val is not None else Decimal("0")

    @property
    def premium_ytd(self) -> Decimal:
        return self.total_regular_premium_ytd + self.total_additional_premium_ytd

    # =====================================================================
    # CASH VALUE / MV PROPERTIES
    # =====================================================================

    @property
    def CSH_SUR_VAL_AMT(self) -> Optional[Decimal]:
        """Current CSV — try advanced first, then traditional."""
        val = self._policy.data_item("TH_POL_MVRY_VAL", "CSV_AMT")
        if val is None:
            val = self._policy.data_item("LH_POL_MVRY_VAL", "CSV_AMT")
        return Decimal(str(val)) if val is not None else None

    @property
    def ACC_VAL_AMT(self) -> Optional[Decimal]:
        """Accumulation value (UL) — try advanced first, then traditional."""
        val = self._policy.data_item("TH_POL_MVRY_VAL", "ACC_VAL_AMT")
        if val is None:
            val = self._policy.data_item("LH_POL_MVRY_VAL", "ACC_VAL_AMT")
        return Decimal(str(val)) if val is not None else None

    @property
    def DTH_BNF_AMT(self) -> Optional[Decimal]:
        """DTH_BNF_AMT does not exist on TH/LH_POL_MVRY_VAL.
        Death benefit is derived from face amount + fund values."""
        return None

    @property
    def NET_AMT_RSK(self) -> Optional[Decimal]:
        val = self._policy.data_item("TH_POL_MVRY_VAL", "NET_AMT_RSK")
        return Decimal(str(val)) if val is not None else None

    # =====================================================================
    # MV DETAIL (LH_POL_MVRY_VAL)
    # =====================================================================

    @property
    def mv_count(self) -> int:
        return self._policy.data_item_count("LH_POL_MVRY_VAL")

    def mv_date(self, index: int = 0) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_POL_MVRY_VAL", "MVRY_DT", index))

    def mv_av(self, index: int = 0) -> Optional[Decimal]:
        val = self._policy.data_item("LH_POL_MVRY_VAL", "CSV_AMT", index)
        return Decimal(str(val)) if val is not None else None

    def mv_coi_charge(self, index: int = 0) -> Decimal:
        val = self._policy.data_item("LH_POL_MVRY_VAL", "CINS_AMT", index)
        return Decimal(str(val)) if val else Decimal("0")

    def mv_expense_charge(self, index: int = 0) -> Decimal:
        val = self._policy.data_item("LH_POL_MVRY_VAL", "EXP_CRG_AMT", index)
        return Decimal(str(val)) if val else Decimal("0")

    def mv_other_charge(self, index: int = 0) -> Decimal:
        val = self._policy.data_item("LH_POL_MVRY_VAL", "OTH_PRM_AMT", index)
        return Decimal(str(val)) if val else Decimal("0")

    def mv_monthly_deduction(self, index: int = 0) -> Decimal:
        return self.mv_coi_charge(index) + self.mv_expense_charge(index) + self.mv_other_charge(index)

    def mv_nar(self, index: int = 0) -> Decimal:
        val = self._policy.data_item("LH_POL_MVRY_VAL", "NAR_AMT", index)
        return Decimal(str(val)) if val else Decimal("0")

    @property
    def mv_policy_year(self) -> Optional[int]:
        val = self._policy.data_item("LH_POL_MVRY_VAL", "POL_DUR_NBR")
        return int(val) if val else None

    # =====================================================================
    # TAMRA / MEC (LH_TAMRA_*)
    # =====================================================================

    @property
    def is_mec(self) -> bool:
        """MEC_IND does not exist on LH_TAMRA_MEC_PRM.
        Use MEC_STA_CD on LH_TAMRA_7_PY_PER instead."""
        return self.mec_indicator in ("M", "1")

    @property
    def seven_pay_premium(self) -> Optional[Decimal]:
        val = self._policy.data_item("LH_TAMRA_7_PY_PER", "SEVN_PY_LVL_PRM_AMT")
        return Decimal(str(val)) if val is not None else None

    @property
    def accumulated_glp(self) -> Optional[Decimal]:
        val = self._policy.data_item("LH_TAMRA_7_PY_YR", "ACC_GLP_AMT")
        return Decimal(str(val)) if val is not None else None

    @property
    def accumulated_mtp(self) -> Optional[Decimal]:
        val = self._policy.data_item("LH_TAMRA_7_PY_YR", "ACC_MTP_AMT")
        return Decimal(str(val)) if val is not None else None

    @property
    def tamra_7pay_level(self) -> Optional[Decimal]:
        val = self._policy.data_item("LH_TAMRA_7_PY_PER", "SVPY_LVL_PRM_AMT")
        return Decimal(str(val)) if val else None

    @property
    def tamra_7pay_start_date(self) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_TAMRA_7_PY_PER", "SVPY_PER_STR_DT"))

    @property
    def tamra_7pay_av(self) -> Optional[Decimal]:
        val = self._policy.data_item("LH_TAMRA_7_PY_PER", "SVPY_BEG_CSV_AMT")
        return Decimal(str(val)) if val else None

    @property
    def tamra_7pay_specified_amount(self) -> Optional[Decimal]:
        val = self._policy.data_item("LH_TAMRA_7_PY_PER", "SVPY_BEG_FCE_AMT")
        return Decimal(str(val)) if val else None

    @property
    def mec_indicator(self) -> str:
        return str(self._policy.data_item("LH_TAMRA_7_PY_PER", "MEC_STA_CD") or "")

    @property
    def count_1035_payments(self) -> int:
        val = self._policy.data_item("LH_TAMRA_7_PY_PER", "XCG_1035_PMT_QTY")
        return int(val) if val else 0

    def tamra_7pay_premium_paid(self, year: int) -> Optional[Decimal]:
        if year < 1 or year > 7:
            return None
        val = self._policy.data_item("LH_TAMRA_7_PY_YR", "SVPY_PRM_PAY_AMT", year - 1)
        return Decimal(str(val)) if val else None

    def tamra_7pay_withdrawals(self, year: int) -> Optional[Decimal]:
        if year < 1 or year > 7:
            return None
        val = self._policy.data_item("LH_TAMRA_7_PY_YR", "SVPY_WTD_AMT", year - 1)
        return Decimal(str(val)) if val else None
