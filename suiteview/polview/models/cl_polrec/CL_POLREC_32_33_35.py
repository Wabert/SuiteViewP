"""
CL_POLREC_32_33_35 — Billing Records (Records 32, 33, 35)
============================================================

DB2 tables
----------
Billing data is sourced from LH_BAS_POL billing fields.
These records don't have dedicated tables but represent
the billing configuration within the base policy record.
"""

from __future__ import annotations

from decimal import Decimal
from datetime import date
from typing import Optional

from .cyberlife_base import PolicyDataAccessor, parse_date
from .policy_data_classes import BillingInfo
from .policy_translations import BILLING_MODE_CODES, NON_STANDARD_BILL_MODE_CODES


class BillingRecords:
    """System-layer access for billing Cyberlife policy records."""

    TABLES = (
        "LH_BAS_POL",
    )

    def __init__(self, policy: PolicyDataAccessor) -> None:
        self._policy = policy

    def invalidate(self) -> None:
        pass

    # =====================================================================
    # BILLING FIELDS (from LH_BAS_POL)
    # =====================================================================

    @property
    def PMT_FQY_PER(self) -> int:
        return int(self._policy.data_item("LH_BAS_POL", "PMT_FQY_PER") or 0)

    @property
    def NSD_MD_CD(self) -> str:
        return str(self._policy.data_item("LH_BAS_POL", "NSD_MD_CD") or "")

    @property
    def billing_mode_desc(self) -> str:
        if self.NSD_MD_CD in NON_STANDARD_BILL_MODE_CODES:
            return NON_STANDARD_BILL_MODE_CODES[self.NSD_MD_CD]
        return BILLING_MODE_CODES.get(self.PMT_FQY_PER, f"{self.PMT_FQY_PER} months")

    @property
    def BL_DAY_NBR(self) -> int:
        return int(self._policy.data_item("LH_BAS_POL", "BIL_DAY_NBR") or 0)

    @property
    def BIL_FRM_CD(self) -> str:
        return str(self._policy.data_item("LH_BAS_POL", "BIL_FRM_CD") or "")

    @property
    def NXT_BIL_DT(self) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_BAS_POL", "NXT_BIL_DT"))

    @property
    def PRM_BILL_TO_DT(self) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_BAS_POL", "PRM_BILL_TO_DT"))

    def get_billing_info(self) -> BillingInfo:
        """Build BillingInfo object."""
        return BillingInfo(
            PMT_FQY_PER=self.PMT_FQY_PER,
            billing_mode_desc=self.billing_mode_desc,
            NSD_MD_CD=self.NSD_MD_CD,
            BL_DAY_NBR=self.BL_DAY_NBR,
            BIL_FRM_CD=self.BIL_FRM_CD,
            billing_form_desc=self.BIL_FRM_CD,
            raw_data={},
        )
