"""PolicyInformation coverages section."""

from __future__ import annotations

from .base import PolicySection
from ..cl_polrec.policy_data_classes import CoverageInfo
from ..cl_polrec.policy_data_classes import SkippedPeriodInfo
from ..cl_polrec.policy_data_classes import SubstandardRatingInfo
from ..cl_polrec.policy_translations import PERSON_CODES
from ..cl_polrec.policy_translations import PRODUCT_LINE_CODES
from ..cl_polrec.policy_translations import SEX_CODES
from ..cl_polrec.policy_translations import SEX_CODE_DISPLAY
from ..cl_polrec.policy_translations import rate_class_description
from ..cl_polrec.policy_translations import translate_benefit_period_code
from ..cl_polrec.policy_translations import translate_elimination_period_code
from ..cl_polrec.policy_translations import translate_substandard_type_code
from ..cl_polrec.policy_translations import translate_table_rating
from datetime import date
from decimal import Decimal
from decimal import ROUND_HALF_UP
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

import logging

logger = logging.getLogger(__name__)


class CoveragesSection(PolicySection):
    """Cohesive PolicyInformation coverages view."""

    CACHE_ATTRS = ('_coverages',)

    @property
    def number_of_lives_code(self) -> str:
        """Base phase 1 FCVLIVES-LIVES: 1 single, 2 first-to-die, 3 second-to-die."""
        value = self.data_item_where(
            "LH_COV_PHA", "NBR_OF_LIVES_CD", "COV_PHA_NBR", 1,
        )
        code = str(value).strip() if value is not None else ""
        if code not in ("1", "2", "3"):
            raise ValueError(
                f"Missing or invalid LH_COV_PHA.NBR_OF_LIVES_CD "
                f"for base coverage phase 1: {value!r}"
            )
        return code

    @property
    def insured_lives_description(self) -> str:
        """Single/joint classification from the base coverage's lives code."""
        return {
            "1": "Single",
            "2": "Joint First to Die",
            "3": "Joint Second to Die",
        }[self.number_of_lives_code]

    @property
    def is_joint_insured(self) -> bool:
        """Whether the base coverage is joint first-to-die or second-to-die."""
        return self.number_of_lives_code in ("2", "3")

    @property
    def base_plancode(self) -> str:
        """Base coverage plancode (from first coverage phase)."""
        covs = self.get_coverages()
        return covs[0].plancode if covs else ""

    @property
    def base_face_amount(self) -> Optional[Decimal]:
        """Base coverage face amount (units * VPU)."""
        covs = self.get_base_coverages()
        return covs[0].face_amount if covs else None

    @property
    def base_units(self) -> Optional[Decimal]:
        """Base coverage raw unit count."""
        covs = self.get_base_coverages()
        return covs[0].units if covs else None

    @property
    def base_total_face_amount(self) -> Decimal:
        """Total face amount across all base coverages (for UL increases)."""
        total = Decimal("0")
        for cov in self.get_base_coverages():
            if cov.face_amount:
                total += cov.face_amount
        return total

    def _coverage_is_active(self, cov: CoverageInfo, as_of_date: Optional[date] = None) -> bool:
        """Return whether a coverage is active as of the valuation date."""
        effective_date = as_of_date or self.values.valuation_date or date.today()
        if cov.terminate_date and cov.terminate_date <= effective_date:
            return False

        status = str(cov.nxt_chg_typ_cd or cov.cov_status or "").strip()
        if status == "0":
            return bool(cov.nxt_chg_dt and cov.nxt_chg_dt > effective_date)
        return True

    @staticmethod
    def _covers_primary_insured(cov: CoverageInfo) -> bool:
        """Return whether a coverage applies only to the primary insured."""
        person_code = str(cov.person_code or "").strip()
        if person_code not in ("", "00"):
            return False
        if cov.prs_seq_nbr not in (0, 1):
            return False
        try:
            return int(str(cov.lives_cov_cd or "1").strip() or "1") <= 1
        except (TypeError, ValueError):
            return False

    @property
    def primary_insured_face_amount(self) -> Decimal:
        """Active face amount covering the primary insured only."""
        total = Decimal("0")
        for cov in self.get_coverages():
            if not self._covers_primary_insured(cov):
                continue
            if not self._coverage_is_active(cov):
                continue
            if cov.face_amount:
                total += cov.face_amount

        if total:
            return total
        return self.base_face_amount or Decimal("0")

    @property
    def primary_insured_db_layers(self) -> List[Tuple[Decimal, Optional[date]]]:
        """Active death-benefit layers covering the primary insured, with expiry.

        Returns a list of ``(face_amount, expiry_date)`` tuples — one per active
        coverage that covers the primary insured (the base coverage plus any
        level-term riders written on the primary insured). ``expiry_date`` is the
        coverage's maturity/expiry date (``COV_MT_EXP_DT``); the base coverage
        expires at policy maturity while a level-term rider expires at the end of
        its level period, at which point its face drops out of the death benefit.

        Mirrors :pyattr:`primary_insured_face_amount` (same coverage selection),
        but preserves per-layer detail so consumers can project a declining death
        benefit. Falls back to the base coverage when no per-insured coverage is
        found.
        """
        layers: List[Tuple[Decimal, Optional[date]]] = []
        for cov in self.get_coverages():
            if not self._covers_primary_insured(cov):
                continue
            if not self._coverage_is_active(cov):
                continue
            if cov.face_amount:
                layers.append((cov.face_amount, cov.maturity_date))

        if layers:
            return layers

        covs = self.get_base_coverages()
        if covs and covs[0].face_amount:
            return [(covs[0].face_amount, covs[0].maturity_date)]
        return []

    @property
    def current_account_value(self) -> Optional[Decimal]:
        """Recorded account value at the most recent monthliversary, if present."""
        return self.values.mv_av(0)

    @property
    def standard_death_benefit(self) -> Decimal:
        """Death benefit before the 7702 corridor test.

        Face amount covering the primary insured plus the DB-option amount
        (option B adds the account value, option C adds premiums paid).
        """
        total = self.primary_insured_face_amount
        db_option = str(self.product.db_option_code or "").strip().upper()

        if db_option in ("2", "B"):
            account_value = self.current_account_value
            if account_value:
                total += account_value
        elif db_option in ("3", "C"):
            premiums_paid = self.billing.total_premiums_paid
            if premiums_paid:
                total += premiums_paid

        return total

    @property
    def corridor_death_benefit(self) -> Optional[Decimal]:
        """Corridor (7702 minimum) death benefit — AV × corridor percent.

        Mirrors the CyberLife/VBA audit rule
        ``ROUND(LH_POL_MVRY_VAL.CSV_AMT * LH_NON_TRD_POL.CDR_PCT / 100, 2)``.
        Returns ``None`` when the corridor does not apply (traditional product,
        or no account value / corridor percent on file).
        """
        if not self.product.is_advanced_product:
            return None

        account_value = self.current_account_value
        if not account_value or account_value <= 0:
            return None

        percent = self.product.corridor_percent
        if percent is None or percent <= 0:
            return None

        return (Decimal(account_value) * Decimal(percent) / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    @property
    def corridor_amount(self) -> Decimal:
        """Amount the corridor adds on top of the standard death benefit (0 if none)."""
        corridor_db = self.corridor_death_benefit
        if corridor_db is None:
            return Decimal("0")
        excess = corridor_db - self.standard_death_benefit
        return excess if excess > 0 else Decimal("0")

    @property
    def is_in_corridor(self) -> bool:
        """Whether the corridor death benefit exceeds the standard death benefit."""
        return self.corridor_amount > 0

    @property
    def total_death_benefit(self) -> Decimal:
        """Total death benefit — the greater of the standard and corridor amounts.

        The corridor (IRC 7702 minimum death benefit) applies when the account
        value has grown large enough that ``AV × corridor %`` exceeds the face
        amount plus the DB-option amount.
        """
        standard = self.standard_death_benefit
        corridor_db = self.corridor_death_benefit
        if corridor_db is not None and corridor_db > standard:
            return corridor_db
        return standard

    @property
    def base_issue_age(self) -> Optional[int]:
        """Base insured issue age."""
        covs = self.get_base_coverages()
        return covs[0].issue_age if covs else None

    @property
    def base_sex_code(self) -> str:
        """Base insured sex code."""
        covs = self.get_base_coverages()
        return covs[0].sex_code if covs else ""

    @property
    def base_sex_description(self) -> str:
        """Base insured sex description."""
        covs = self.get_base_coverages()
        return covs[0].sex_desc if covs else ""

    @property
    def base_rate_class(self) -> str:
        """Base coverage rate class code."""
        covs = self.get_base_coverages()
        return covs[0].rate_class if covs else ""

    @property
    def base_rate_class_description(self) -> str:
        """Base coverage rate class description."""
        covs = self.get_base_coverages()
        return covs[0].rate_class_desc if covs else ""

    @property
    def attained_age(self) -> Optional[int]:
        """Current attained age of base insured (VBA: CovIssueAge(1) + PolicyYear - 1)."""
        if self.base_issue_age is not None:
            py = self.activity.policy_year
            if py > 0:
                return self.base_issue_age + py - 1
        return None

    @property
    def age_at_maturity(self) -> Optional[int]:
        """Age at maturity of base coverage (VBA: AgeAtMaturity).
        Calculated as issue_age + years from issue to maturity date."""
        covs = self.get_base_coverages()
        if not covs:
            return None
        cov = covs[0]
        issue_date = cov.issue_date
        maturity_date = cov.maturity_date
        issue_age = cov.issue_age
        if issue_date and maturity_date and issue_age is not None:
            years = maturity_date.year - issue_date.year
            if (maturity_date.month, maturity_date.day) < (issue_date.month, issue_date.day):
                years -= 1
            return issue_age + years
        return None

    @property
    def coverage_count(self) -> int:
        """Number of coverage phases."""
        return self.data_item_count("LH_COV_PHA")

    @property
    def has_annuity_rider(self) -> bool:
        """Whether Policy Support's 0699830R annuity-rider tool applies."""
        return any(
            coverage.plancode.strip().upper() == "0699830R"
            for coverage in self.get_coverages()
        )

    def _th_coverage_rows_by_phase(self) -> Dict[int, Dict[str, Any]]:
        th_cov_data: Dict[int, Dict[str, Any]] = {}
        try:
            th_rows = self.fetch_table("TH_COV_PHA")
            for th_row in th_rows:
                pha = int(th_row.get("COV_PHA_NBR", 0))
                th_cov_data[pha] = th_row
        except Exception:
            pass  # Table may not exist for all policies
        return th_cov_data

    def _substandard_ratings_by_phase(self) -> Dict[int, List[SubstandardRatingInfo]]:
        all_ratings: Dict[int, List[SubstandardRatingInfo]] = {}
        for rating in self.get_substandard_ratings():
            all_ratings.setdefault(rating.coverage_phase, []).append(rating)
        return all_ratings

    @staticmethod
    def _base_plancode_from_coverage_rows(rows: List[Dict[str, Any]]) -> str:
        if not rows:
            return ""
        return str(rows[0].get("PLN_DES_SER_CD", "")).strip()

    def _coverage_amount_fields(self, row: Dict[str, Any]):
        units = self._parse_optional_decimal(row.get("COV_UNT_QTY"))
        orig_units = self._parse_optional_decimal(row.get("OGN_SPC_UNT_QTY"))
        vpu = self._parse_optional_decimal(row.get("COV_VPU_AMT"))
        premium_rate = self._parse_optional_decimal(row.get("ANN_PRM_UNT_AMT"))
        face_amount = (units * vpu) if (units is not None and vpu is not None) else None
        orig_amount = (orig_units * vpu) if (orig_units is not None and vpu is not None) else None
        return units, orig_units, vpu, premium_rate, face_amount, orig_amount

    @staticmethod
    def _coverage_substandard_fields(cov_ratings: List[SubstandardRatingInfo]):
        table_rating = None
        table_rating_code = ""
        table_cease_date = None
        flat_extra = None
        flat_cease_date = None
        for rating in cov_ratings:
            if rating.type_code == "T" and rating.table_rating_numeric and rating.table_rating_numeric > 0:
                table_rating = rating.table_rating_numeric
                table_rating_code = rating.table_rating or ""
                if rating.flat_cease_date:
                    table_cease_date = rating.flat_cease_date
            if rating.type_code == "F":
                if rating.flat_amount is not None:
                    flat_extra = rating.flat_amount
                if rating.flat_cease_date:
                    flat_cease_date = rating.flat_cease_date
        return table_rating, table_rating_code, table_cease_date, flat_extra, flat_cease_date

    def _build_coverage_info(
        self,
        row: Dict[str, Any],
        th_cov_data: Dict[int, Dict[str, Any]],
        all_ratings: Dict[int, List[SubstandardRatingInfo]],
        base_plancode: str,
    ) -> CoverageInfo:
        cov_pha_nbr = int(row.get("COV_PHA_NBR", 0))
        plancode = str(row.get("PLN_DES_SER_CD", "")).strip()
        units, orig_units, vpu, premium_rate, face_amount, orig_amount = (
            self._coverage_amount_fields(row)
        )
        th_row = th_cov_data.get(cov_pha_nbr, {})
        cola_indicator = str(th_row.get("COLA_INCR_IND", "")) if th_row else ""
        status_code = str(row.get("NXT_CHG_TYP_CD", ""))
        elim_code = str(row.get("AH_ACC_ELM_PER_CD", "") or "")
        bnf_code = str(row.get("AH_ACC_BNF_PER_CD", "") or "")
        substandard = self._coverage_substandard_fields(all_ratings.get(cov_pha_nbr, []))
        table_rating, table_rating_code, table_cease_date, flat_extra, flat_cease_date = substandard
        return CoverageInfo(
            cov_pha_nbr=cov_pha_nbr,
            plancode=plancode,
            form_number=str(row.get("POL_FRM_NBR", "")).strip(),
            issue_date=self._parse_date(row.get("ISSUE_DT")),
            maturity_date=self._parse_date(row.get("COV_MT_EXP_DT")),
            issue_age=self._parse_optional_int(row.get("INS_ISS_AGE")),
            face_amount=face_amount,
            orig_amount=orig_amount,
            units=units,
            orig_units=orig_units,
            vpu=vpu,
            person_code=str(row.get("PRS_CD", "00")),
            person_desc=PERSON_CODES.get(str(row.get("PRS_CD", "00")), ""),
            sex_code=SEX_CODE_DISPLAY.get(str(row.get("INS_SEX_CD", "")), str(row.get("INS_SEX_CD", ""))),
            sex_desc=SEX_CODES.get(str(row.get("INS_SEX_CD", "")), ""),
            product_line_code=str(row.get("PRD_LIN_TYP_CD", "")),
            product_line_desc=PRODUCT_LINE_CODES.get(str(row.get("PRD_LIN_TYP_CD", "")), ""),
            class_code=str(row.get("INS_CLS_CD", "")),
            rate_class="",
            rate_class_desc="",
            table_rating=table_rating,
            table_rating_code=table_rating_code,
            table_cease_date=table_cease_date,
            cola_indicator=cola_indicator,
            gio_indicator="",
            flat_extra=flat_extra,
            flat_cease_date=flat_cease_date,
            prs_seq_nbr=int(row.get("PRS_SEQ_NBR", 0) or 0),
            lives_cov_cd=str(row.get("LIVES_COV_CD", "")),
            cov_status=status_code,
            cov_status_date=self._parse_date(row.get("NXT_CHG_DT")),
            cov_status_desc="",
            premium_rate=premium_rate,
            nxt_chg_typ_cd=str(row.get("NXT_CHG_TYP_CD", "")),
            nxt_chg_dt=self._parse_date(row.get("NXT_CHG_DT")),
            terminate_date=self._parse_date(row.get("PLN_TMN_DT")),
            is_base=(plancode == base_plancode),
            cov_annual_premium=(
                premium_rate * units
                if premium_rate is not None and units is not None
                else premium_rate
            ),
            annual_premium_per_unit=premium_rate,
            cv_amount=None,
            nsp_amount=None,
            elimination_period=translate_elimination_period_code(elim_code) if elim_code else "",
            benefit_period=translate_benefit_period_code(bnf_code) if bnf_code else "",
            number_of_lives_code=str(row.get("NBR_OF_LIVES_CD") or "").strip(),
            joint_issue_age=self._parse_optional_int(row.get("JNT_ISU_ISS_AGE")),
            joint_mortality_table_code=str(row.get("JNT_ISU_MTL_TBL_CD") or "").strip(),
            raw_data=row
        )

    def _apply_coverage_renewal_fields(
        self,
        cov: CoverageInfo,
        coi_rate_divisor: Decimal | None,
    ) -> None:
        rnl_idx = self.rates.cov_renewal_index(cov.cov_pha_nbr, "C", "0")
        if rnl_idx >= 0:
            rc = str(self.data_item("LH_COV_INS_RNL_RT", "RT_CLS_CD", rnl_idx) or "")
            cov.rate_class = rc
            cov.rate_class_desc = rate_class_description(rc, cov.plancode)
            rnl_sex = str(self.data_item("LH_COV_INS_RNL_RT", "RT_SEX_CD", rnl_idx) or "")
            if rnl_sex:
                cov.sex_code = SEX_CODE_DISPLAY.get(rnl_sex, rnl_sex)
                cov.sex_desc = SEX_CODES.get(rnl_sex, "")
        if coi_rate_divisor is not None and rnl_idx >= 0:
            raw_rate = self.data_item("LH_COV_INS_RNL_RT", "RNL_RT", rnl_idx)
            if raw_rate is not None and str(raw_rate).strip() != "":
                try:
                    rate = Decimal(str(raw_rate))
                except ArithmeticError as exc:
                    raise ValueError(f"Invalid COI renewal rate {raw_rate!r}") from exc
                cov.coi_rate = rate / coi_rate_divisor

    def get_coverages(self) -> List[CoverageInfo]:
        """Get all coverage phases with complete field mapping.

        Coverage classification:
        - is_base=True for all coverages sharing the same plancode as COV_PHA_NBR=1
          (for UL products, coverage increases are added as additional base coverages)
        - is_base=False for riders (different plancode from coverage 1)

        Substandard ratings (table_rating, table_cease_date, flat_extra,
        flat_cease_date) and
        TH_COV_PHA fields (cv_amount, nsp_amount) are populated during build.

        """
        if self._coverages is not None:
            return self._coverages

        # Don't set self._coverages until we succeed — prevents caching a
        # partial/empty list if an exception occurs mid-build.
        built: List[CoverageInfo] = []
        th_cov_data = self._th_coverage_rows_by_phase()
        all_ratings = self._substandard_ratings_by_phase()
        lh_rows = self.fetch_table("LH_COV_PHA")
        base_plancode = self._base_plancode_from_coverage_rows(lh_rows)
        rules = self.product._product_rules_for_rate_display()
        coi_rate_divisor = rules.coi_rate_divisor()

        for i, row in enumerate(lh_rows):
            try:
                cov = self._build_coverage_info(row, th_cov_data, all_ratings, base_plancode)
                self._apply_coverage_renewal_fields(cov, coi_rate_divisor)
                built.append(cov)
            except Exception as _cov_exc:
                logger.error(
                    "Failed to build coverage row %s (COV_PHA_NBR=%s)",
                    i,
                    row.get("COV_PHA_NBR", "?"),
                    exc_info=True,
                )
                raise RuntimeError(
                    f"Failed to build coverage row {i} "
                    f"(COV_PHA_NBR={row.get('COV_PHA_NBR', '?')})"
                ) from _cov_exc

        self._coverages = built
        return self._coverages

    def get_base_coverages(self) -> List[CoverageInfo]:
        """Get all base coverages (same plancode as coverage 1).

        For UL products, coverage increases are added as additional coverages
        with the same plancode as the original base. All such coverages are
        considered base coverages.
        """
        return [c for c in self.get_coverages() if c.is_base]

    def get_base_coverage(self) -> Optional[CoverageInfo]:
        """Get primary base coverage (COV_PHA_NBR = 1).

        Deprecated: Use get_base_coverages() for UL products with increases.
        """
        covs = self.get_base_coverages()
        return covs[0] if covs else None

    def get_riders(self) -> List[CoverageInfo]:
        """Get rider coverages (different plancode from base)."""
        return [c for c in self.get_coverages() if not c.is_base]

    def cov_index_for_phase(self, cov_pha_nbr: int) -> int:
        """PolView's 1-based coverage index for a COV_PHA_NBR (phases can have gaps)."""
        for index, cov in enumerate(self.get_coverages(), start=1):
            if cov.cov_pha_nbr == cov_pha_nbr:
                return index
        raise ValueError(f"Coverage phase {cov_pha_nbr} is not on the policy")

    def cov_plancode(self, index: int) -> str:
        """Get plancode for coverage at index (1-based)."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].plancode
        return ""

    def cov_face_amount(self, index: int) -> Optional[Decimal]:
        """Get face amount for coverage at index (1-based). Returns units * VPU."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].face_amount
        return None

    def cov_issue_age(self, index: int) -> Optional[int]:
        """Get issue age for coverage at index (1-based)."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].issue_age
        return None

    def cov_issue_date(self, index: int) -> Optional[date]:
        """Get coverage issue date (1-based index). Delegates to get_coverages()."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].issue_date
        return None

    def cov_maturity_date(self, index: int) -> Optional[date]:
        """Get coverage maturity/expiry date (1-based index). Delegates to get_coverages()."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].maturity_date
        return None

    def cov_amount(self, index: int) -> Optional[Decimal]:
        """Get coverage face amount (units * VPU) (1-based index). Delegates to get_coverages()."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].face_amount
        return None

    def cov_orig_amount(self, index: int) -> Optional[Decimal]:
        """Get coverage original face amount (1-based index). Delegates to get_coverages()."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].orig_amount
        return None

    @property
    def total_specified_amount(self) -> Decimal:
        """Total specified amount across all *active* base coverages.

        Terminated (or otherwise inactive) base coverages no longer contribute
        to the policy's specified amount, so their face is excluded here. This
        matters for band determination: including a terminated base coverage's
        face would over-count the total and can push the policy into a higher
        band than CyberLife (e.g. band 3 vs band 2 across the 250,000 boundary).
        """
        total = Decimal("0")
        for cov in self.get_base_coverages():
            if cov.face_amount and self._coverage_is_active(cov):
                total += cov.face_amount
        return total

    def _base_banding_rider_face(self) -> Decimal:
        """Face of active riders that band as base coverage (see core.band_rules).

        A few riders (e.g. ``1U144A00`` on IUL08 plans) act like a segment of
        base coverage: their face is folded into the base specified amount when
        determining the band. This returns the total such rider face; it is
        added ONLY to the band-determining face, never to the death-benefit
        specified amount.
        """
        from suiteview.core.band_rules import rider_bands_as_base

        total = Decimal("0")
        for cov in self.get_riders():
            if (
                cov.face_amount
                and self._coverage_is_active(cov)
                and rider_bands_as_base(cov.plancode)
            ):
                total += cov.face_amount
        return total

    @property
    def base_band_specified_amount(self) -> Decimal:
        """Specified amount used for BASE band determination.

        Active base coverages plus any rider that bands as base coverage. Kept
        separate from ``total_specified_amount`` (which stays base-only for
        display/export) so the rider quirk only ever moves the band.
        """
        return self.total_specified_amount + self._base_banding_rider_face()

    def get_substandard_ratings(self, cov_pha_nbr: int = None) -> List[SubstandardRatingInfo]:
        """Get substandard/flat extra ratings, optionally filtered by coverage."""
        ratings = []
        for row in self.fetch_table("LH_SST_XTR_CRG"):
            phase = int(row.get("COV_PHA_NBR", 0) or 0)
            if cov_pha_nbr is not None and phase != cov_pha_nbr:
                continue

            type_code = str(row.get("SST_XTR_TYP_CD", "") or "")
            translated_type = translate_substandard_type_code(type_code)
            table_letter = str(row.get("SST_XTR_RT_TBL_CD", "") or "").strip()

            rating = SubstandardRatingInfo(
                coverage_phase=phase,
                person_seq=int(row.get("PRS_SEQ_NBR", 0) or 0),
                joint_indicator=str(row.get("JT_INS_IND", "") or ""),
                type_code=translated_type,
                type_desc="Table Rating" if translated_type == "T" else "Flat Extra",
                table_rating=table_letter,
                table_rating_numeric=translate_table_rating(table_letter),
                flat_amount=self._parse_optional_decimal(row.get("XTR_PER_1000_AMT")),
                flat_cease_date=self._parse_date(row.get("SST_XTR_CEA_DT")),
                duration=int(row.get("SST_XTR_CEA_DUR", 0) or 0) or None,
                raw_data=row
            )
            ratings.append(rating)
        return ratings

    def cov_table_rating(self, index: int) -> int:
        """Get coverage table rating as number (1-based index). Returns 0 if none."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].table_rating or 0
        return 0

    def cov_table_rating_code(self, index: int) -> str:
        """Get coverage table rating letter code (1-based index). Returns '' if none."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].table_rating_code or ""
        return ""

    def cov_table_cease_date(self, index: int) -> Optional[date]:
        """Get coverage table rating cease date (1-based index). Delegates to get_coverages()."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].table_cease_date
        return None

    def cov_flat_extra(self, index: int) -> Optional[Decimal]:
        """Get coverage flat extra amount (1-based index). Delegates to get_coverages()."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].flat_extra
        return None

    def cov_flat_cease_date(self, index: int) -> Optional[date]:
        """Get coverage flat extra cease date (1-based index). Delegates to get_coverages()."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].flat_cease_date
        return None

    def get_skipped_periods(self, cov_pha_nbr: int = None) -> List[SkippedPeriodInfo]:
        """Get skipped/reinstatement periods, optionally filtered by coverage."""
        periods = []
        for row in self.fetch_table("LH_COV_SKIPPED_PER"):
            phase = int(row.get("COV_PHA_NBR", 0) or 0)
            if cov_pha_nbr is not None and phase != cov_pha_nbr:
                continue

            period = SkippedPeriodInfo(
                coverage_phase=phase,
                period_type=str(row.get("SKP_TYP_CD", "") or ""),
                skip_from_date=self._parse_date(row.get("SKP_FRM_DT")),
                skip_to_date=self._parse_date(row.get("SKP_TO_DT")),
                raw_data=row
            )
            periods.append(period)
        return periods

    @property
    def skipped_period_count(self) -> int:
        """Count of skipped period records."""
        return self.data_item_count("LH_COV_SKIPPED_PER")

    def skipped_from_date(self, index: int) -> Optional[date]:
        """Get skipped period from date (1-based index)."""
        return self._parse_date(self.data_item("LH_COV_SKIPPED_PER", "SKP_FRM_DT", index - 1))

    def skipped_to_date(self, index: int) -> Optional[date]:
        """Get skipped period to date (1-based index)."""
        return self._parse_date(self.data_item("LH_COV_SKIPPED_PER", "SKP_TO_DT", index - 1))

    def skipped_cov_phase(self, index: int) -> int:
        """Get skipped period coverage phase (1-based index)."""
        val = self.data_item("LH_COV_SKIPPED_PER", "COV_PHA_NBR", index - 1)
        return int(val) if val else 0
