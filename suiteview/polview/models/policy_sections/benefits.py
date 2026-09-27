"""PolicyInformation benefits section."""

from __future__ import annotations

from .base import PolicySection
from ..cl_polrec.policy_data_classes import BenefitInfo
from typing import Any
from typing import List


class BenefitsSection(PolicySection):
    """Cohesive PolicyInformation benefits view."""

    TABLES = frozenset(('BNF_ANN_PPU_AMT', 'BNF_CEA_DT', 'BNF_FRM_NBR', 'BNF_ISS_AGE', 'BNF_ISS_DT', 'BNF_OGN_CEA_DT', 'BNF_PAY_UP_DT', 'BNF_RT_FCT', 'BNF_UNT_QTY', 'BNF_VPU_AMT', 'COV_PHA_NBR', 'LH_SPM_BNF', 'RNL_RT_IND', 'SPM_BNF_SBY_CD', 'SPM_BNF_TYP_CD',))
    CACHE_ATTRS = ('_benefits',)

    @property
    def benefit_count(self) -> int:
        """Number of benefits."""
        return self.data_item_count("LH_SPM_BNF")

    def get_benefits(self, cov_pha_nbr: int = None) -> List[BenefitInfo]:
        """Get benefits with complete VBA-compatible field mapping."""
        if self._benefits is None:
            self._benefits = []
            for row in self.fetch_table("LH_SPM_BNF"):
                # Get type and subtype codes to build benefit code (plancode)
                type_cd = str(row.get("SPM_BNF_TYP_CD", "")).strip()
                subtype_cd = str(row.get("SPM_BNF_SBY_CD", "")).strip()
                benefit_code = type_cd + subtype_cd
                ben_cov_pha_nbr = int(row.get("COV_PHA_NBR", 0) or 0)

                # Get units and VPU for amount calculation
                units = self._parse_optional_decimal(row.get("BNF_UNT_QTY"))
                vpu = self._parse_optional_decimal(row.get("BNF_VPU_AMT"))
                benefit_amount = (units * vpu) if (units is not None and vpu is not None) else None

                # Renewal rate from the 67 segment (LH_BNF_INS_RNL_RT, type "B").
                # The Record-04 BNF_ANN_PPU_AMT above is the issue rate; this is
                # the renewal rate that applies once the benefit renews.
                renewal_rate = self.rates.benefit_renewal_rate(
                    ben_cov_pha_nbr, type_cd, subtype_cd, "B"
                )

                ben = BenefitInfo(
                    cov_pha_nbr=ben_cov_pha_nbr,
                    benefit_code=benefit_code,
                    benefit_type_cd=type_cd,
                    benefit_subtype_cd=subtype_cd,
                    benefit_desc=type_cd,  # Type code is the primary descriptor
                    form_number=str(row.get("BNF_FRM_NBR", "")).strip(),
                    issue_date=self._parse_date(row.get("BNF_ISS_DT")),
                    pay_up_date=self._parse_date(row.get("BNF_PAY_UP_DT")),
                    cease_date=self._parse_date(row.get("BNF_CEA_DT")),
                    orig_cease_date=self._parse_date(row.get("BNF_OGN_CEA_DT")),
                    units=units,
                    vpu=vpu,
                    benefit_amount=benefit_amount,
                    issue_age=self._parse_optional_int(row.get("BNF_ISS_AGE")),
                    rating_factor=self._parse_optional_decimal(row.get("BNF_RT_FCT")),
                    renewal_indicator=str(row.get("RNL_RT_IND", "")).strip(),
                    coi_rate=self._parse_optional_decimal(row.get("BNF_ANN_PPU_AMT")),
                    renewal_rate=renewal_rate,
                    raw_data=row
                )
                self._benefits.append(ben)

        if cov_pha_nbr is not None:
            return [b for b in self._benefits if b.cov_pha_nbr == cov_pha_nbr]
        return self._benefits

    def ben_value_by_name(self, plancode: str, field_name: str) -> Any:
        """Get raw field value for benefit matching plancode (type+subtype).

        For structured access, use get_benefits() which returns BenefitInfo objects.
        This method is for ad-hoc lookups of fields not in BenefitInfo.
        """
        for ben in self.get_benefits():
            if ben.benefit_code == plancode:
                return ben.raw_data.get(field_name.upper())
        return None
