"""PolicyInformation persons section."""

from __future__ import annotations

from .base import PolicySection
from datetime import date
from typing import Optional


class PersonsSection(PolicySection):
    """Cohesive PolicyInformation persons view."""

    CACHE_ATTRS = ()

    @property
    def person_count(self) -> int:
        """Number of persons on policy."""
        return self.data_item_count("LH_CTT_CLIENT")

    def person_index(self, person_code: str = "00", seq_nbr: int = 1) -> Optional[int]:
        """Find index for person by code and sequence."""
        for i in range(self.person_count):
            if (str(self.data_item("LH_CTT_CLIENT", "PRS_CD", i)) == person_code and
                int(self.data_item("LH_CTT_CLIENT", "PRS_SEQ_NBR", i) or 0) == seq_nbr):
                return i
        return None

    def person_first_name(self, index: int) -> str:
        """Get person first name at index."""
        return str(self.data_item("VH_POL_HAS_LOC_CLT", "CK_FST_NM", index) or "").strip()

    def person_last_name(self, index: int) -> str:
        """Get person last name at index."""
        return str(self.data_item("VH_POL_HAS_LOC_CLT", "CK_LST_NM", index) or "").strip()

    def person_full_name(self, index: int) -> str:
        """Get person full name at index."""
        return f"{self.person_first_name(index)} {self.person_last_name(index)}".strip()

    def person_birth_date(self, index: int) -> Optional[date]:
        """Get person birth date at index."""
        return self._parse_date(self.data_item("LH_CTT_CLIENT", "BIR_DT", index))

    def person_gender(self, index: int) -> str:
        """Get person gender code at index."""
        return str(self.data_item("LH_CTT_CLIENT", "GENDER_CD", index) or "")

    def person_code(self, index: int) -> str:
        """Get person code at index."""
        return str(self.data_item("LH_CTT_CLIENT", "PRS_CD", index) or "")

    @property
    def primary_insured_name(self) -> str:
        """Primary insured full name."""
        idx = self.person_index("00", 1)
        if idx is not None:
            return self.person_full_name(idx)
        return ""

    @property
    def primary_insured_birth_date(self) -> Optional[date]:
        """Primary insured date of birth (LH_CTT_CLIENT.BIR_DT)."""
        idx = self.person_index("00", 1)
        if idx is not None:
            return self.person_birth_date(idx)
        return None

    @property
    def address_count(self) -> int:
        """Number of address records."""
        return self.data_item_count("LH_LOC_CLT_ADR")

    def address_street1(self, index: int) -> str:
        """Get address line 1 at index."""
        return str(self.data_item("LH_LOC_CLT_ADR", "ADR_LIN_1", index) or "").strip()

    def address_street2(self, index: int) -> str:
        """Get address line 2 at index."""
        return str(self.data_item("LH_LOC_CLT_ADR", "ADR_LIN_2", index) or "").strip()

    def address_city(self, index: int) -> str:
        """Get city at index."""
        return str(self.data_item("LH_LOC_CLT_ADR", "CIT_TXT", index) or "").strip()

    def address_state(self, index: int) -> str:
        """Get state at index."""
        return str(self.data_item("LH_LOC_CLT_ADR", "CK_ST_CD", index) or "").strip()

    def address_zip(self, index: int) -> str:
        """Get ZIP code at index."""
        return str(self.data_item("LH_LOC_CLT_ADR", "ZIP_CD", index) or "").strip()

    def get_full_address(self, index: int = 0) -> str:
        """Get formatted full address at index."""
        street = f"{self.address_street1(index)} {self.address_street2(index)}".strip()
        city_state_zip = f"{self.address_city(index)}, {self.address_state(index)} {self.address_zip(index)}"
        return f"{street}\n{city_state_zip}".strip()
