"""PolicyInformation rates section."""

from __future__ import annotations

from .base import PolicySection
from ._rate_matrices import RateMatrixMixin
from ..cl_polrec.policy_data_classes import RenewalBenRateInfo
from ..cl_polrec.policy_data_classes import RenewalCovRateInfo
from ..cl_polrec.policy_translations import rate_class_description
from ..cl_polrec.policy_translations import translate_renewal_rate_type_code
from decimal import Decimal
from typing import List
from typing import Optional

try:
    from suiteview.core.rates import Rates, RatesError
except ImportError:
    Rates = None  # type: ignore[assignment,misc]
    RatesError = RuntimeError  # type: ignore[assignment,misc]


class RatesSection(RateMatrixMixin, PolicySection):
    """Cohesive PolicyInformation rates view."""

    CACHE_ATTRS = ()

    def get_coverage_renewal_rates(self, cov_pha_nbr: int = None) -> List[RenewalCovRateInfo]:
        """Get coverage renewal rate records, optionally filtered by coverage."""
        rates = []
        plancodes_by_phase = {
            int(row.get("COV_PHA_NBR", 0) or 0): str(row.get("PLN_DES_SER_CD", "") or "")
            for row in self.fetch_table("LH_COV_PHA")
        }
        for row in self.fetch_table("LH_COV_INS_RNL_RT"):
            phase = int(row.get("COV_PHA_NBR", 0) or 0)
            if cov_pha_nbr is not None and phase != cov_pha_nbr:
                continue

            rate_type = str(row.get("PRM_RT_TYP_CD", "") or "")
            rate_class = str(row.get("RT_CLS_CD", "") or "")
            rate = RenewalCovRateInfo(
                coverage_phase=phase,
                rate_type=rate_type,
                rate_type_desc=translate_renewal_rate_type_code(rate_type),
                joint_indicator=str(row.get("JT_INS_IND", "") or ""),
                rate_class=rate_class,
                rate_class_desc=rate_class_description(
                    rate_class, plancodes_by_phase.get(phase, "")
                ),
                issue_age=self._parse_optional_int(row.get("ISS_AGE")),
                raw_data=row
            )
            rates.append(rate)
        return rates

    def get_benefit_renewal_rates(self, cov_pha_nbr: int = None) -> List[RenewalBenRateInfo]:
        """Get benefit renewal rate records, optionally filtered by coverage."""
        rates = []
        for row in self.fetch_table("LH_BNF_INS_RNL_RT"):
            phase = int(row.get("COV_PHA_NBR", 0) or 0)
            if cov_pha_nbr is not None and phase != cov_pha_nbr:
                continue

            rate_type = str(row.get("PRM_RT_TYP_CD", "") or "")
            rate = RenewalBenRateInfo(
                coverage_phase=phase,
                benefit_type=str(row.get("SPM_BNF_TYP_CD", "") or ""),
                benefit_subtype=str(row.get("SPM_BNF_SBY_CD", "") or ""),
                rate_type=rate_type,
                rate_type_desc=translate_renewal_rate_type_code(rate_type),
                joint_indicator=str(row.get("JT_INS_IND", "") or ""),
                rate_class=str(row.get("RT_CLS_CD", "") or ""),
                issue_age=self._parse_optional_int(row.get("ISS_AGE")),
                raw_data=row
            )
            rates.append(rate)
        return rates

    @property
    def renewal_cov_count(self) -> int:
        """Count of coverage renewal rate records."""
        return self.data_item_count("LH_COV_INS_RNL_RT")

    @property
    def renewal_ben_count(self) -> int:
        """Count of benefit renewal rate records."""
        return self.data_item_count("LH_BNF_INS_RNL_RT")

    def cov_renewal_index(self, cov_pha_nbr: int, rate_type: str = "C", joint_ind: str = "0") -> int:
        """Find index of coverage renewal rate record matching criteria (0-based)."""
        for i in range(self.renewal_cov_count):
            if (int(self.data_item("LH_COV_INS_RNL_RT", "COV_PHA_NBR", i) or 0) == cov_pha_nbr and
                str(self.data_item("LH_COV_INS_RNL_RT", "PRM_RT_TYP_CD", i) or "") == rate_type and
                str(self.data_item("LH_COV_INS_RNL_RT", "JT_INS_IND", i) or "") == joint_ind):
                return i
        return -1

    def renewal_cov_rateclass(self, index: int) -> str:
        """Get renewal coverage rate class (0-based index)."""
        return str(self.data_item("LH_COV_INS_RNL_RT", "RT_CLS_CD", index) or "")

    def renewal_cov_issue_age(self, index: int) -> Optional[int]:
        """Get renewal coverage issue age (0-based index)."""
        val = self.data_item("LH_COV_INS_RNL_RT", "ISS_AGE", index)
        return int(val) if val else None

    def ben_renewal_index(self, cov_pha_nbr: int, ben_type: str, ben_subtype: str, 
                          rate_type: str = "C", joint_ind: str = "0") -> int:
        """Find index of benefit renewal rate record matching criteria (0-based)."""
        for i in range(self.renewal_ben_count):
            if (int(self.data_item("LH_BNF_INS_RNL_RT", "COV_PHA_NBR", i) or 0) == cov_pha_nbr and
                str(self.data_item("LH_BNF_INS_RNL_RT", "SPM_BNF_TYP_CD", i) or "") == ben_type and
                str(self.data_item("LH_BNF_INS_RNL_RT", "SPM_BNF_SBY_CD", i) or "") == ben_subtype and
                str(self.data_item("LH_BNF_INS_RNL_RT", "PRM_RT_TYP_CD", i) or "") == rate_type and
                str(self.data_item("LH_BNF_INS_RNL_RT", "JT_INS_IND", i) or "") == joint_ind):
                return i
        return -1

    def renewal_ben_rateclass(self, index: int) -> str:
        """Get renewal benefit rate class (0-based index)."""
        return str(self.data_item("LH_BNF_INS_RNL_RT", "RT_CLS_CD", index) or "")

    def renewal_ben_issue_age(self, index: int) -> Optional[int]:
        """Get renewal benefit issue age (0-based index)."""
        val = self.data_item("LH_BNF_INS_RNL_RT", "ISS_AGE", index)
        return int(val) if val else None

    def benefit_renewal_rate(self, cov_pha_nbr: int, ben_type: str,
                             ben_subtype: str, rate_type: str = "B") -> Optional[Decimal]:
        """Renewal rate (RNL_RT) for a benefit, from LH_BNF_INS_RNL_RT (Record 67).

        Matches the benefit by coverage phase, type, and subtype, restricted to
        the renewal-premium rate row (PRM_RT_TYP_CD = "B").  The stored RNL_RT is
        scaled, so it is divided by 100,000 to give a per-unit rate.  Returns None
        when no matching row exists for the benefit (rate simply not present).
        """
        for row in self.fetch_table("LH_BNF_INS_RNL_RT"):
            if (int(row.get("COV_PHA_NBR", 0) or 0) == cov_pha_nbr and
                    str(row.get("SPM_BNF_TYP_CD", "") or "").strip() == ben_type and
                    str(row.get("SPM_BNF_SBY_CD", "") or "").strip() == ben_subtype and
                    str(row.get("PRM_RT_TYP_CD", "") or "").strip() == rate_type):
                raw_rate = row.get("RNL_RT")
                if raw_rate is None or str(raw_rate).strip() == "":
                    return None
                try:
                    return Decimal(str(raw_rate)) / 100000
                except Exception:
                    return None
        return None

    def _get_rates(self) -> Optional['Rates']:
        """Get or create Rates instance for rate lookups."""
        self.policy._data.reject_uncached_read("Rates lookup during cached rendering")
        if self.policy._rates is None:
            if Rates is not None:
                self.policy._rates = Rates()
        return self.policy._rates

    def _translate_sex_for_rates(self, sex_code: str) -> str:
        """Translate sex code for rate lookups (1->M, 2->F)."""
        if sex_code == "1":
            return "M"
        elif sex_code == "2":
            return "F"
        return sex_code

    def renewal_cov_sex_code(self, cov_index: int, joint_ind: int = 0) -> str:
        """
        Get sex code for coverage from renewal rates table.
        Uses current rate type "C" by default.

        Args:
            cov_index: Coverage index (1-based)
            joint_ind: Joint indicator (0=primary, 1=joint)

        Returns:
            Sex code from renewal rates table
        """
        cov_pha_nbr = self._cov_phase_for_index(cov_index)
        if cov_pha_nbr is None:
            return ""
        idx = self.cov_renewal_index(cov_pha_nbr, "C", str(joint_ind))
        if idx >= 0:
            return str(self.data_item("LH_COV_INS_RNL_RT", "RT_SEX_CD", idx) or "")
        return ""

    def renewal_cov_rateclass_by_cov(self, cov_index: int, joint_ind: int = 0) -> str:
        """
        Get rate class for coverage from renewal rates table.

        Args:
            cov_index: Coverage index (1-based)
            joint_ind: Joint indicator (0=primary, 1=joint)

        Returns:
            Rate class code from renewal rates table
        """
        cov_pha_nbr = self._cov_phase_for_index(cov_index)
        if cov_pha_nbr is None:
            return ""
        idx = self.cov_renewal_index(cov_pha_nbr, "C", str(joint_ind))
        if idx >= 0:
            return str(self.data_item("LH_COV_INS_RNL_RT", "RT_CLS_CD", idx) or "")
        return ""

    def _cov_phase_for_index(self, cov_index: int) -> Optional[int]:
        """Map a 1-based coverage index to its real COV_PHA_NBR.

        Coverage phases are NOT guaranteed to be 1..N contiguous — terminated
        coverages and interleaved riders leave gaps (e.g. 1, 5, 6, 7, 10, ...).
        The renewal-rate lookup (cov_renewal_index) matches on the real
        COV_PHA_NBR, so callers that pass a 1-based index must be translated
        here first. (Passing the index straight through silently matched the
        wrong renewal row — or none — yielding blank/wrong sex & rate class,
        and in turn empty/wrong COI/EPU/SCR schedules for increase coverages.)
        """
        covs = self.coverages.get_coverages()
        if not (0 < cov_index <= len(covs)):
            return None
        return covs[cov_index - 1].cov_pha_nbr

    def cov_mtp_band(self, cov_pha_nbr: int) -> int:
        """Stored MTP band by phase, RERUN's BandAtIssue (not current face).

        Segment 02/67 mappings verify BAN_STRUCTURE_CD and RT_BAN_CD.
        ExecuLife structure 6 orders X/Y before A; other structures start at A.
        """
        coverage_rows = [
            row for row in self.fetch_table("LH_COV_PHA")
            if int(row["COV_PHA_NBR"]) == cov_pha_nbr
        ]
        if len(coverage_rows) != 1:
            raise ValueError(f"Coverage {cov_pha_nbr}: missing or ambiguous band structure")
        raw_structure = coverage_rows[0]["BAN_STRUCTURE_CD"]
        if raw_structure is None:
            raise ValueError(f"Coverage {cov_pha_nbr}: NULL band structure")
        structure = str(raw_structure).strip()
        if structure in ("", "00", "0"):
            return 0
        codes = {
            str(row["RT_BAN_CD"] or "").strip()
            for row in self.fetch_table("LH_COV_INS_RNL_RT")
            if int(row["COV_PHA_NBR"]) == cov_pha_nbr
            and str(row["PRM_RT_TYP_CD"]).strip() == "M"
            and str(row["JT_INS_IND"]).strip() == "0"
        }
        alphabet = "XYABCDEFGHIJK" if structure in ("6", "06") else "ABCDEFGHIJK"
        if len(codes) != 1:
            raise ValueError(f"Coverage {cov_pha_nbr}: missing or ambiguous stored MTP band")
        code = codes.pop()
        if len(code) != 1 or code not in alphabet:
            raise ValueError(f"Coverage {cov_pha_nbr}: invalid stored MTP band {code!r}")
        return alphabet.index(code) + 1

    def cov_band(self, cov_index: int) -> Optional[int]:
        """
        Get face amount band for coverage.

        Base coverage bands are based on the total face amount across base
        coverages. Rider coverage bands are based only on that rider's face
        amount.

        Args:
            cov_index: Coverage index (1-based)

        Returns:
            Band number or None if not determinable
        """
        if cov_index in self.policy._band_cache:
            return self.policy._band_cache[cov_index]

        rates = self._get_rates()
        if rates is None:
            self.policy._band_cache[cov_index] = None
            return None

        covs = self.coverages.get_coverages()
        if not (0 < cov_index <= len(covs)):
            self.policy._band_cache[cov_index] = None
            return None

        cov = covs[cov_index - 1]
        from suiteview.core.band_rules import rider_bands_as_base

        cov_plancode = self.coverages.cov_plancode(cov_index)
        # A base-banding rider (e.g. 1U144A00) acts like a segment of base
        # coverage: it is banded on the BASE plancode's band table using the
        # combined base specified amount — the same band as the policy.
        bands_as_base = cov.is_base or rider_bands_as_base(cov_plancode)
        if bands_as_base:
            band_face = float(self.coverages.base_band_specified_amount)
            band_plancode = self.coverages.base_plancode if not cov.is_base else cov_plancode
        else:
            band_face = float(cov.face_amount or 0)
            band_plancode = cov_plancode

        # Base coverages (and base-banding riders) pass the policy issue date for
        # the Rates_Control-CZ issue-date band boundary (see Rates.get_band); the
        # rule never applies to ordinary rider band tables, so they stay dateless.
        band = rates.get_band(
            band_plancode, band_face,
            issue_date=self.activity.issue_date if bands_as_base else None,
        )
        self.policy._band_cache[cov_index] = band
        return band

    def rates_coi(self, cov_index: int, scale: int = 1) -> Optional[List[float]]:
        """
        Get COI rates for coverage.

        Args:
            cov_index: Coverage index (1-based)
            scale: Rate scale (default 1)

        Returns:
            List of COI rates by duration (1-indexed) or None
        """
        rates = self._get_rates()
        if rates is None:
            return None

        band = self.cov_band(cov_index)
        if band is None:
            return None

        sex_code = self.renewal_cov_sex_code(cov_index)
        sex = self._translate_sex_for_rates(sex_code)

        return rates.get_coi(
            plancode=self.coverages.cov_plancode(cov_index),
            issue_age=self.coverages.cov_issue_age(cov_index),
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(cov_index),
            scale=scale,
            band=band
        )

    def rates_mtp(self, cov_index: int) -> Optional[float]:
        """
        Get Maximum Target Premium for coverage.

        Args:
            cov_index: Coverage index (1-based)

        Returns:
            MTP rate or None
        """
        rates = self._get_rates()
        if rates is None:
            return None

        band = self.cov_band(cov_index)
        if band is None:
            return None

        sex_code = self.renewal_cov_sex_code(cov_index)
        sex = self._translate_sex_for_rates(sex_code)

        result = rates.get_mtp(
            plancode=self.coverages.cov_plancode(cov_index),
            issue_age=self.coverages.cov_issue_age(cov_index),
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(cov_index),
            band=band
        )
        return result if result else "NA"

    def rates_ctp(self, cov_index: int) -> Optional[float]:
        """
        Get Commission Target Premium for coverage.

        Args:
            cov_index: Coverage index (1-based)

        Returns:
            CTP rate or None
        """
        rates = self._get_rates()
        if rates is None:
            return None

        band = self.cov_band(cov_index)
        if band is None:
            return None

        sex_code = self.renewal_cov_sex_code(cov_index)
        sex = self._translate_sex_for_rates(sex_code)

        result = rates.get_ctp(
            plancode=self.coverages.cov_plancode(cov_index),
            issue_age=self.coverages.cov_issue_age(cov_index),
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(cov_index),
            band=band
        )
        return result if result else "NA"

    def rates_tbl1_mtp(self, cov_index: int) -> Optional[float]:
        """
        Get Table 1 Maximum Target Premium for coverage.

        Args:
            cov_index: Coverage index (1-based)

        Returns:
            TBL1MTP rate or None
        """
        rates = self._get_rates()
        if rates is None:
            return None

        band = self.cov_band(cov_index)
        if band is None:
            return None

        sex_code = self.renewal_cov_sex_code(cov_index)
        sex = self._translate_sex_for_rates(sex_code)

        result = rates.get_tbl1_mtp(
            plancode=self.coverages.cov_plancode(cov_index),
            issue_age=self.coverages.cov_issue_age(cov_index),
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(cov_index),
            band=band
        )
        return result if result else "NA"

    def rates_tbl1_ctp(self, cov_index: int) -> Optional[float]:
        """
        Get Table 1 Commission Target Premium for coverage.

        Args:
            cov_index: Coverage index (1-based)

        Returns:
            TBL1CTP rate or None
        """
        rates = self._get_rates()
        if rates is None:
            return None

        band = self.cov_band(cov_index)
        if band is None:
            return None

        sex_code = self.renewal_cov_sex_code(cov_index)
        sex = self._translate_sex_for_rates(sex_code)

        result = rates.get_tbl1_ctp(
            plancode=self.coverages.cov_plancode(cov_index),
            issue_age=self.coverages.cov_issue_age(cov_index),
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(cov_index),
            band=band
        )
        return result if result else "NA"

    def rates_epu(self, cov_index: int, scale: int = 1) -> Optional[List[float]]:
        """
        Get Extended Paid-Up rates for coverage.

        Args:
            cov_index: Coverage index (1-based)
            scale: Rate scale (default 1)

        Returns:
            List of EPU rates by duration (1-indexed) or None
        """
        rates = self._get_rates()
        if rates is None:
            return None

        band = self.cov_band(cov_index)
        if band is None:
            return None

        sex_code = self.renewal_cov_sex_code(cov_index)
        sex = self._translate_sex_for_rates(sex_code)

        return rates.get_epu(
            plancode=self.coverages.cov_plancode(cov_index),
            issue_age=self.coverages.cov_issue_age(cov_index),
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(cov_index),
            scale=scale,
            band=band
        )

    def rates_scr(self, cov_index: int, scale: int = 1) -> Optional[List[float]]:
        """
        Get Surrender Charge rates for coverage.

        Args:
            cov_index: Coverage index (1-based)
            scale: Rate scale (default 1)

        Returns:
            List of SCR rates by duration (1-indexed) or None
        """
        rates = self._get_rates()
        if rates is None:
            return None

        band = self.cov_band(cov_index)
        if band is None:
            return None

        sex_code = self.renewal_cov_sex_code(cov_index)
        sex = self._translate_sex_for_rates(sex_code)

        return rates.get_scr(
            plancode=self.coverages.cov_plancode(cov_index),
            issue_age=self.coverages.cov_issue_age(cov_index),
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(cov_index),
            band=band,
            state=self.product.issue_state
        )

    def rates_corr(self) -> Optional[List[float]]:
        """
        Get Corridor rates for base coverage.

        Returns:
            List of corridor rates by attained age or None
        """
        rates = self._get_rates()
        if rates is None:
            return None

        return rates.get_corr(
            plancode=self.coverages.cov_plancode(1),
            issue_age=self.coverages.cov_issue_age(1)
        )

    def rates_gint(self) -> Optional[List[float]]:
        """
        Get Guaranteed Interest rates for base coverage.

        Returns:
            List of GINT rates by duration or None
        """
        rates = self._get_rates()
        if rates is None:
            return None

        return rates.get_gint(plancode=self.coverages.cov_plancode(1))

    def rates_epp(self, scale: int) -> Optional[List[float]]:
        """
        Get Expense Per Premium rates for base coverage.

        Args:
            scale: Rate scale

        Returns:
            List of EPP rates by duration or None
        """
        rates = self._get_rates()
        if rates is None:
            return None

        band = self.cov_band(1)
        if band is None:
            return None

        sex_code = self.renewal_cov_sex_code(1)
        sex = self._translate_sex_for_rates(sex_code)

        return rates.get_epp(
            plancode=self.coverages.cov_plancode(1),
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(1),
            scale=scale,
            band=band
        )

    def rates_tpp(self, scale: int) -> Optional[List[float]]:
        """
        Get Target Premium Percent rates for base coverage.

        Args:
            scale: Rate scale

        Returns:
            List of TPP rates by duration or None
        """
        rates = self._get_rates()
        if rates is None:
            return None

        band = self.cov_band(1)
        if band is None:
            return None

        sex_code = self.renewal_cov_sex_code(1)
        sex = self._translate_sex_for_rates(sex_code)

        return rates.get_tpp(
            plancode=self.coverages.cov_plancode(1),
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(1),
            scale=scale,
            band=band
        )

    def rates_mfee(self, scale: int) -> Optional[List[float]]:
        """
        Get Monthly Fee rates for base coverage.

        Args:
            scale: Rate scale

        Returns:
            List of MFEE rates by duration or None
        """
        rates = self._get_rates()
        if rates is None:
            return None

        band = self.cov_band(1)
        if band is None:
            return None

        sex_code = self.renewal_cov_sex_code(1)
        sex = self._translate_sex_for_rates(sex_code)

        return rates.get_mfee(
            plancode=self.coverages.cov_plancode(1),
            issue_age=self.coverages.cov_issue_age(1),
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(1),
            scale=scale,
            band=band
        )

    def rates_ben_coi(self, ben_index: int, scale: int = 1) -> Optional[List[float]]:
        """
        Get Benefit COI rates.

        Args:
            ben_index: Benefit index (1-based)
            scale: Rate scale (default 1)

        Returns:
            List of BENCOI rates by duration or None
        """
        rates = self._get_rates()
        if rates is None:
            return None

        band = self.cov_band(1)
        if band is None:
            return None

        sex_code = self.renewal_cov_sex_code(1)
        sex = self._translate_sex_for_rates(sex_code)

        benefits = self.benefits.get_benefits()
        if ben_index < 1 or ben_index > len(benefits):
            return None
        ben = benefits[ben_index - 1]

        return rates.get_ben_coi(
            plancode=self.coverages.cov_plancode(1),
            issue_age=ben.issue_age,
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(1),
            scale=scale,
            band=band,
            benefit_type=ben.benefit_code
        )

    def rates_ben_ctp(self, ben_index: int) -> Optional[float]:
        """
        Get Benefit Commission Target Premium.

        Args:
            ben_index: Benefit index (1-based)

        Returns:
            BENCTP rate or None
        """
        rates = self._get_rates()
        if rates is None:
            return None

        band = self.cov_band(1)
        if band is None:
            return None

        sex_code = self.renewal_cov_sex_code(1)
        sex = self._translate_sex_for_rates(sex_code)

        benefits = self.benefits.get_benefits()
        if ben_index < 1 or ben_index > len(benefits):
            return None
        ben = benefits[ben_index - 1]

        result = rates.get_ben_ctp(
            plancode=self.coverages.cov_plancode(1),
            issue_age=ben.issue_age,
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(1),
            band=band,
            benefit_type=ben.benefit_code
        )
        return result if result else None

    def rates_ben_mtp(self, ben_index: int) -> Optional[float]:
        """
        Get Benefit Maximum Target Premium.

        Args:
            ben_index: Benefit index (1-based)

        Returns:
            BENMTP rate or None
        """
        rates = self._get_rates()
        if rates is None:
            return None

        band = self.cov_band(1)
        if band is None:
            return None

        sex_code = self.renewal_cov_sex_code(1)
        sex = self._translate_sex_for_rates(sex_code)

        benefits = self.benefits.get_benefits()
        if ben_index < 1 or ben_index > len(benefits):
            return None
        ben = benefits[ben_index - 1]

        result = rates.get_ben_mtp(
            plancode=self.coverages.cov_plancode(1),
            issue_age=ben.issue_age,
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(1),
            band=band,
            benefit_type=ben.benefit_code
        )
        return result if result else None
