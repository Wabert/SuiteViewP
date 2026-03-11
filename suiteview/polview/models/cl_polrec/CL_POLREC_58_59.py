"""
CL_POLREC_58_59 — Target Records (Records 58, 59)
====================================================

DB2 tables
----------
Record 58 — Policy Targets
    LH_POL_TARGET        Policy-level target premiums/dates

Record 59 — Commission Targets / Guideline Premiums
    LH_COM_TARGET        Commission target premiums
    LH_COV_INS_GDL_PRM  Guideline premiums (GLP/GSP per coverage)
"""

from __future__ import annotations

from decimal import Decimal
from datetime import date
from typing import List, Optional

from .cyberlife_base import PolicyDataAccessor, parse_date
from .policy_data_classes import PolicyTargetInfo, GuidelinePremiumInfo


class TargetRecords:
    """System-layer access for target/guideline premium records."""

    TABLES = (
        "LH_POL_TARGET",
        "LH_COM_TARGET",
        "LH_COV_INS_GDL_PRM",
    )

    def __init__(self, policy: PolicyDataAccessor) -> None:
        self._policy = policy

    def invalidate(self) -> None:
        pass

    # =====================================================================
    # POLICY TARGETS (LH_POL_TARGET)
    # =====================================================================

    def _get_target_amount(self, TAR_TYP_CD: str) -> Optional[Decimal]:
        val = self._policy.data_item_where("LH_POL_TARGET", "TAR_PRM_AMT", "TAR_TYP_CD", TAR_TYP_CD)
        return Decimal(str(val)) if val is not None else None

    def _get_target_date(self, TAR_TYP_CD: str) -> Optional[date]:
        val = self._policy.data_item_where("LH_POL_TARGET", "TAR_DT", "TAR_TYP_CD", TAR_TYP_CD)
        return parse_date(val)

    @property
    def mtp(self) -> Optional[Decimal]:
        """Minimum Target Premium (MT)."""
        return self._get_target_amount("MT")

    @property
    def accumulated_mtp_target(self) -> Optional[Decimal]:
        """Accumulated MTP (MA)."""
        return self._get_target_amount("MA")

    @property
    def map_date(self) -> Optional[date]:
        """MAP (SafetyNet) cease date (MA)."""
        return self._get_target_date("MA")

    @property
    def accumulated_glp_target(self) -> Optional[Decimal]:
        """Accumulated GLP (TA)."""
        return self._get_target_amount("TA")

    @property
    def plt(self) -> Optional[Decimal]:
        """Premium Limit Target (LT)."""
        return self._get_target_amount("LT")

    @property
    def gav(self) -> Optional[Decimal]:
        """GAV from Index target (IX)."""
        return self._get_target_amount("IX")

    @property
    def dial_to_premium(self) -> Optional[Decimal]:
        """Dial-to premium (DT)."""
        return self._get_target_amount("DT")

    @property
    def nsp_base(self) -> Optional[Decimal]:
        """NSP Base (NS)."""
        return self._get_target_amount("NS")

    @property
    def nsp_other(self) -> Optional[Decimal]:
        """NSP Other (NT)."""
        return self._get_target_amount("NT")

    @property
    def short_pay_premium(self) -> Optional[Decimal]:
        """Short pay premium (VS)."""
        return self._get_target_amount("VS")

    @property
    def short_pay_date(self) -> Optional[date]:
        """Short pay billing cease date (VS)."""
        return self._get_target_date("VS")

    # =====================================================================
    # COMMISSION TARGETS (LH_COM_TARGET)
    # =====================================================================

    @property
    def ctp(self) -> Optional[Decimal]:
        """Commission Target Premium — sum of all CT entries."""
        amounts = self._policy.data_items_where("LH_COM_TARGET", "TAR_PRM_AMT", "TAR_TYP_CD", "CT")
        if not amounts:
            return None
        total = Decimal("0")
        for val in amounts:
            if val is not None:
                total += Decimal(str(val))
        return total if total > 0 else None

    # =====================================================================
    # GUIDELINE PREMIUMS (LH_COV_INS_GDL_PRM)
    # =====================================================================

    @property
    def glp(self) -> Optional[Decimal]:
        """Guideline Level Premium (PRM_RT_TYP_CD = 'A')."""
        val = self._policy.data_item_where("LH_COV_INS_GDL_PRM", "GDL_PRM_AMT", "PRM_RT_TYP_CD", "A")
        return Decimal(str(val)) if val is not None else None

    @property
    def gsp(self) -> Optional[Decimal]:
        """Guideline Single Premium (PRM_RT_TYP_CD = 'S')."""
        val = self._policy.data_item_where("LH_COV_INS_GDL_PRM", "GDL_PRM_AMT", "PRM_RT_TYP_CD", "S")
        return Decimal(str(val)) if val is not None else None

    def get_guideline_premiums(self) -> List[GuidelinePremiumInfo]:
        """Build GuidelinePremiumInfo objects from LH_COV_INS_GDL_PRM."""
        premiums: List[GuidelinePremiumInfo] = []
        for row in self._policy.fetch_table("LH_COV_INS_GDL_PRM"):
            rate_type = str(row.get("PRM_RT_TYP_CD", "") or "")
            desc = "GLP" if rate_type == "A" else "GSP" if rate_type == "S" else rate_type
            prem = GuidelinePremiumInfo(
                COV_PHA_NBR=int(row.get("COV_PHA_NBR", 0) or 0),
                PRM_RT_TYP_CD=rate_type,
                rate_type_desc=desc,
                GDL_PRM_AMT=Decimal(str(row["GDL_PRM_AMT"])) if row.get("GDL_PRM_AMT") else None,
                raw_data=row,
            )
            premiums.append(prem)
        return premiums
