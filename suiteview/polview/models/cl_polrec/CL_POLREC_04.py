"""
CL_POLREC_04 — Benefit Records (Record 04)
============================================

DB2 tables
----------
    LH_SPM_BNF          Supplemental benefit rows
    LH_BNF_INS_RNL_RT   Benefit renewal rates
"""

from __future__ import annotations

from decimal import Decimal
from datetime import date
from typing import Any, Dict, List, Optional

from .cyberlife_base import PolicyDataAccessor, parse_date
from .policy_data_classes import BenefitInfo, RenewalBenRateInfo
from .policy_translations import (
    RATE_CLASS_CODES,
    translate_renewal_rate_type_code,
)


class BenefitRecords:
    """System-layer access for benefit Cyberlife policy records."""

    TABLES = (
        "LH_SPM_BNF",
        "LH_BNF_INS_RNL_RT",
    )

    def __init__(self, policy: PolicyDataAccessor) -> None:
        self._policy = policy
        self._benefits: Optional[List[BenefitInfo]] = None

    def invalidate(self) -> None:
        self._benefits = None

    # =====================================================================
    # BENEFITS (LH_SPM_BNF)
    # =====================================================================

    @property
    def benefit_count(self) -> int:
        return self._policy.data_item_count("LH_SPM_BNF")

    def get_benefits(self, COV_PHA_NBR: Optional[int] = None) -> List[BenefitInfo]:
        """Build BenefitInfo objects from LH_SPM_BNF rows."""
        if self._benefits is None:
            self._benefits = []
            for row in self._policy.fetch_table("LH_SPM_BNF"):
                type_cd = str(row.get("SPM_BNF_TYP_CD", "")).strip()
                subtype_cd = str(row.get("SPM_BNF_SBY_CD", "")).strip()
                benefit_code = type_cd + subtype_cd

                units = Decimal(str(row["BNF_UNT_QTY"])) if row.get("BNF_UNT_QTY") else None
                vpu = Decimal(str(row["BNF_VPU_AMT"])) if row.get("BNF_VPU_AMT") else None
                benefit_amount = (units * vpu) if (units is not None and vpu is not None) else None

                ben = BenefitInfo(
                    COV_PHA_NBR=int(row.get("COV_PHA_NBR", 0)),
                    benefit_code=benefit_code,
                    SPM_BNF_TYP_CD=type_cd,
                    SPM_BNF_SBY_CD=subtype_cd,
                    benefit_desc=type_cd,
                    BNF_FRM_NBR=str(row.get("BNF_FRM_NBR", "")).strip(),
                    issue_date=parse_date(row.get("BNF_ISS_DT")),
                    cease_date=parse_date(row.get("BNF_CEA_DT")),
                    orig_cease_date=parse_date(row.get("BNF_OGN_CEA_DT")),
                    BNF_UNT_QTY=units,
                    BNF_VPU_AMT=vpu,
                    benefit_amount=benefit_amount,
                    BNF_ISS_AGE=int(row["BNF_ISS_AGE"]) if row.get("BNF_ISS_AGE") else None,
                    BNF_RT_FCT=Decimal(str(row["BNF_RT_FCT"])) if row.get("BNF_RT_FCT") else None,
                    RNL_RT_IND=str(row.get("RNL_RT_IND", "")).strip(),
                    BNF_ANN_PPU_AMT=Decimal(str(row["BNF_ANN_PPU_AMT"])) if row.get("BNF_ANN_PPU_AMT") else None,
                    raw_data=row,
                )
                self._benefits.append(ben)

        if COV_PHA_NBR is not None:
            return [b for b in self._benefits if b.COV_PHA_NBR == COV_PHA_NBR]
        return self._benefits

    def ben_value_by_name(self, plancode: str, FIELD_NAME: str) -> Any:
        """Get raw field value for benefit matching plancode (type+subtype)."""
        for ben in self.get_benefits():
            if ben.benefit_code == plancode:
                return ben.raw_data.get(FIELD_NAME.upper())
        return None

    # =====================================================================
    # BENEFIT RENEWAL RATES (LH_BNF_INS_RNL_RT)
    # =====================================================================

    def get_benefit_renewal_rates(self, COV_PHA_NBR: Optional[int] = None) -> List[RenewalBenRateInfo]:
        rates: List[RenewalBenRateInfo] = []
        for row in self._policy.fetch_table("LH_BNF_INS_RNL_RT"):
            phase = int(row.get("COV_PHA_NBR", 0) or 0)
            if COV_PHA_NBR is not None and phase != COV_PHA_NBR:
                continue
            rate_type = str(row.get("PRM_RT_TYP_CD", "") or "")
            rate = RenewalBenRateInfo(
                COV_PHA_NBR=phase,
                SPM_BNF_TYP_CD=str(row.get("SPM_BNF_TYP_CD", "") or ""),
                SPM_BNF_SBY_CD=str(row.get("SPM_BNF_SBY_CD", "") or ""),
                rate_type=rate_type,
                rate_type_desc=translate_renewal_rate_type_code(rate_type),
                JT_INS_IND=str(row.get("JT_INS_IND", "") or ""),
                rate_class=str(row.get("RT_CLS_CD", "") or ""),
                issue_age=int(row["ISS_AGE"]) if row.get("ISS_AGE") else None,
                raw_data=row,
            )
            rates.append(rate)
        return rates

    @property
    def renewal_ben_count(self) -> int:
        return self._policy.data_item_count("LH_BNF_INS_RNL_RT")

    def ben_renewal_index(self, COV_PHA_NBR: int, ben_type: str, ben_subtype: str,
                          rate_type: str = "C", joint_ind: str = "0") -> int:
        for i in range(self.renewal_ben_count):
            if (int(self._policy.data_item("LH_BNF_INS_RNL_RT", "COV_PHA_NBR", i) or 0) == COV_PHA_NBR
                    and str(self._policy.data_item("LH_BNF_INS_RNL_RT", "SPM_BNF_TYP_CD", i) or "") == ben_type
                    and str(self._policy.data_item("LH_BNF_INS_RNL_RT", "SPM_BNF_SBY_CD", i) or "") == ben_subtype
                    and str(self._policy.data_item("LH_BNF_INS_RNL_RT", "PRM_RT_TYP_CD", i) or "") == rate_type
                    and str(self._policy.data_item("LH_BNF_INS_RNL_RT", "JT_INS_IND", i) or "") == joint_ind):
                return i
        return -1

    def renewal_ben_rateclass(self, index: int) -> str:
        return str(self._policy.data_item("LH_BNF_INS_RNL_RT", "RT_CLS_CD", index) or "")

    def renewal_ben_issue_age(self, index: int) -> Optional[int]:
        val = self._policy.data_item("LH_BNF_INS_RNL_RT", "ISS_AGE", index)
        return int(val) if val else None
