"""
ABR Quote — Core service to build ABRPolicyData from CyberLife DB2 records.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional, Tuple

from suiteview.polview.models.cl_polrec.policy_translations import BENEFIT_TYPE_CODES
from ...core.policy_service import get_policy_info
from ..models.abr_data import ABRPolicyData, RiderInfo
from ..models.abr_constants import NON_STANDARD_MODE_MAP

logger = logging.getLogger(__name__)

# Billing frequency (months) → ABR billing mode code
_FREQ_TO_MODE = {12: 1, 6: 2, 3: 3, 1: 4}

def build_abr_policy(policy_num: str, region: str) -> Tuple[Optional[ABRPolicyData], Optional[object]]:
    """Fetch policy data from DB2 via the shared PolicyService and assemble an ABRPolicyData object.

    Falls back to a manual entry stub if DB2 is unavailable.
    
    Returns:
        Tuple of (ABRPolicyData, PolicyInformation)
        The PolicyInformation object from DB2 is returned for UI reference if needed.
    """
    
    def _create_manual_policy(pn: str, r: str) -> ABRPolicyData:
        return ABRPolicyData(policy_number=pn, region=r)
        
    try:
        pi = get_policy_info(policy_num, region=region)
        if pi is None:
            logger.info(f"Policy {policy_num} not found, manual entry mode")
            return _create_manual_policy(policy_num, region), None

        # Map billing frequency (months) → ABR mode code
        # Monthly has two modes: 4=Direct Bill (0.0930), 5=PAC/EFT (0.0864)
        # Non-standard modes (NSD_MD_CD) override the standard mapping.
        nsd_code = pi.non_standard_mode_code
        if nsd_code and nsd_code in NON_STANDARD_MODE_MAP:
            billing_mode = NON_STANDARD_MODE_MAP[nsd_code]
        else:
            freq = pi.billing_frequency or 12
            billing_mode = _FREQ_TO_MODE.get(freq, 1)
            if freq == 1 and pi.is_eft:
                billing_mode = 5  # PAC/EFT Monthly

        # Table rating numeric (from substandard ratings on base coverage)
        table_numeric = 0
        flat_extra = 0.0
        flat_to_age = 0
        flat_cease_date = None
        try:
            ratings = pi.get_substandard_ratings(1)
            for r in ratings:
                if r.type_code == "T" and not table_numeric:
                    table_numeric = r.table_rating_numeric or 0
                if r.type_code == "F":
                    flat_extra = float(r.flat_amount or 0)
                    flat_cease_date = r.flat_cease_date
                    if flat_cease_date and pi.issue_date and pi.base_issue_age is not None:
                        flat_to_age = pi.base_issue_age + (
                            flat_cease_date.year - pi.issue_date.year
                        )
        except Exception as e:
            logger.debug(f"Substandard lookup: {e}")

        # Translate DB2 sex code ("1"->"M", "2"->"F", "3"->"U")
        raw_sex = pi.base_sex_code or ""
        sex = {"1": "M", "2": "F", "3": "U"}.get(raw_sex, raw_sex)

        # Rate sex from 67 segment (LH_COV_INS_RNL_RT.RT_SEX_CD)
        raw_rate_sex = pi.renewal_cov_sex_code(1)  # base coverage
        rate_sex = {"1": "M", "2": "F"}.get(raw_rate_sex, raw_rate_sex)
        if not rate_sex:
            rate_sex = sex  # fallback to true sex

        # Maturity age
        maturity = pi.age_at_maturity or 95

        riders = []
        rider_annual = 0.0
        try:
            coverages = pi.get_coverages()
            all_benefits = pi.get_benefits()
            today = date.today()

            def _make_benefit_rider(cov, ben, cov_sex_mapped, cov_rc_str):
                """Create a RiderInfo for a single benefit on a coverage."""
                pc = (cov.plancode or "").upper()
                cov_face = float(cov.face_amount or 0)
                cov_issue_age = int(cov.issue_age or 0)
                cov_table = int(cov.table_rating or 0)
                ben_type = (ben.benefit_type_cd or "").strip()
                ben_sub = (ben.benefit_subtype_cd or "").strip()
                ben_units = float(ben.units or 0)
                ben_vpu = float(ben.vpu or 0)
                ben_face = float(ben.benefit_amount or 0) or cov_face
                ben_issue_age = int(ben.issue_age or cov_issue_age or 0)
                ben_rating = float(ben.rating_factor) if ben.rating_factor else 0.0
                fallback = 0.0
                if ben.coi_rate is not None and ben.units:
                    fallback = float(ben.coi_rate) * float(ben.units)
                    
                return RiderInfo(
                    plancode=pc,
                    face_amount=ben_face,
                    issue_age=ben_issue_age,
                    sex=cov_sex_mapped,
                    rate_class=cov_rc_str,
                    table_rating=cov_table,
                    rider_type="BENEFIT",
                    fallback_premium=fallback,
                    benefit_type=ben_type,
                    benefit_subtype=ben_sub,
                    benefit_units=ben_units,
                    benefit_vpu=ben_vpu,
                    benefit_rating_factor=ben_rating,
                    cease_date=ben.cease_date,
                )

            for cov in coverages:
                pc = (cov.plancode or "").upper()
                cov_sex_mapped = {"1": "M", "2": "F"}.get(
                    cov.sex_code, cov.sex_code or sex
                )
                cov_rc = (cov.rate_class or "0").strip()
                if cov_rc == "0" and cov.is_base:
                    cov_rc = pi.base_rate_class or "N"
                cov_table = int(cov.table_rating or 0)
                cov_issue_age = int(cov.issue_age or 0)
                cov_face = float(cov.face_amount or 0)

                # Base coverage premium is computed directly over its rate schedule
                if not cov.is_base:
                    is_ctr = (cov.person_code == "50")
                    ann = cov.cov_annual_premium
                    if ann is None and cov.premium_rate and cov.units:
                        ann = cov.premium_rate * cov.units
                    fallback = float(ann) if ann else 0.0
                    rider_annual += fallback
                    rtype = "CTR" if is_ctr else "COVERAGE"
                    riders.append(RiderInfo(
                        plancode=pc,
                        face_amount=cov_face,
                        issue_age=cov_issue_age,
                        sex=cov_sex_mapped,
                        rate_class=cov_rc,
                        table_rating=cov_table,
                        rider_type=rtype,
                        fallback_premium=fallback,
                    ))

                cov_benefits = [b for b in all_benefits
                                if b.cov_pha_nbr == cov.cov_pha_nbr]
                for ben in cov_benefits:
                    if ben.cease_date and ben.cease_date < today:
                        continue
                    ben_type = (ben.benefit_type_cd or "").strip()
                    
                    # NOTE: We must skip '#' benefits (ABR) since they have no premium charge.
                    if ben_type == "#":
                        continue
                        
                    riders.append(
                        _make_benefit_rider(cov, ben, cov_sex_mapped, cov_rc)
                    )

        except Exception as e:
            logger.debug(f"Error building rider list: {e}")

        policy = ABRPolicyData(
            policy_number=policy_num,
            region=region,
            insured_name=pi.primary_insured_name or "",
            issue_age=int(pi.base_issue_age or 0),
            attained_age=int(pi.attained_age or 0),
            sex=sex,
            rate_sex=rate_sex,
            rate_class=pi.base_rate_class or "N",
            face_amount=float(pi.base_face_amount or 0),
            issue_date=(
                pi.issue_date
                or (pi.get_coverages()[0].issue_date if pi.get_coverages() else None)
            ),
            maturity_age=maturity,
            issue_state=pi.issue_state or pi.issue_state_code or "",
            plan_code=pi.base_plancode or "",
            base_plancode=str(pi.data_item("LH_COV_PHA", "PLN_BSE_SRE_CD") or "").strip(),
            billing_mode=billing_mode,
            policy_month=pi.policy_month or 1,
            policy_year=pi.policy_year or 1,
            table_rating=table_numeric,
            flat_extra=flat_extra,
            flat_to_age=flat_to_age,
            flat_cease_date=flat_cease_date,
            paid_to_date=pi.paid_to_date,
            modal_premium=float(pi.modal_premium or 0),
            annual_premium=float(pi.annual_premium or 0),
            rider_annual_premium=rider_annual,
            riders=riders,
        )
        return policy, pi

    except Exception as e:
        logger.error(f"DB2 fetch error: {e}")
        return _create_manual_policy(policy_num, region), None
