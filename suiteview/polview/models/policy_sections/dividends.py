"""PolicyInformation dividends section.

Participation values live on CyberLife segments 12-15 and 19 (DB2 tables
``LH_PTP_ON_DEP``, ``LH_PAID_UP_ADD``, ``LH_ONE_YR_TRM_ADD``, ``LH_UNAPPLIED_PTP`` and
``LH_APPLIED_PTP``). Rows with ``MVRY_DT`` 12/31/9999 are current; other rows are
snapshots taken at an anniversary (``ANV_PRC_CRN_IND`` 1 = before that anniversary's
processing). Month-year numbers (``ERN_DT_MO_YR_NBR``, ``PUA_MT_MO_YR_NBR``...) count
months from January 1900: ``(year - 1900) * 12 + month``.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from typing import List, Optional, Tuple

from .base import PolicySection
from ..cl_polrec.policy_data_classes import AppliedDividendInfo
from ..cl_polrec.policy_data_classes import DivDepositInfo
from ..cl_polrec.policy_data_classes import DivOYTInfo
from ..cl_polrec.policy_data_classes import DivPUAInfo
from ..cl_polrec.policy_data_classes import UnappliedDividendInfo
from ..cl_polrec.policy_translations import DIV_OPTION_CODES
from ..cl_polrec.policy_translations import NFO_CODES


def decode_month_year(value) -> Tuple[Optional[int], Optional[int]]:
    """CyberLife MOYR number -> (year, month); ``(None, None)`` when blank or zero."""
    if value is None or str(value).strip() in ("", "0"):
        return None, None
    number = int(value)
    year, month = divmod(number, 12)
    if month == 0:
        return 1900 + year - 1, 12
    return 1900 + year, month


def _decimal(value) -> Decimal:
    return Decimal(str(value)) if value not in (None, "") else Decimal("0")


def _optional_decimal(value) -> Optional[Decimal]:
    return Decimal(str(value)) if value not in (None, "") else None


class DividendsSection(PolicySection):
    """Cohesive PolicyInformation dividends view."""

    CACHE_ATTRS = ()

    @property
    def div_option_code(self) -> str:
        """Primary dividend option code (LH_BAS_POL.PRI_DIV_OPT_CD)."""
        return str(self._field("div_option_code") or "0").strip() or "0"

    @property
    def div_option_description(self) -> str:
        """Dividend option description."""
        return DIV_OPTION_CODES.get(self.div_option_code, f"Unknown ({self.div_option_code})")

    @property
    def secondary_div_option_code(self) -> str:
        """Secondary dividend option code (LH_BAS_POL.DIV_2ND_OPT_CD); blank when absent."""
        return str(self._field("second_dividend_option") or "").strip()

    @property
    def nfo_code(self) -> str:
        """Non-forfeiture option code."""
        return str(self._field("nfo_code") or "0")

    @property
    def nfo_description(self) -> str:
        """Non-forfeiture option description."""
        return NFO_CODES.get(self.nfo_code, f"Unknown ({self.nfo_code})")

    # -- dividend values (segment 19) ---------------------------------------------

    def get_applied_dividends(self) -> List[AppliedDividendInfo]:
        """Applied participation values, newest earn date first."""
        rows = []
        for row in self.fetch_table("LH_APPLIED_PTP"):
            year, month = decode_month_year(row.get("ERN_DT_MO_YR_NBR"))
            rows.append(AppliedDividendInfo(
                coverage_phase=int(row.get("COV_PHA_NBR", 0) or 0),
                participation_type=str(row.get("CK_PTP_TYP_CD", "") or "").strip(),
                earn_year=year,
                earn_month=month,
                source=str(row.get("PTP_SRC_IND", "") or "").strip(),
                applied_option=str(row.get("APP_OPT_CD", "") or "").strip(),
                cash_per_unit=_decimal(row.get("CSH_AMT")),
                pua_per_unit=_decimal(row.get("PUA_AMT")),
                oyt_per_unit=_decimal(row.get("OYT_AMT")),
                units=_decimal(row.get("PUA_UNT_QTY")),
                raw_data=row,
            ))
        rows.sort(key=lambda r: (r.earn_year or 0, r.earn_month or 0), reverse=True)
        return rows

    def get_unapplied_dividends(self) -> List[UnappliedDividendInfo]:
        """Unapplied participation values, newest earn date first."""
        rows = []
        for row in self.fetch_table("LH_UNAPPLIED_PTP"):
            year, month = decode_month_year(row.get("ERN_DT_MO_YR_NBR"))
            rows.append(UnappliedDividendInfo(
                coverage_phase=int(row.get("COV_PHA_NBR", 0) or 0),
                participation_type=str(row.get("CK_PTP_TYP_CD", "") or "").strip(),
                earn_year=year,
                earn_month=month,
                source=str(row.get("PTP_SRC_IND", "") or "").strip(),
                rpu_values=str(row.get("RPU_VAL_IND", "") or "").strip() == "1",
                earn_rule=str(row.get("ERN_RLE_CD", "") or "").strip(),
                deposit_interest_rate=_optional_decimal(row.get("DEP_ITS_RT")),
                cash_per_unit=_decimal(row.get("CSH_AMT")),
                pua_per_unit=_decimal(row.get("PUA_AMT")),
                oyt_per_unit=_decimal(row.get("OYT_AMT")),
                projected_cash_per_unit=_optional_decimal(row.get("PRJ_CSH_AMT")),
                units=_decimal(row.get("PUA_UNT_QTY")),
                pua_mortality_table=str(row.get("PUA_MTL_TBL_CD", "") or "").strip(),
                pua_interest_rate=_optional_decimal(row.get("PUA_ITS_RT")),
                raw_data=row,
                direct_recognition=str(row.get("DIR_RCG_DIV_IND", "") or "").strip() == "1",
                gross_interest_rate=_optional_decimal(row.get("DIV_GRS_ITS_RT")),
            ))
        rows.sort(key=lambda r: (r.earn_year or 0, r.earn_month or 0), reverse=True)
        return rows

    # -- paid-up additions (segment 14) ---------------------------------------------

    def get_div_pua(self) -> List[DivPUAInfo]:
        """Every paid-up additions row, current and anniversary snapshots."""
        rows = []
        for row in self.fetch_table("LH_PAID_UP_ADD"):
            year, month = decode_month_year(row.get("PUA_MT_MO_YR_NBR"))
            rows.append(DivPUAInfo(
                coverage_phase=int(row.get("COV_PHA_NBR", 0) or 0),
                purchase_source=str(row.get("PUA_PUR_SRC_CD", "") or "").strip(),
                mv_date=self._parse_date(row.get("MVRY_DT")),
                before_anniversary=str(row.get("ANV_PRC_CRN_IND", "") or "").strip() == "1",
                maturity_year=year,
                maturity_month=month,
                nfo_code=str(row.get("PUA_NF_CD", "") or "").strip(),
                mortality_table=str(row.get("PUA_MTL_TBL_CD", "") or "").strip(),
                interest_rate=_optional_decimal(row.get("PUA_ITS_RT")),
                pua_class=str(row.get("PUA_CLS_CD", "") or "").strip(),
                amount=_decimal(row.get("PUA_AMT")),
                raw_data=row,
            ))
        return rows

    def current_puas(self) -> List[DivPUAInfo]:
        """Current paid-up additions rows (MVRY_DT 12/31/9999)."""
        return [row for row in self.get_div_pua() if row.is_current]

    @property
    def total_pua_amount(self) -> Decimal:
        """Current paid-up additions face, all coverage phases and sources."""
        return sum((row.amount for row in self.current_puas()), Decimal("0"))

    # -- one-year term additions (segment 15) --------------------------------------

    def get_div_oyt(self) -> List[DivOYTInfo]:
        """Every one-year term additions row, current and anniversary snapshots."""
        rows = []
        for row in self.fetch_table("LH_ONE_YR_TRM_ADD"):
            year, month = decode_month_year(row.get("OYT_EXP_MO_YR_NBR"))
            rows.append(DivOYTInfo(
                mv_date=self._parse_date(row.get("MVRY_DT")),
                before_anniversary=str(row.get("ANV_PRC_CRN_IND", "") or "").strip() == "1",
                expiry_year=year,
                expiry_month=month,
                nfo_code=str(row.get("OYT_ADD_NF_CD", "") or "").strip(),
                mortality_table=str(row.get("OYT_MTL_TBL_CD", "") or "").strip(),
                interest_rate=_optional_decimal(row.get("OYT_ITS_RT")),
                amount=_decimal(row.get("OYT_ADD_AMT")),
                raw_data=row,
            ))
        return rows

    def current_oyts(self) -> List[DivOYTInfo]:
        """Current one-year term additions rows (MVRY_DT 12/31/9999)."""
        return [row for row in self.get_div_oyt() if row.is_current]

    @property
    def total_oyt_amount(self) -> Decimal:
        """Current one-year term additions face."""
        return sum((row.amount for row in self.current_oyts()), Decimal("0"))

    # -- values on deposit (segments 12/13) ----------------------------------------

    def get_div_deposits(self) -> List[DivDepositInfo]:
        """Every deposit row, current and anniversary snapshots."""
        rows = []
        for row in self.fetch_table("LH_PTP_ON_DEP"):
            year, month = decode_month_year(row.get("ITS_APP_MO_YR_NBR"))
            rows.append(DivDepositInfo(
                participation_type=str(row.get("CK_PTP_TYP_CD", "") or "").strip(),
                mv_date=self._parse_date(row.get("MVRY_DT")),
                before_anniversary=str(row.get("ANV_PRC_CRN_IND", "") or "").strip() == "1",
                interest_applied_year=year,
                interest_applied_month=month,
                nfo_code=str(row.get("DEP_NF_CD", "") or "").strip(),
                interest_rate=_optional_decimal(row.get("DEP_ITS_RT")),
                deposit_amount=_decimal(row.get("PTP_DEP_AMT")),
                interest_amount=_decimal(row.get("DEP_ITS_AMT")),
                raw_data=row,
            ))
        return rows

    def current_deposits(self) -> List[DivDepositInfo]:
        """Current values on deposit (MVRY_DT 12/31/9999)."""
        return [row for row in self.get_div_deposits() if row.is_current]

    @property
    def total_div_deposit(self) -> Decimal:
        """Current dividends on deposit."""
        return sum((row.deposit_amount for row in self.current_deposits()), Decimal("0"))

    @property
    def total_div_interest(self) -> Decimal:
        """Interest on the current deposits not yet added to the deposit amount."""
        return sum((row.interest_amount for row in self.current_deposits()), Decimal("0"))

    @staticmethod
    def month_year_date(year: Optional[int], month: Optional[int], day: int) -> Optional[date]:
        """The date in a decoded month-year on the policy's anniversary ``day``."""
        if year is None or month is None:
            return None
        return date(year, month, min(day, calendar.monthrange(year, month)[1]))
