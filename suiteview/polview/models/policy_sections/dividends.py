"""PolicyInformation dividends section."""

from __future__ import annotations

from .base import PolicySection
from ..cl_polrec.policy_data_classes import AppliedDividendInfo
from ..cl_polrec.policy_data_classes import DivDepositInfo
from ..cl_polrec.policy_data_classes import DivOYTInfo
from ..cl_polrec.policy_data_classes import DivPUAInfo
from ..cl_polrec.policy_data_classes import UnappliedDividendInfo
from ..cl_polrec.policy_translations import DIV_OPTION_CODES
from ..cl_polrec.policy_translations import NFO_CODES
from ..cl_polrec.policy_translations import translate_div_type_code
from datetime import date
from decimal import Decimal
from typing import List
from typing import Optional


class DividendsSection(PolicySection):
    """Cohesive PolicyInformation dividends view."""

    CACHE_ATTRS = ()

    @property
    def div_option_code(self) -> str:
        """Dividend option code."""
        return str(self._field("div_option_code") or "0")

    @property
    def div_option_description(self) -> str:
        """Dividend option description."""
        return DIV_OPTION_CODES.get(self.div_option_code, f"Unknown ({self.div_option_code})")

    @property
    def nfo_code(self) -> str:
        """Non-forfeiture option code."""
        return str(self._field("nfo_code") or "0")

    @property
    def nfo_description(self) -> str:
        """Non-forfeiture option description."""
        return NFO_CODES.get(self.nfo_code, f"Unknown ({self.nfo_code})")

    def get_applied_dividends(self) -> List[AppliedDividendInfo]:
        """Get applied dividend records."""
        dividends = []
        for row in self.fetch_table("LH_APPLIED_PTP"):
            div_type = str(row.get("PTP_APL_TYP_CD", "") or "")
            div = AppliedDividendInfo(
                dividend_date=self._parse_date(row.get("PTP_APL_DT")),
                dividend_type=div_type,
                dividend_type_desc=translate_div_type_code(div_type),
                gross_amount=Decimal(str(row["PTP_GRS_AMT"])) if row.get("PTP_GRS_AMT") else None,
                net_amount=Decimal(str(row["PTP_NET_AMT"])) if row.get("PTP_NET_AMT") else None,
                year=int(row["POL_DUR_NBR"]) if row.get("POL_DUR_NBR") else None,
                raw_data=row
            )
            dividends.append(div)
        return dividends

    @property
    def applied_div_count(self) -> int:
        """Count of applied dividend records."""
        return self.data_item_count("LH_APPLIED_PTP")

    def applied_div_date(self, index: int) -> Optional[date]:
        """Get applied dividend date (0-based index)."""
        return self._parse_date(self.data_item("LH_APPLIED_PTP", "PTP_APL_DT", index))

    def applied_div_type(self, index: int) -> str:
        """Get applied dividend type code (0-based index)."""
        return str(self.data_item("LH_APPLIED_PTP", "PTP_APL_TYP_CD", index) or "")

    def applied_div_gross_amount(self, index: int) -> Optional[Decimal]:
        """Get applied dividend gross amount (0-based index)."""
        val = self.data_item("LH_APPLIED_PTP", "PTP_GRS_AMT", index)
        return Decimal(str(val)) if val else None

    def applied_div_net_amount(self, index: int) -> Optional[Decimal]:
        """Get applied dividend net amount (0-based index)."""
        val = self.data_item("LH_APPLIED_PTP", "PTP_NET_AMT", index)
        return Decimal(str(val)) if val else None

    def applied_div_year(self, index: int) -> Optional[int]:
        """Get applied dividend policy year (0-based index)."""
        val = self.data_item("LH_APPLIED_PTP", "POL_DUR_NBR", index)
        return int(val) if val else None

    def get_unapplied_dividends(self) -> List[UnappliedDividendInfo]:
        """Get unapplied dividend records."""
        dividends = []
        for row in self.fetch_table("LH_UNAPPLIED_PTP"):
            div_type = str(row.get("PTP_TYP_CD", "") or "")
            div = UnappliedDividendInfo(
                dividend_date=self._parse_date(row.get("PTP_PRO_DT")),
                dividend_type=div_type,
                dividend_type_desc=translate_div_type_code(div_type),
                gross_amount=Decimal(str(row["PTP_GRS_AMT"])) if row.get("PTP_GRS_AMT") else None,
                net_amount=Decimal(str(row["PTP_NET_AMT"])) if row.get("PTP_NET_AMT") else None,
                year=int(row["POL_DUR_NBR"]) if row.get("POL_DUR_NBR") else None,
                raw_data=row
            )
            dividends.append(div)
        return dividends

    @property
    def unapplied_div_count(self) -> int:
        """Count of unapplied dividend records."""
        return self.data_item_count("LH_UNAPPLIED_PTP")

    def unapplied_div_date(self, index: int) -> Optional[date]:
        """Get unapplied dividend date (0-based index)."""
        return self._parse_date(self.data_item("LH_UNAPPLIED_PTP", "PTP_PRO_DT", index))

    def unapplied_div_type(self, index: int) -> str:
        """Get unapplied dividend type code (0-based index)."""
        return str(self.data_item("LH_UNAPPLIED_PTP", "PTP_TYP_CD", index) or "")

    def unapplied_div_gross_amount(self, index: int) -> Optional[Decimal]:
        """Get unapplied dividend gross amount (0-based index)."""
        val = self.data_item("LH_UNAPPLIED_PTP", "PTP_GRS_AMT", index)
        return Decimal(str(val)) if val else None

    def unapplied_div_net_amount(self, index: int) -> Optional[Decimal]:
        """Get unapplied dividend net amount (0-based index)."""
        val = self.data_item("LH_UNAPPLIED_PTP", "PTP_NET_AMT", index)
        return Decimal(str(val)) if val else None

    def unapplied_div_year(self, index: int) -> Optional[int]:
        """Get unapplied dividend policy year (0-based index)."""
        val = self.data_item("LH_UNAPPLIED_PTP", "POL_DUR_NBR", index)
        return int(val) if val else None

    def get_div_oyt(self) -> List[DivOYTInfo]:
        """Get one year term dividend addition records."""
        oyts = []
        for row in self.fetch_table("LH_ONE_YR_TRM_ADD"):
            oyt = DivOYTInfo(
                coverage_phase=int(row.get("COV_PHA_NBR", 0) or 0),
                issue_date=self._parse_date(row.get("OYT_ISS_DT")),
                face_amount=Decimal(str(row["OYT_FCE_AMT"])) if row.get("OYT_FCE_AMT") else None,
                csv_amount=Decimal(str(row["OYT_CSV_AMT"])) if row.get("OYT_CSV_AMT") else None,
                raw_data=row
            )
            oyts.append(oyt)
        return oyts

    @property
    def div_oyt_count(self) -> int:
        """Count of OYT records."""
        return self.data_item_count("LH_ONE_YR_TRM_ADD")

    def div_oyt_cov_phase(self, index: int) -> int:
        """Get OYT coverage phase (0-based index)."""
        val = self.data_item("LH_ONE_YR_TRM_ADD", "COV_PHA_NBR", index)
        return int(val) if val else 0

    def div_oyt_issue_date(self, index: int) -> Optional[date]:
        """Get OYT issue date (0-based index)."""
        return self._parse_date(self.data_item("LH_ONE_YR_TRM_ADD", "OYT_ISS_DT", index))

    def div_oyt_face_amount(self, index: int) -> Optional[Decimal]:
        """Get OYT face amount (0-based index)."""
        val = self.data_item("LH_ONE_YR_TRM_ADD", "OYT_FCE_AMT", index)
        return Decimal(str(val)) if val else None

    def div_oyt_csv(self, index: int) -> Optional[Decimal]:
        """Get OYT cash surrender value (0-based index)."""
        val = self.data_item("LH_ONE_YR_TRM_ADD", "OYT_CSV_AMT", index)
        return Decimal(str(val)) if val else None

    @property
    def total_oyt_face(self) -> Decimal:
        """Total OYT face amount."""
        total = Decimal("0")
        for i in range(self.div_oyt_count):
            val = self.div_oyt_face_amount(i)
            if val:
                total += val
        return total

    @property
    def total_oyt_csv(self) -> Decimal:
        """Total OYT cash surrender value."""
        total = Decimal("0")
        for i in range(self.div_oyt_count):
            val = self.div_oyt_csv(i)
            if val:
                total += val
        return total

    def get_div_pua(self) -> List[DivPUAInfo]:
        """Get paid-up addition records."""
        puas = []
        for row in self.fetch_table("LH_PAID_UP_ADD"):
            pua = DivPUAInfo(
                coverage_phase=int(row.get("COV_PHA_NBR", 0) or 0),
                issue_date=self._parse_date(row.get("PUA_ISS_DT")),
                face_amount=Decimal(str(row["PUA_FCE_AMT"])) if row.get("PUA_FCE_AMT") else None,
                csv_amount=Decimal(str(row["PUA_CSV_AMT"])) if row.get("PUA_CSV_AMT") else None,
                raw_data=row
            )
            puas.append(pua)
        return puas

    @property
    def div_pua_count(self) -> int:
        """Count of PUA records."""
        return self.data_item_count("LH_PAID_UP_ADD")

    def div_pua_cov_phase(self, index: int) -> int:
        """Get PUA coverage phase (0-based index)."""
        val = self.data_item("LH_PAID_UP_ADD", "COV_PHA_NBR", index)
        return int(val) if val else 0

    def div_pua_issue_date(self, index: int) -> Optional[date]:
        """Get PUA issue date (0-based index)."""
        return self._parse_date(self.data_item("LH_PAID_UP_ADD", "PUA_ISS_DT", index))

    def div_pua_face_amount(self, index: int) -> Optional[Decimal]:
        """Get PUA face amount (0-based index)."""
        val = self.data_item("LH_PAID_UP_ADD", "PUA_FCE_AMT", index)
        return Decimal(str(val)) if val else None

    def div_pua_csv(self, index: int) -> Optional[Decimal]:
        """Get PUA cash surrender value (0-based index)."""
        val = self.data_item("LH_PAID_UP_ADD", "PUA_CSV_AMT", index)
        return Decimal(str(val)) if val else None

    @property
    def total_pua_face(self) -> Decimal:
        """Total PUA face amount."""
        total = Decimal("0")
        for i in range(self.div_pua_count):
            val = self.div_pua_face_amount(i)
            if val:
                total += val
        return total

    @property
    def total_pua_csv(self) -> Decimal:
        """Total PUA cash surrender value."""
        total = Decimal("0")
        for i in range(self.div_pua_count):
            val = self.div_pua_csv(i)
            if val:
                total += val
        return total

    def get_div_deposits(self) -> List[DivDepositInfo]:
        """Get dividend on deposit records."""
        deposits = []
        for row in self.fetch_table("LH_PTP_ON_DEP"):
            dep_type = str(row.get("PTP_TYP_CD", "") or "")
            dep = DivDepositInfo(
                deposit_date=self._parse_date(row.get("DEP_DT")),
                deposit_type=dep_type,
                deposit_type_desc=translate_div_type_code(dep_type),
                deposit_amount=Decimal(str(row["CUM_DEP_AMT"])) if row.get("CUM_DEP_AMT") else None,
                interest_amount=Decimal(str(row["ITS_AMT"])) if row.get("ITS_AMT") else None,
                raw_data=row
            )
            deposits.append(dep)
        return deposits

    @property
    def div_deposit_count(self) -> int:
        """Count of dividend deposit records."""
        return self.data_item_count("LH_PTP_ON_DEP")

    def div_deposit_date(self, index: int) -> Optional[date]:
        """Get dividend deposit date (0-based index)."""
        return self._parse_date(self.data_item("LH_PTP_ON_DEP", "DEP_DT", index))

    def div_deposit_type(self, index: int) -> str:
        """Get dividend deposit type code (0-based index)."""
        return str(self.data_item("LH_PTP_ON_DEP", "PTP_TYP_CD", index) or "")

    def div_deposit_amount(self, index: int) -> Optional[Decimal]:
        """Get cumulative dividend deposit amount (0-based index)."""
        val = self.data_item("LH_PTP_ON_DEP", "CUM_DEP_AMT", index)
        return Decimal(str(val)) if val else None

    def div_deposit_interest(self, index: int) -> Optional[Decimal]:
        """Get dividend deposit interest amount (0-based index)."""
        val = self.data_item("LH_PTP_ON_DEP", "ITS_AMT", index)
        return Decimal(str(val)) if val else None

    @property
    def total_div_deposit(self) -> Decimal:
        """Total dividend deposits."""
        total = Decimal("0")
        for i in range(self.div_deposit_count):
            val = self.div_deposit_amount(i)
            if val:
                total += val
        return total

    @property
    def total_div_interest(self) -> Decimal:
        """Total dividend deposit interest."""
        total = Decimal("0")
        for i in range(self.div_deposit_count):
            val = self.div_deposit_interest(i)
            if val:
                total += val
        return total
