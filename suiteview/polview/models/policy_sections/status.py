"""PolicyInformation status section."""

from __future__ import annotations

from .base import PolicySection
from ..cl_polrec.policy_translations import PREMIUM_PAY_STATUS_CODES
from ..cl_polrec.policy_translations import STATUS_CODES
from ..cl_polrec.policy_translations import SUSPENSE_CODES
from datetime import date
from typing import Optional


class StatusSection(PolicySection):
    """Cohesive PolicyInformation status view."""

    TABLES = frozenset(('ADVANCED_GRACE_EXPIRY', 'ADVANCED_GRACE_INDICATOR', 'LAST_ENTRY_CODE', 'ORIGINAL_ENTRY_CODE', 'PREMIUM_PAY_STATUS_CODE', 'STATUS_CODE', 'SUSPENSE_CODE', 'TRADITIONAL_GRACE_EXPIRY', 'TRADITIONAL_GRACE_INDICATOR',))
    CACHE_ATTRS = ()

    @property
    def status_code(self) -> str:
        """Policy status code."""
        return str(self._field("status_code") or "")

    @property
    def status_description(self) -> str:
        """Policy status description."""
        return STATUS_CODES.get(self.status_code, f"Unknown ({self.status_code})")

    @property
    def suspense_code(self) -> str:
        """Suspense code."""
        return str(self._field("suspense_code") or "0")

    @property
    def suspense_description(self) -> str:
        """Suspense description."""
        return SUSPENSE_CODES.get(self.suspense_code, f"Unknown ({self.suspense_code})")

    @property
    def premium_pay_status_code(self) -> str:
        """Premium paying status code (PRM_PAY_STA_REA_CD)."""
        return str(self._field("premium_pay_status_code") or "")

    @property
    def premium_pay_status_description(self) -> str:
        """Premium paying status description."""
        return PREMIUM_PAY_STATUS_CODES.get(self.premium_pay_status_code, f"Unknown ({self.premium_pay_status_code})")

    @property
    def is_active(self) -> bool:
        """Whether policy is in active status."""
        return self.status_code in ("10", "14", "15")

    @property
    def is_suspended(self) -> bool:
        """Whether policy is suspended."""
        return self.status_code == "20"

    @property
    def is_terminated(self) -> bool:
        """Whether policy is terminated (any non-active status)."""
        return self.status_code not in ("10", "14", "15", "20")

    @property
    def grace_indicator(self) -> bool:
        """Whether policy is in grace period (always False — use in_grace() instead)."""
        return False

    @property
    def grace_period_expiry_date(self) -> Optional[date]:
        """Grace period expiration date."""
        field = "advanced_grace_expiry" if self.product.product_rules.is_advanced else "traditional_grace_expiry"
        return self._parse_date(self._field(field))

    @property
    def in_grace(self) -> bool:
        """Whether policy is in grace period."""
        field = "advanced_grace_indicator" if self.product.product_rules.is_advanced else "traditional_grace_indicator"
        return str(self._field(field)) == "1"

    @property
    def original_entry_code(self) -> str:
        """Original entry code."""
        return str(self._field("original_entry_code") or "")

    @property
    def last_entry_code(self) -> str:
        """Last entry code."""
        return str(self._field("last_entry_code") or "")

    @property
    def policy_1035_indicator(self) -> bool:
        """Whether policy involved a 1035 exchange."""
        return str(self._field("policy_1035_indicator")) == "1"
