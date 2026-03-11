"""
CL_POLREC_52 — User Field Records (Record 52)
================================================

DB2 tables
----------
Record 52 — User Generic Fields
    TH_USER_GENERIC      User-defined generic fields (short pay, dial-to, etc.)
"""

from __future__ import annotations

from typing import Optional

from .cyberlife_base import PolicyDataAccessor
from .policy_data_classes import UserFieldInfo


class UserFieldRecords:
    """System-layer access for user-defined generic fields."""

    TABLES = (
        "TH_USER_GENERIC",
    )

    def __init__(self, policy: PolicyDataAccessor) -> None:
        self._policy = policy

    def invalidate(self) -> None:
        pass

    # =====================================================================
    # USER GENERIC FIELDS (TH_USER_GENERIC)
    # =====================================================================

    @property
    def INITIAL_PAY_DUR(self) -> Optional[int]:
        """Short pay duration in years."""
        val = self._policy.data_item("TH_USER_GENERIC", "INITIAL_PAY_DUR")
        return int(val) if val and int(val) > 0 else None

    @property
    def INITIAL_MODE(self) -> Optional[str]:
        """Short pay mode."""
        return str(self._policy.data_item("TH_USER_GENERIC", "INITIAL_MODE") or "") if self.INITIAL_PAY_DUR else None

    @property
    def DIAL_TO_PREM_AGE(self) -> Optional[int]:
        """Death benefit dial-to premium age."""
        val = self._policy.data_item("TH_USER_GENERIC", "DIAL_TO_PREM_AGE")
        return int(val) if val and int(val) > 0 else None

    def get_user_field_info(self) -> UserFieldInfo:
        """Build UserFieldInfo object."""
        return UserFieldInfo(
            INITIAL_PAY_DUR=self.INITIAL_PAY_DUR,
            INITIAL_MODE=self.INITIAL_MODE,
            DIAL_TO_PREM_AGE=self.DIAL_TO_PREM_AGE,
            raw_data={},
        )
