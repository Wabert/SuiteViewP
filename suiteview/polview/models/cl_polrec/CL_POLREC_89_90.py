"""
CL_POLREC_89_90 — Person Records (Records 89, 90)
====================================================

DB2 tables
----------
Record 89 — Client Information
    VH_POL_HAS_LOC_CLT  Policy-client cross-reference (names)
    LH_CTT_CLIENT       Client details (birth date, gender, person code)

Record 90 — Address Information
    LH_LOC_CLT_ADR       Client address records
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from .cyberlife_base import PolicyDataAccessor, parse_date
from .policy_data_classes import PersonInfo, AddressInfo
from .policy_translations import SEX_CODES, PERSON_CODES


class PersonRecords:
    """System-layer access for person/client Cyberlife policy records."""

    TABLES = (
        "VH_POL_HAS_LOC_CLT",
        "LH_CTT_CLIENT",
        "LH_LOC_CLT_ADR",
    )

    def __init__(self, policy: PolicyDataAccessor) -> None:
        self._policy = policy

    def invalidate(self) -> None:
        pass

    # =====================================================================
    # PERSONS (LH_CTT_CLIENT / VH_POL_HAS_LOC_CLT)
    # =====================================================================

    @property
    def person_count(self) -> int:
        return self._policy.data_item_count("LH_CTT_CLIENT")

    def person_index(self, PRS_CD: str = "00", PRS_SEQ_NBR: int = 1) -> Optional[int]:
        """Find index for person by code and sequence."""
        for i in range(self.person_count):
            if (str(self._policy.data_item("LH_CTT_CLIENT", "PRS_CD", i)) == PRS_CD
                    and int(self._policy.data_item("LH_CTT_CLIENT", "PRS_SEQ_NBR", i) or 0) == PRS_SEQ_NBR):
                return i
        return None

    def person_first_name(self, index: int) -> str:
        return str(self._policy.data_item("VH_POL_HAS_LOC_CLT", "CK_FST_NM", index) or "").strip()

    def person_last_name(self, index: int) -> str:
        return str(self._policy.data_item("VH_POL_HAS_LOC_CLT", "CK_LST_NM", index) or "").strip()

    def person_full_name(self, index: int) -> str:
        return f"{self.person_first_name(index)} {self.person_last_name(index)}".strip()

    def person_birth_date(self, index: int) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_CTT_CLIENT", "BIR_DT", index))

    def person_gender(self, index: int) -> str:
        return str(self._policy.data_item("LH_CTT_CLIENT", "GENDER_CD", index) or "")

    def person_code(self, index: int) -> str:
        return str(self._policy.data_item("LH_CTT_CLIENT", "PRS_CD", index) or "")

    def get_persons(self) -> List[PersonInfo]:
        """Build PersonInfo objects for all persons on the policy."""
        persons: List[PersonInfo] = []
        for i in range(self.person_count):
            prs_cd = self.person_code(i)
            gender_cd = self.person_gender(i)
            person = PersonInfo(
                PRS_CD=prs_cd,
                PRS_SEQ_NBR=int(self._policy.data_item("LH_CTT_CLIENT", "PRS_SEQ_NBR", i) or 0),
                person_desc=PERSON_CODES.get(prs_cd, ""),
                first_name=self.person_first_name(i),
                last_name=self.person_last_name(i),
                BIR_DT=self.person_birth_date(i),
                GENDER_CD=gender_cd,
                gender_desc=SEX_CODES.get(gender_cd, ""),
                raw_data={},
            )
            persons.append(person)
        return persons

    @property
    def is_joint_insured(self) -> bool:
        for i in range(self.person_count):
            if self.person_code(i) == "01":
                return True
        return False

    @property
    def primary_insured_name(self) -> str:
        idx = self.person_index("00", 1)
        if idx is not None:
            return self.person_full_name(idx)
        return ""

    # =====================================================================
    # ADDRESS (LH_LOC_CLT_ADR)
    # =====================================================================

    @property
    def address_count(self) -> int:
        return self._policy.data_item_count("LH_LOC_CLT_ADR")

    def address_street1(self, index: int) -> str:
        return str(self._policy.data_item("LH_LOC_CLT_ADR", "ADR_LIN_1", index) or "").strip()

    def address_street2(self, index: int) -> str:
        return str(self._policy.data_item("LH_LOC_CLT_ADR", "ADR_LIN_2", index) or "").strip()

    def address_city(self, index: int) -> str:
        return str(self._policy.data_item("LH_LOC_CLT_ADR", "CIT_TXT", index) or "").strip()

    def address_state(self, index: int) -> str:
        return str(self._policy.data_item("LH_LOC_CLT_ADR", "CK_ST_CD", index) or "").strip()

    def address_zip(self, index: int) -> str:
        return str(self._policy.data_item("LH_LOC_CLT_ADR", "ZIP_CD", index) or "").strip()

    def get_full_address(self, index: int = 0) -> str:
        street = f"{self.address_street1(index)} {self.address_street2(index)}".strip()
        city_state_zip = f"{self.address_city(index)}, {self.address_state(index)} {self.address_zip(index)}"
        return f"{street}\n{city_state_zip}".strip()

    def get_addresses(self) -> List[AddressInfo]:
        """Build AddressInfo objects for all addresses."""
        addresses: List[AddressInfo] = []
        for i in range(self.address_count):
            addr = AddressInfo(
                ADR_LIN_1=self.address_street1(i),
                ADR_LIN_2=self.address_street2(i),
                CIT_TXT=self.address_city(i),
                CK_ST_CD=self.address_state(i),
                ZIP_CD=self.address_zip(i),
                raw_data={},
            )
            addresses.append(addr)
        return addresses
