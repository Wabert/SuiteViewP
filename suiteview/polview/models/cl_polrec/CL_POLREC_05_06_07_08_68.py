"""
CL_POLREC_05_06_07_08_68 — Change Records (Records 05-08, 68)
===============================================================

DB2 tables
----------
Record 05 — Policy Changes
    (Change history is generally reconstructed from entry codes
     and transaction history rather than a dedicated table.)

Note: Cyberlife does not have a single dedicated change-history table.
Change data is derived from LH_BAS_POL entry codes and FH_FIXED
transaction records. This module provides a structured interface
for that derived data.
"""

from __future__ import annotations

from decimal import Decimal
from datetime import date
from typing import Any, Dict, List, Optional

from .cyberlife_base import PolicyDataAccessor, parse_date
from .policy_data_classes import PolicyChangeInfo


class ChangeRecords:
    """System-layer access for policy change records.

    Change history is derived from entry codes on LH_BAS_POL
    and transaction records in FH_FIXED.
    """

    TABLES = (
        "LH_BAS_POL",
    )

    def __init__(self, policy: PolicyDataAccessor) -> None:
        self._policy = policy

    def invalidate(self) -> None:
        pass

    # =====================================================================
    # ENTRY CODES (from LH_BAS_POL)
    # =====================================================================

    @property
    def OGN_ETR_CD(self) -> str:
        """Original entry code."""
        return str(self._policy.data_item("LH_BAS_POL", "OGN_ETR_CD") or "")

    @property
    def LST_ETR_CD(self) -> str:
        """Last entry code."""
        return str(self._policy.data_item("LH_BAS_POL", "LST_ETR_CD") or "")

    def get_change_summary(self) -> PolicyChangeInfo:
        """Build a summary change info from entry codes."""
        return PolicyChangeInfo(
            change_date=None,
            change_type=self.LST_ETR_CD,
            change_desc=f"Last entry: {self.LST_ETR_CD}",
            OGN_ETR_CD=self.OGN_ETR_CD,
            LST_ETR_CD=self.LST_ETR_CD,
            raw_data={},
        )
