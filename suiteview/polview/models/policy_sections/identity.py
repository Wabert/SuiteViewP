"""PolicyInformation identity section."""

from __future__ import annotations

from .base import PolicySection
from ..cl_polrec.policy_translations import COMPANY_CODES
from typing import List


class IdentitySection(PolicySection):
    """Cohesive PolicyInformation identity view."""

    TABLES = frozenset()
    CACHE_ATTRS = ()

    @property
    def exists(self) -> bool:
        """Whether the policy exists in the database."""
        return self.policy._data.exists

    @property
    def cancelled(self) -> bool:
        """Whether loading was cancelled or errored."""
        return self.policy._data.cancelled

    @property
    def last_error(self) -> str:
        """Last error message if cancelled."""
        return self.policy._data.last_error

    @property
    def available_companies(self) -> List[str]:
        """List of company codes when policy exists in multiple companies."""
        return self.policy._data.available_companies

    @property
    def policy_number(self) -> str:
        """Policy number."""
        return self.policy._data.policy_number

    @property
    def policy_id(self) -> str:
        """Technical policy ID (TCH_POL_ID)."""
        return self.policy._data.policy_id or ""

    @property
    def company_code(self) -> str:
        """Company code."""
        return self.policy._data.company_code or ""

    @property
    def company_name(self) -> str:
        """Company name (translated)."""
        return COMPANY_CODES.get(self.company_code, self.company_code)

    @property
    def system_code(self) -> str:
        """System code."""
        return self.policy._data.system_code

    @property
    def region(self) -> str:
        """Database region."""
        return self.policy._data.region
