"""
CL_POLREC_02_03_09_67 — Coverage Records (02, 03, 09, 67)
===========================================================

DB2 tables
----------
Record 02 — Coverage Phase
    LH_COV_PHA          Primary coverage phase rows
    TH_COV_PHA          Tracking history (COLA, GIO, CV, NSP)

Record 03 — Substandard / Extra Charges
    LH_SST_XTR_CRG     Table ratings and flat extras

Record 09 — Skipped Periods
    LH_COV_SKIPPED_PER  Reinstatement / skip ranges

Record 67 — Renewal Rates & Coverage Targets
    LH_COV_INS_RNL_RT  Coverage-level renewal rates
    LH_COV_TARGET       Coverage-level targets (CCV, surrender, etc.)
"""

from __future__ import annotations

from decimal import Decimal
from datetime import date
from typing import Any, Dict, List, Optional

from .cyberlife_base import PolicyDataAccessor, parse_date
from .policy_data_classes import (
    CoverageInfo,
    CoverageTargetInfo,
    RenewalCovRateInfo,
    SkippedPeriodInfo,
    SubstandardRatingInfo,
)
from .policy_translations import (
    PERSON_CODES,
    PRODUCT_LINE_CODES,

    RATE_CLASS_CODES,
    SEX_CODE_DISPLAY,
    SEX_CODES,
    translate_benefit_period_code,
    translate_coverage_target_type,
    translate_elimination_period_code,
    translate_renewal_rate_type_code,
    translate_substandard_type_code,
    translate_table_rating,
)


class CoverageRecords:
    """System-layer access for coverage-related Cyberlife policy records.

    Parameters
    ----------
    policy : PolicyDataAccessor
        Object satisfying the data-access protocol.
    """

    TABLES = (
        "LH_COV_PHA",
        "TH_COV_PHA",
        "LH_SST_XTR_CRG",
        "LH_COV_SKIPPED_PER",
        "LH_COV_INS_RNL_RT",
        "LH_COV_TARGET",
    )

    def __init__(self, policy: PolicyDataAccessor) -> None:
        self._policy = policy
        self._coverages: Optional[List[CoverageInfo]] = None

    def invalidate(self) -> None:
        """Clear local coverage cache."""
        self._coverages = None

    # =====================================================================
    # RECORD 02 — COVERAGE PHASES  (LH_COV_PHA / TH_COV_PHA)
    # =====================================================================

    @property
    def coverage_count(self) -> int:
        return self._policy.data_item_count("LH_COV_PHA")

    def get_coverages(self) -> List[CoverageInfo]:
        """Build the full list of CoverageInfo objects."""
        if self._coverages is not None:
            return self._coverages

        self._coverages = []

        # TH_COV_PHA join data
        th_cov_data: Dict[int, Dict[str, Any]] = {}
        try:
            for th_row in self._policy.fetch_table("TH_COV_PHA"):
                pha = int(th_row.get("COV_PHA_NBR", 0))
                th_cov_data[pha] = th_row
        except Exception:
            pass

        # Pre-fetch substandard ratings
        all_ratings: Dict[int, List[SubstandardRatingInfo]] = {}
        try:
            for rating in self.get_substandard_ratings():
                phase = rating.COV_PHA_NBR
                all_ratings.setdefault(phase, []).append(rating)
        except Exception:
            pass

        # Determine base plancode from first row
        lh_rows = self._policy.fetch_table("LH_COV_PHA")
        base_plancode = ""
        if lh_rows:
            base_plancode = str(lh_rows[0].get("PLN_DES_SER_CD", "")).strip()

        # Detect advanced product (UL/IUL/VUL) vs Traditional
        is_advanced = str(self._policy.data_item("LH_BAS_POL", "NON_TRD_POL_IND", 0) or "") == "1"
        # Policy-level product line code (for COI rate divisor)
        pol_product_line = str(self._policy.data_item("LH_COV_PHA", "PRD_LIN_TYP_CD", 0) or "")

        for _i, row in enumerate(lh_rows):
            cov_pha_nbr = int(row.get("COV_PHA_NBR", 0))
            plancode = str(row.get("PLN_DES_SER_CD", "")).strip()

            # Units & VPU
            units = Decimal(str(row["COV_UNT_QTY"])) if row.get("COV_UNT_QTY") else None
            orig_units = Decimal(str(row["OGN_SPC_UNT_QTY"])) if row.get("OGN_SPC_UNT_QTY") else None
            vpu = Decimal(str(row.get("COV_VPU_AMT") or 0))
            if vpu == 0:
                vpu = None

            face_amount = (units * vpu) if (units is not None and vpu is not None) else None
            orig_amount = (orig_units * vpu) if (orig_units is not None and vpu is not None) else None

            # TH_COV_PHA join
            th_row = th_cov_data.get(cov_pha_nbr, {})
            cola_indicator = str(th_row.get("COLA_INCR_IND", "")) if th_row else ""
            gio_indicator = ""  # OPT_EXER_IND does not exist on TH_COV_PHA
            cv_amount = None    # CV_AMT does not exist on TH_COV_PHA
            nsp_amount = None   # NSP_AMT does not exist on TH_COV_PHA

            # Substandard ratings for this phase
            cov_ratings = all_ratings.get(cov_pha_nbr, [])
            table_rating: Optional[int] = None
            table_rating_code = ""
            flat_extra: Optional[Decimal] = None
            flat_cease_date: Optional[date] = None
            for r in cov_ratings:
                if r.type_code == "T" and r.table_rating_numeric and r.table_rating_numeric > 0:
                    table_rating = r.table_rating_numeric
                    table_rating_code = r.table_rating or ""
                if r.type_code == "F":
                    if r.flat_amount:
                        flat_extra = r.flat_amount
                    if r.flat_cease_date:
                        flat_cease_date = r.flat_cease_date

            # Get status code
            status_code = str(row.get("NXT_CHG_TYP_CD", ""))
            status_date = parse_date(row.get("NXT_CHG_DT"))

            # DI fields
            elim_code = str(row.get("AH_ACC_ELM_PER_CD", "") or "")
            bnf_code = str(row.get("AH_ACC_BNF_PER_CD", "") or "")
            is_base = (plancode == base_plancode)

            cov = CoverageInfo(
                cov_pha_nbr=cov_pha_nbr,
                plancode=plancode,
                form_number=str(row.get("POL_FRM_NBR", "")).strip(),
                issue_date=parse_date(row.get("ISSUE_DT")),
                maturity_date=parse_date(row.get("COV_MT_EXP_DT")),
                issue_age=int(row.get("INS_ISS_AGE") or 0) or None,
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
                rate_class="",   # populated below from LH_COV_INS_RNL_RT
                rate_class_desc="",
                table_rating=table_rating,
                table_rating_code=table_rating_code,
                cola_indicator=cola_indicator,
                gio_indicator=gio_indicator,
                flat_extra=flat_extra,
                flat_cease_date=flat_cease_date,
                prs_seq_nbr=int(row.get("PRS_SEQ_NBR", 0) or 0),
                lives_cov_cd=str(row.get("LIVES_COV_CD", "")),
                cov_status=status_code,
                cov_status_date=status_date,
                cov_status_desc="",
                # Premium rate (Trad) – from LH_COV_PHA.ANN_PRM_UNT_AMT
                premium_rate=Decimal(str(row["ANN_PRM_UNT_AMT"])) if row.get("ANN_PRM_UNT_AMT") else None,
                nxt_chg_typ_cd=str(row.get("NXT_CHG_TYP_CD", "")),
                nxt_chg_dt=parse_date(row.get("NXT_CHG_DT")),
                terminate_date=parse_date(row.get("PLN_TMN_DT")),
                is_base=is_base,
                # Total annual premium = per-unit rate × units
                cov_annual_premium=(
                    Decimal(str(row["ANN_PRM_UNT_AMT"])) * units
                    if row.get("ANN_PRM_UNT_AMT") and units is not None
                    else (Decimal(str(row["ANN_PRM_UNT_AMT"])) if row.get("ANN_PRM_UNT_AMT") else None)
                ),
                # Raw per-unit rate (ANN_PRM_UNT_AMT)
                annual_premium_per_unit=Decimal(str(row["ANN_PRM_UNT_AMT"])) if row.get("ANN_PRM_UNT_AMT") else None,
                cv_amount=cv_amount,
                nsp_amount=nsp_amount,
                elimination_period=translate_elimination_period_code(elim_code) if elim_code else "",
                benefit_period=translate_benefit_period_code(bnf_code) if bnf_code else "",
                raw_data=row,
            )

            # Rate class & sex — from LH_COV_INS_RNL_RT (Record 67)
            # Look up the renewal rate record for this coverage phase.
            # The 67 segment has per-coverage sex (RT_SEX_CD) and rate class
            # (RT_CLS_CD).  LH_COV_PHA.INS_SEX_CD may be the same for all
            # coverages, so the 67 segment is the authoritative source.
            rnl_idx = self.cov_renewal_index(cov_pha_nbr, "C", "0")
            if rnl_idx >= 0:
                rc = str(self._policy.data_item(
                    "LH_COV_INS_RNL_RT", "RT_CLS_CD", rnl_idx
                ) or "")
                cov.rate_class = rc
                cov.rate_class_desc = RATE_CLASS_CODES.get(rc, "")
                # Per-coverage sex code from 67 segment
                rnl_sex = str(self._policy.data_item(
                    "LH_COV_INS_RNL_RT", "RT_SEX_CD", rnl_idx
                ) or "")
                if rnl_sex:
                    cov.sex_code = SEX_CODE_DISPLAY.get(rnl_sex, rnl_sex)
                    cov.sex_desc = SEX_CODES.get(rnl_sex, "")

            # COI rate (Advanced) – from LH_COV_INS_RNL_RT.RNL_RT (type "C")
            # Divided by 100 for product line "I", or 100,000 for others.
            if is_advanced and rnl_idx >= 0:
                raw_rate = self._policy.data_item("LH_COV_INS_RNL_RT", "RNL_RT", rnl_idx)
                if raw_rate is not None:
                    try:
                        r = Decimal(str(raw_rate))
                        if pol_product_line == "I":
                            cov.coi_rate = r / 100
                        else:
                            cov.coi_rate = r / 100000
                    except Exception:
                        pass

            # Flat extra fallback — LH_SST_XTR_CRG is the only source
            # for flat extra data.  LH_COV_INS_RNL_RT does NOT carry
            # flat extra fields (per COBOL DB2 translation workbook).

            self._coverages.append(cov)

        return self._coverages

    def get_base_coverages(self) -> List[CoverageInfo]:
        """Coverages sharing the same plancode as coverage 1."""
        return [c for c in self.get_coverages() if c.is_base]

    def get_riders(self) -> List[CoverageInfo]:
        """Coverages with a different plancode from base."""
        return [c for c in self.get_coverages() if not c.is_base]

    # -- Scalar accessors (1-based index) ----------------------------------

    def cov_plancode(self, index: int) -> str:
        covs = self.get_coverages()
        return covs[index - 1].plancode if 0 < index <= len(covs) else ""

    def cov_face_amount(self, index: int) -> Optional[Decimal]:
        covs = self.get_coverages()
        return covs[index - 1].face_amount if 0 < index <= len(covs) else None

    def cov_issue_age(self, index: int) -> Optional[int]:
        covs = self.get_coverages()
        return covs[index - 1].issue_age if 0 < index <= len(covs) else None

    def cov_issue_date(self, index: int) -> Optional[date]:
        covs = self.get_coverages()
        return covs[index - 1].issue_date if 0 < index <= len(covs) else None

    def cov_maturity_date(self, index: int) -> Optional[date]:
        covs = self.get_coverages()
        return covs[index - 1].maturity_date if 0 < index <= len(covs) else None

    def cov_amount(self, index: int) -> Optional[Decimal]:
        return self.cov_face_amount(index)

    def cov_orig_amount(self, index: int) -> Optional[Decimal]:
        covs = self.get_coverages()
        return covs[index - 1].orig_amount if 0 < index <= len(covs) else None

    # =====================================================================
    # RECORD 03 — SUBSTANDARD EXTRA CHARGES  (LH_SST_XTR_CRG)
    # =====================================================================

    def get_substandard_ratings(self, COV_PHA_NBR: Optional[int] = None) -> List[SubstandardRatingInfo]:
        ratings: List[SubstandardRatingInfo] = []
        for row in self._policy.fetch_table("LH_SST_XTR_CRG"):
            phase = int(row.get("COV_PHA_NBR", 0) or 0)
            if COV_PHA_NBR is not None and phase != COV_PHA_NBR:
                continue

            type_code = str(row.get("SST_XTR_TYP_CD", "") or "")
            translated_type = translate_substandard_type_code(type_code)
            table_letter = str(row.get("SST_XTR_RT_TBL_CD", "") or "").strip()

            rating = SubstandardRatingInfo(
                COV_PHA_NBR=phase,
                PRS_SEQ_NBR=int(row.get("PRS_SEQ_NBR", 0) or 0),
                JT_INS_IND=str(row.get("JT_INS_IND", "") or ""),
                type_code=translated_type,
                type_desc="Table Rating" if translated_type == "T" else "Flat Extra",
                table_rating=table_letter,
                table_rating_numeric=translate_table_rating(table_letter),
                flat_amount=Decimal(str(row["XTR_PER_1000_AMT"])) if row.get("XTR_PER_1000_AMT") else None,
                flat_cease_date=parse_date(row.get("SST_XTR_CEA_DT")),
                duration=int(row.get("SST_XTR_CEA_DUR", 0) or 0) or None,
                raw_data=row,
            )
            ratings.append(rating)
        return ratings

    def cov_table_rating(self, index: int) -> int:
        covs = self.get_coverages()
        return covs[index - 1].table_rating or 0 if 0 < index <= len(covs) else 0

    def cov_table_rating_code(self, index: int) -> str:
        covs = self.get_coverages()
        return covs[index - 1].table_rating_code or "" if 0 < index <= len(covs) else ""

    def cov_flat_extra(self, index: int) -> Optional[Decimal]:
        covs = self.get_coverages()
        return covs[index - 1].flat_extra if 0 < index <= len(covs) else None

    def cov_flat_cease_date(self, index: int) -> Optional[date]:
        covs = self.get_coverages()
        return covs[index - 1].flat_cease_date if 0 < index <= len(covs) else None

    # =====================================================================
    # RECORD 09 — SKIPPED PERIODS  (LH_COV_SKIPPED_PER)
    # =====================================================================

    def get_skipped_periods(self, COV_PHA_NBR: Optional[int] = None) -> List[SkippedPeriodInfo]:
        periods: List[SkippedPeriodInfo] = []
        for row in self._policy.fetch_table("LH_COV_SKIPPED_PER"):
            phase = int(row.get("COV_PHA_NBR", 0) or 0)
            if COV_PHA_NBR is not None and phase != COV_PHA_NBR:
                continue
            period = SkippedPeriodInfo(
                COV_PHA_NBR=phase,
                period_type=str(row.get("SKP_TYP_CD", "") or ""),
                skip_from_date=parse_date(row.get("SKP_FRM_DT")),
                skip_to_date=parse_date(row.get("SKP_TO_DT")),
                raw_data=row,
            )
            periods.append(period)
        return periods

    @property
    def skipped_period_count(self) -> int:
        return self._policy.data_item_count("LH_COV_SKIPPED_PER")

    def skipped_from_date(self, index: int) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_COV_SKIPPED_PER", "SKP_FRM_DT", index - 1))

    def skipped_to_date(self, index: int) -> Optional[date]:
        return parse_date(self._policy.data_item("LH_COV_SKIPPED_PER", "SKP_TO_DT", index - 1))

    def skipped_cov_phase(self, index: int) -> int:
        val = self._policy.data_item("LH_COV_SKIPPED_PER", "COV_PHA_NBR", index - 1)
        return int(val) if val else 0

    # =====================================================================
    # RECORD 67 — RENEWAL RATES  (LH_COV_INS_RNL_RT)
    # =====================================================================

    def get_coverage_renewal_rates(self, COV_PHA_NBR: Optional[int] = None) -> List[RenewalCovRateInfo]:
        rates: List[RenewalCovRateInfo] = []
        for row in self._policy.fetch_table("LH_COV_INS_RNL_RT"):
            phase = int(row.get("COV_PHA_NBR", 0) or 0)
            if COV_PHA_NBR is not None and phase != COV_PHA_NBR:
                continue
            rate_type = str(row.get("PRM_RT_TYP_CD", "") or "")
            rate = RenewalCovRateInfo(
                COV_PHA_NBR=phase,
                rate_type=rate_type,
                rate_type_desc=translate_renewal_rate_type_code(rate_type),
                JT_INS_IND=str(row.get("JT_INS_IND", "") or ""),
                rate_class=str(row.get("RT_CLS_CD", "") or ""),
                rate_class_desc=RATE_CLASS_CODES.get(str(row.get("RT_CLS_CD", "") or ""), ""),
                issue_age=int(row["ISS_AGE"]) if row.get("ISS_AGE") else None,  # TODO: verify column name
                raw_data=row,
            )
            rates.append(rate)
        return rates

    @property
    def renewal_cov_count(self) -> int:
        return self._policy.data_item_count("LH_COV_INS_RNL_RT")

    def cov_renewal_index(self, COV_PHA_NBR: int, rate_type: str = "C", joint_ind: str = "0") -> int:
        for i in range(self.renewal_cov_count):
            if (int(self._policy.data_item("LH_COV_INS_RNL_RT", "COV_PHA_NBR", i) or 0) == COV_PHA_NBR
                    and str(self._policy.data_item("LH_COV_INS_RNL_RT", "PRM_RT_TYP_CD", i) or "") == rate_type
                    and str(self._policy.data_item("LH_COV_INS_RNL_RT", "JT_INS_IND", i) or "") == joint_ind):
                return i
        return -1

    def renewal_cov_rateclass(self, index: int) -> str:
        return str(self._policy.data_item("LH_COV_INS_RNL_RT", "RT_CLS_CD", index) or "")

    def renewal_cov_issue_age(self, index: int) -> Optional[int]:
        val = self._policy.data_item("LH_COV_INS_RNL_RT", "ISS_AGE", index)
        return int(val) if val else None

    # =====================================================================
    # RECORD 67 — COVERAGE TARGETS  (LH_COV_TARGET)
    # =====================================================================

    def get_coverage_targets(self, COV_PHA_NBR: Optional[int] = None) -> List[CoverageTargetInfo]:
        targets: List[CoverageTargetInfo] = []
        for row in self._policy.fetch_table("LH_COV_TARGET"):
            phase = int(row.get("COV_PHA_NBR", 0) or 0)
            if COV_PHA_NBR is not None and phase != COV_PHA_NBR:
                continue
            target_type = str(row.get("TAR_TYP_CD", "") or "")
            target = CoverageTargetInfo(
                COV_PHA_NBR=phase,
                target_type=target_type,
                target_type_desc=translate_coverage_target_type(target_type),
                target_amount=Decimal(str(row.get("TAR_PRM_AMT") or 0)) or None,
                target_date=parse_date(row.get("TAR_DT")),
                raw_data=row,
            )
            targets.append(target)
        return targets

    @property
    def ccv_target(self) -> Optional[Decimal]:
        val = self._policy.data_item_where("LH_COV_TARGET", "TAR_PRM_AMT", "TAR_TYP_CD", "CV")
        return Decimal(str(val)) if val else None

    @property
    def surrender_target(self) -> Optional[Decimal]:
        val = self._policy.data_item_where("LH_COV_TARGET", "TAR_PRM_AMT", "TAR_TYP_CD", "SU")
        return Decimal(str(val)) if val else None
