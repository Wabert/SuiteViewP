from __future__ import annotations

from datetime import date
from typing import Optional

from suiteview.core.policy_service import get_policy_info
from suiteview.core.rates import Rates
from suiteview.illustration.models.policy_data import (
    BenefitInfo as IllBenefitInfo,
    CoverageSegment,
    IllustrationPolicyData,
)


def build_illustration_data(
    policy_number: str,
    region: str = "CKPR",
    company_code: Optional[str] = None,
) -> IllustrationPolicyData:
    """Load policy data from DB2 and return a ready-to-project IllustrationPolicyData.

    Uses the shared PolicyInformation class to fetch all tables from DB2,
    then maps fields into the illustration data model.

    Raises:
        ValueError: If policy not found in DB2.
    """
    pi = get_policy_info(policy_number, region, company_code)
    if pi is None or not pi.exists:
        raise ValueError(f"Policy {policy_number} not found in region {region}")

    rates_db = Rates()

    # ── Basic identity / plan ─────────────────────────────────
    plancode = pi.base_plancode or ""
    issue_date = pi.issue_date
    issue_age = pi.base_issue_age or 0

    # ── Demographics ──────────────────────────────────────────
    rate_sex = _translate_sex(pi.base_sex_code)
    rate_class = getattr(pi, "base_rate_class", "") or ""

    # ── Face / DB ─────────────────────────────────────────────
    face_raw = pi.base_total_face_amount
    face_amount = float(face_raw) if face_raw else 0.0
    units = face_amount / 1000.0 if face_amount else 0.0
    db_option = _translate_dbo(pi.db_option_code or "")
    band = rates_db.get_band(plancode, face_amount) or 1

    # ── Account value ─────────────────────────────────────────
    av_raw = pi.mv_av(0)
    account_value = float(av_raw) if av_raw is not None else 0.0

    # ── Premium ───────────────────────────────────────────────
    modal_raw = pi.modal_premium
    modal_premium = float(modal_raw) if modal_raw is not None else 0.0
    billing_frequency = pi.billing_frequency or 1
    if billing_frequency <= 0:
        billing_frequency = 1
    annual_premium = modal_premium * (12.0 / billing_frequency)

    # ── Duration / timing ─────────────────────────────────────
    policy_year = pi.policy_year or 1
    policy_month = pi.policy_month or 1
    duration = (policy_year - 1) * 12 + policy_month
    att_age_raw = pi.attained_age
    attained_age = att_age_raw if att_age_raw is not None else (issue_age + policy_year - 1)
    valuation_date = pi.valuation_date

    # ── Interest ──────────────────────────────────────────────
    guar_raw = pi.guaranteed_interest_rate
    guaranteed_rate = float(guar_raw) / 100.0 if guar_raw is not None else 0.0
    current_rate = guaranteed_rate  # default to guar; override via what-if or plancode config

    # ── 7702 / Guideline ──────────────────────────────────────
    doli_code = str(pi.def_of_life_ins_code or "")
    def_of_life_ins = _translate_doli(doli_code)

    glp_raw = pi.glp
    glp = float(glp_raw) if glp_raw is not None else 0.0
    gsp_raw = pi.gsp
    gsp = float(gsp_raw) if gsp_raw is not None else 0.0
    corr_raw = pi.corridor_percent
    corridor_pct = float(corr_raw) if corr_raw is not None else 100.0

    # ── Targets ───────────────────────────────────────────────
    mtp_raw = pi.mtp
    mtp = float(mtp_raw) if mtp_raw is not None else 0.0
    ctp_raw = pi.ctp
    ctp = float(ctp_raw) if ctp_raw is not None else 0.0
    accum_mtp_raw = pi.accumulated_mtp_target
    accumulated_mtp = float(accum_mtp_raw) if accum_mtp_raw is not None else 0.0
    map_cease_date = getattr(pi, "map_date", None)

    # ── Premiums paid ─────────────────────────────────────────
    paid_raw = pi.total_premiums_paid
    premiums_paid = float(paid_raw) if paid_raw is not None else 0.0
    ytd_raw = pi.premium_ytd
    premiums_ytd = float(ytd_raw) if ytd_raw is not None else 0.0
    cost_basis_raw = pi.cost_basis
    cost_basis = float(cost_basis_raw) if cost_basis_raw is not None else 0.0

    # ── Loans ─────────────────────────────────────────────────
    # NOTE: DB2 regular loan values mapped to preferred for testing
    reg_loan_prin = 0.0
    reg_loan_acc = 0.0
    pref_loan_prin = float(pi.total_regular_loan_principal or 0)
    pref_loan_acc = float(pi.total_regular_loan_accrued or 0)
    var_loan_prin = float(pi.total_variable_loan_principal or 0)
    var_loan_acc = float(pi.total_variable_loan_accrued or 0)

    # ── Withdrawals ───────────────────────────────────────────
    withdrawals = float(pi.total_withdrawals or 0)

    # ── Shadow ────────────────────────────────────────────────
    gav_raw = pi.gav
    shadow_av = float(gav_raw) if gav_raw is not None else 0.0

    # ── MEC / TAMRA ───────────────────────────────────────────
    is_mec = pi.is_mec

    # ── Build coverage segments ───────────────────────────────
    segments = []
    try:
        base_covs = pi.get_base_coverages()
    except Exception:
        base_covs = []

    for cov in base_covs:
        seg_face = float(cov.face_amount) if cov.face_amount else 0.0
        seg_orig_face = float(cov.orig_amount) if cov.orig_amount else seg_face
        seg_units = float(cov.units) if cov.units else seg_face / 1000.0
        seg_band = rates_db.get_band(plancode, seg_face) or 1

        # Get rate sex from coverage record
        try:
            seg_rate_sex = _translate_sex(cov.sex_code)
        except Exception:
            seg_rate_sex = rate_sex

        seg_rate_class = cov.rate_class or rate_class
        seg_table = cov.table_rating if cov.table_rating is not None else 0
        seg_flat = float(cov.flat_extra) if cov.flat_extra else 0.0
        seg_flat_cease = cov.flat_cease_date

        segments.append(CoverageSegment(
            coverage_phase=cov.cov_pha_nbr,
            is_base=True,
            issue_date=cov.issue_date,
            issue_age=cov.issue_age or issue_age,
            rate_sex=seg_rate_sex,
            rate_class=seg_rate_class,
            face_amount=seg_face,
            original_face_amount=seg_orig_face,
            units=seg_units,
            vpu=float(cov.vpu) if cov.vpu else 1000.0,
            band=seg_band,
            original_band=seg_band,
            table_rating=seg_table,
            flat_extra=seg_flat,
            flat_cease_date=seg_flat_cease,
            status=cov.cov_status or "A",
            maturity_date=cov.maturity_date,
            coi_renewal_rate=float(cov.coi_rate) if cov.coi_rate else None,
        ))

    # ── Build benefits list ───────────────────────────────────
    benefits = []
    try:
        raw_benefits = pi.get_benefits()
    except Exception:
        raw_benefits = []

    today = date.today()
    for b in raw_benefits:
        if b.cease_date and b.cease_date < today:
            continue
        benefits.append(IllBenefitInfo(
            coverage_phase=b.cov_pha_nbr,
            benefit_type=b.benefit_type_cd or "",
            benefit_subtype=b.benefit_subtype_cd or "",
            benefit_amount=float(b.benefit_amount) if b.benefit_amount else 0.0,
            units=float(b.units) if b.units else 0.0,
            vpu=float(b.vpu) if b.vpu else 0.0,
            issue_date=b.issue_date,
            issue_age=b.issue_age or 0,
            cease_date=b.cease_date,
            rating_factor=float(b.rating_factor) if b.rating_factor else 0.0,
            coi_rate=float(b.coi_rate) if b.coi_rate else None,
            is_active=True,
        ))

    # ── CCV / Shadow Account detection ───────────────────────
    ccv_active = False
    ccv_units = 0.0
    ccv_coi_rate: Optional[float] = None
    for ben in benefits:
        if ben.benefit_type == "A" and ben.is_active:
            ccv_active = True
            ccv_units = ben.units
            ccv_coi_rate = ben.coi_rate
            break

    # ── Assemble ──────────────────────────────────────────────
    return IllustrationPolicyData(
        policy_number=policy_number.strip(),
        region=region,
        company_code=pi.company_code or "",
        insured_name=pi.primary_insured_name or "",
        plancode=plancode,
        product_type=pi.product_type or "",
        form_number="",  # TODO: map from coverage form_number
        issue_state=pi.issue_state or "",
        company_sub=pi.company_name or "",
        issue_date=issue_date,
        issue_age=issue_age,
        attained_age=attained_age,
        rate_sex=rate_sex,
        rate_class=rate_class,
        face_amount=face_amount,
        units=units,
        db_option=db_option,
        band=band,
        account_value=account_value,
        cost_basis=cost_basis,
        modal_premium=modal_premium,
        annual_premium=annual_premium,
        billing_frequency=billing_frequency,
        premiums_paid_to_date=premiums_paid,
        premiums_ytd=premiums_ytd,
        guaranteed_interest_rate=guaranteed_rate,
        current_interest_rate=current_rate,
        policy_year=policy_year,
        policy_month=policy_month,
        duration=duration,
        valuation_date=valuation_date,
        maturity_age=121,
        def_of_life_ins=def_of_life_ins,
        glp=glp,
        gsp=gsp,
        corridor_percent=corridor_pct,
        mtp=mtp,
        accumulated_mtp=accumulated_mtp,
        map_cease_date=map_cease_date,
        ctp=ctp,
        is_mec=is_mec,
        regular_loan_principal=reg_loan_prin,
        regular_loan_accrued=reg_loan_acc,
        preferred_loan_principal=pref_loan_prin,
        preferred_loan_accrued=pref_loan_acc,
        variable_loan_principal=var_loan_prin,
        variable_loan_accrued=var_loan_acc,
        withdrawals_to_date=withdrawals,
        shadow_account_value=shadow_av,
        ccv_active=ccv_active,
        ccv_units=ccv_units,
        ccv_coi_rate=ccv_coi_rate,
        segments=segments,
        benefits=benefits,
    )


# ── Private helpers ───────────────────────────────────────────


def _translate_sex(code: str) -> str:
    """Translate sex code from DB2/PI to rate sex."""
    code = (code or "").strip().upper()
    if code in ("M", "1"):
        return "M"
    if code in ("F", "2"):
        return "F"
    if code in ("U", "0"):
        return "U"
    return code


def _translate_dbo(code: str) -> str:
    """Translate death benefit option code."""
    code = (code or "").strip()
    mapping = {"1": "A", "2": "B", "3": "C", "A": "A", "B": "B", "C": "C"}
    return mapping.get(code, "A")


def _translate_doli(code: str) -> str:
    """Translate def_of_life_ins_code: 1/2/4 -> GPT, 3/5 -> CVAT."""
    code = (code or "").strip()
    if code in ("1", "2", "4"):
        return "GPT"
    if code in ("3", "5"):
        return "CVAT"
    return "GPT"
