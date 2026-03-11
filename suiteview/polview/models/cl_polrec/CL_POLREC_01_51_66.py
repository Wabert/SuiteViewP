"""
CL_POLREC_01_51_66 — Base Policy Records (01, 51, 66)
=======================================================

DB2 tables
----------
Record 01 — Base Policy
    LH_BAS_POL          Primary policy header
    TH_BAS_POL          Tracking header (UL/VUL/IUL extras)

Record 51 — Non-Traditional Policy
    LH_NON_TRD_POL      Non-trad (UL/VUL/IUL) policy fields

Record 66 — Traditional Policy
    LH_TRD_POL           Traditional (WL/Term) policy fields
"""

from __future__ import annotations

from decimal import Decimal
from datetime import date
from typing import Any, Dict, Optional

from .cyberlife_base import PolicyDataAccessor, parse_date
from .policy_data_classes import BillingInfo, UserFieldInfo
from .policy_translations import (
    STATUS_CODES,
    SUSPENSE_CODES,
    PREMIUM_PAY_STATUS_CODES,
    COMPANY_CODES,
    PRODUCT_LINE_CODES,
    BILLING_MODE_CODES,
    DIV_OPTION_CODES,
    NFO_CODES,
    DB_OPTION_CODES,
    DEF_OF_LIFE_INS_CODES,
    NON_STANDARD_BILL_MODE_CODES,
    translate_state_code,
    translate_market_org,
)


class BasePolicyRecords:
    """System-layer access for base policy Cyberlife records.

    Parameters
    ----------
    policy : PolicyDataAccessor
        Object satisfying the data-access protocol.
    """

    TABLES = (
        "LH_BAS_POL",
        "TH_BAS_POL",
        "LH_NON_TRD_POL",
        "LH_TRD_POL",
    )

    def __init__(self, policy: PolicyDataAccessor) -> None:
        self._policy = policy

    def invalidate(self) -> None:
        """No local caches to clear."""
        pass

    # =====================================================================
    # STATUS
    # =====================================================================

    @property
    def STS_CD(self) -> str:
        return str(self._policy.data_item("LH_BAS_POL", "POL_STS_CD") or "")

    @property
    def status_description(self) -> str:
        return STATUS_CODES.get(self.STS_CD, f"Unknown ({self.STS_CD})")

    @property
    def SUS_CD(self) -> str:
        return str(self._policy.data_item("LH_BAS_POL", "SUS_CD") or "0")

    @property
    def suspense_description(self) -> str:
        return SUSPENSE_CODES.get(self.SUS_CD, f"Unknown ({self.SUS_CD})")

    @property
    def PRM_PAY_STA_REA_CD(self) -> str:
        return str(self._policy.data_item("LH_BAS_POL", "PRM_PAY_STA_REA_CD") or "")

    @property
    def premium_pay_status_description(self) -> str:
        return PREMIUM_PAY_STATUS_CODES.get(self.PRM_PAY_STA_REA_CD, f"Unknown ({self.PRM_PAY_STA_REA_CD})")

    @property
    def is_active(self) -> bool:
        return self.STS_CD in ("10", "14", "15")

    @property
    def is_suspended(self) -> bool:
        return self.STS_CD == "20"

    @property
    def is_terminated(self) -> bool:
        return self.STS_CD not in ("10", "14", "15", "20")

    @property
    def GRC_IND(self) -> bool:
        """Grace indicator — field does not exist on LH_BAS_POL.
        Grace status is determined via in_grace() / GRA_PER_EXP_DT instead."""
        return False

    # =====================================================================
    # DATES
    # =====================================================================

    @property
    def ISSUE_DT(self) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_COV_PHA", "ISSUE_DT"))

    @property
    def PAID_TO_DT(self) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_BAS_POL", "PRM_PAID_TO_DT"))

    @property
    def NXT_ANV_DT(self) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_BAS_POL", "NXT_YR_END_PRC_DT"))

    @property
    def NXT_MVRY_DT(self) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_BAS_POL", "NXT_MVRY_PRC_DT"))


    @property
    def TMN_DT(self) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_BAS_POL", "PLN_TMN_DT"))

    @property
    def LST_ANV_DT(self) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_BAS_POL", "LST_ANV_DT"))

    @property
    def NXT_MVRY_PRC_DT(self) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_BAS_POL", "NXT_MVRY_PRC_DT"))

    @property
    def LST_FIN_DT(self) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_BAS_POL", "LST_FIN_DT"))

    @property
    def NXT_BIL_DT(self) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_BAS_POL", "NXT_BIL_DT"))

    @property
    def PRM_BILL_TO_DT(self) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_BAS_POL", "PRM_BILL_TO_DT"))

    # =====================================================================
    # BILLING
    # =====================================================================

    @property
    def PMT_FQY_PER(self) -> int:
        return int(self._policy.data_item("LH_BAS_POL", "PMT_FQY_PER") or 0)

    @property
    def billing_mode_desc(self) -> str:
        nsd = str(self._policy.data_item("LH_BAS_POL", "NSD_MD_CD") or "")
        if nsd in NON_STANDARD_BILL_MODE_CODES:
            return NON_STANDARD_BILL_MODE_CODES[nsd]
        return BILLING_MODE_CODES.get(self.PMT_FQY_PER, f"{self.PMT_FQY_PER} months")

    @property
    def BL_DAY_NBR(self) -> int:
        return int(self._policy.data_item("LH_BAS_POL", "BIL_DAY_NBR") or 0)

    @property
    def ISSUE_ST_CD(self) -> str:
        return str(self._policy.data_item("LH_BAS_POL", "POL_ISS_ST_CD") or "")

    @property
    def issue_state(self) -> str:
        code = self.ISSUE_ST_CD
        if code and code.isdigit():
            return translate_state_code(int(code))
        return code

    @property
    def PRM_PAY_ST_CD(self) -> str:
        return str(self._policy.data_item("LH_BAS_POL", "PRM_PAY_ST_CD") or "")

    @property
    def resident_state(self) -> str:
        code = self.PRM_PAY_ST_CD
        if code and code.isdigit():
            return translate_state_code(int(code))
        return code

    # =====================================================================
    # PREMIUMS
    # =====================================================================

    @property
    def POL_PRM_AMT(self) -> Optional[Decimal]:
        val = self._policy.data_item("LH_BAS_POL", "POL_PRM_AMT")
        return Decimal(str(val)) if val is not None else None

    @property
    def REG_PRM_AMT(self) -> Optional[Decimal]:
        """Alias — REG_PRM_AMT does not exist; the correct field is POL_PRM_AMT."""
        return self.POL_PRM_AMT

    @property
    def annual_premium(self) -> Optional[Decimal]:
        if self.POL_PRM_AMT and self.PMT_FQY_PER:
            return self.POL_PRM_AMT * (Decimal(12) / Decimal(self.PMT_FQY_PER))
        return self.POL_PRM_AMT

    @property
    def TAR_PRM_AMT(self) -> Optional[Decimal]:
        """Target premium — moved from TH_BAS_POL to LH_POL_TARGET."""
        val = self._policy.data_item("LH_POL_TARGET", "TAR_PRM_AMT")
        return Decimal(str(val)) if val is not None else None

    @property
    def MIN_PRM_AMT(self) -> Optional[Decimal]:
        """Minimum premium — MIN_PRM_AMT does not exist on TH_BAS_POL."""
        return None

    # =====================================================================
    # OPTIONS
    # =====================================================================

    @property
    def PR_DIV_OPT_CD(self) -> str:
        return str(self._policy.data_item("LH_BAS_POL", "PRI_DIV_OPT_CD") or "0")

    @property
    def div_option_description(self) -> str:
        return DIV_OPTION_CODES.get(self.PR_DIV_OPT_CD, f"Unknown ({self.PR_DIV_OPT_CD})")

    @property
    def NFO_CD(self) -> str:
        return str(self._policy.data_item("LH_BAS_POL", "NFO_OPT_TYP_CD") or "0")

    @property
    def nfo_description(self) -> str:
        return NFO_CODES.get(self.NFO_CD, f"Unknown ({self.NFO_CD})")

    @property
    def DTH_BNF_PLN_OPT_CD(self) -> str:
        return str(self._policy.data_item("LH_NON_TRD_POL", "DTH_BNF_PLN_OPT_CD") or "")

    @property
    def db_option_description(self) -> str:
        return DB_OPTION_CODES.get(self.DTH_BNF_PLN_OPT_CD, f"Unknown ({self.DTH_BNF_PLN_OPT_CD})")

    # =====================================================================
    # CLASSIFICATION
    # =====================================================================

    @property
    def NON_TRD_POL_IND(self) -> bool:
        """Whether this is an advanced product (UL/IUL/VUL)."""
        return str(self._policy.data_item("LH_BAS_POL", "NON_TRD_POL_IND")) == "1"

    @property
    def DEFRA_IND(self) -> str:
        """DEFRA_IND does not exist on LH_BAS_POL.
        Use TFDF_CD on LH_NON_TRD_POL for TEFRA/DEFRA determination."""
        return ""

    @property
    def TFDF_CD(self) -> str:
        return str(self._policy.data_item("LH_NON_TRD_POL", "TFDF_CD") or "")

    @property
    def def_of_life_ins_description(self) -> str:
        return DEF_OF_LIFE_INS_CODES.get(self.TFDF_CD, "")

    @property
    def GSP_AMT(self) -> Optional[Decimal]:
        """GSP_AMT does not exist on LH_BAS_POL.
        Use LH_COV_INS_GDL_PRM with PRM_RT_TYP_CD='S' instead."""
        return None

    @property
    def GLP_AMT(self) -> Optional[Decimal]:
        """GLP_AMT does not exist on LH_BAS_POL.
        Use LH_COV_INS_GDL_PRM with PRM_RT_TYP_CD='A' instead."""
        return None

    # =====================================================================
    # ENTRY CODES / MISC
    # =====================================================================

    @property
    def OGN_ETR_CD(self) -> str:
        return str(self._policy.data_item("LH_BAS_POL", "OGN_ETR_CD") or "")

    @property
    def LST_ETR_CD(self) -> str:
        return str(self._policy.data_item("LH_BAS_POL", "LST_ETR_CD") or "")

    @property
    def POL_1035_XCG_IND(self) -> bool:
        return str(self._policy.data_item("LH_BAS_POL", "POL_1035_XCG_IND")) == "1"

    @property
    def SVC_AGT_NBR(self) -> str:
        return str(self._policy.data_item("LH_BAS_POL", "SVC_AGT_NBR") or "")

    @property
    def SVC_AGC_NBR(self) -> str:
        return str(self._policy.data_item("LH_BAS_POL", "SVC_AGC_NBR") or "")

    @property
    def servicing_market_org(self) -> str:
        branch = self.SVC_AGC_NBR
        agent_code = branch[0] if branch else ""
        company_code = str(self._policy.data_item("LH_BAS_POL", "CK_CMP_CD") or "")
        return translate_market_org(company_code, agent_code)

    @property
    def agency_branch_code(self) -> str:
        branch = self.SVC_AGC_NBR
        return branch[1:5] if len(branch) >= 5 else branch

    @property
    def LN_PLN_ITS_RT(self) -> Optional[Decimal]:
        val = self._policy.data_item("LH_BAS_POL", "LN_PLN_ITS_RT")
        return Decimal(str(val)) if val is not None else None

    @property
    def FORCED_PREM_IND(self) -> bool:
        return str(self._policy.data_item("TH_BAS_POL", "FORCED_PREM_IND")) == "1"

    @property
    def USR_RES_CD(self) -> str:
        return str(self._policy.data_item("LH_BAS_POL", "USR_RES_CD") or "")

    @property
    def BIL_FRM_CD(self) -> str:
        return str(self._policy.data_item("LH_BAS_POL", "BIL_FRM_CD") or "")

    # =====================================================================
    # RECORD 51 — NON-TRAD POLICY (LH_NON_TRD_POL)
    # =====================================================================

    @property
    def POL_GUA_ITS_RT(self) -> Optional[Decimal]:
        val = self._policy.data_item("LH_NON_TRD_POL", "POL_GUA_ITS_RT")
        return Decimal(str(val)) if val is not None else None

    @property
    def CDR_PCT(self) -> Optional[Decimal]:
        val = self._policy.data_item("LH_NON_TRD_POL", "CDR_PCT")
        return Decimal(str(val)) if val is not None else Decimal("100")

    @property
    def GRA_THD_RLE_CD(self) -> str:
        return str(self._policy.data_item("LH_NON_TRD_POL", "GRA_THD_RLE_CD") or "")

    @property
    def NON_TRD_TFDF_CD(self) -> str:
        return str(self._policy.data_item("LH_NON_TRD_POL", "TFDF_CD") or "")

    @property
    def PRF_LN_OPT_CD(self) -> str:
        val = self._policy.data_item("LH_NON_TRD_POL", "PRF_LN_OPT_CD")
        return str(val) if val is not None else "0"

    @property
    def preferred_loans_available(self) -> bool:
        return self.PRF_LN_OPT_CD != "0"

    # Grace period - works for both trad and non-trad
    def grace_period_expiry_date(self, is_advanced: bool) -> Optional[date]:
        if is_advanced:
            return parse_date(self._policy.data_item("LH_NON_TRD_POL", "GRA_PER_EXP_DT"))
        else:
            return parse_date(self._policy.data_item("LH_TRD_POL", "GRA_PER_EXP_DT"))

    def in_grace(self, is_advanced: bool) -> bool:
        if is_advanced:
            return str(self._policy.data_item("LH_NON_TRD_POL", "IN_GRA_PER_IND")) == "1"
        else:
            return str(self._policy.data_item("LH_TRD_POL", "IN_GRA_PER_IND")) == "1"
