from __future__ import annotations

from datetime import date
from typing import Optional

from suiteview.core.policy_service import get_policy_info
from suiteview.core.rates import Rates
from suiteview.illustration.models.policy_data import (
    BenefitInfo as IllBenefitInfo,
    CoverageSegment,
    IllustrationPolicyData,
    RiderInfo,
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
    raw_band = rates_db.get_band(plancode, face_amount)
    band = raw_band if raw_band is not None else 1

    # ── Account value ─────────────────────────────────────────
    av_raw = pi.mv_av(0)
    account_value = float(av_raw) if av_raw is not None else 0.0
    system_coi_charge = float(pi.mv_coi_charge(0) or 0)
    system_expense_charge = float(pi.mv_expense_charge(0) or 0)
    system_other_charge = float(pi.mv_other_charge(0) or 0)
    system_monthly_deduction = float(pi.mv_monthly_deduction(0) or 0)

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
    valuation_date = pi.valuation_date
    if issue_date and valuation_date:
        months_since_issue = _completed_months(issue_date, valuation_date)
        policy_month = (months_since_issue % 12) + 1
    duration = (policy_year - 1) * 12 + policy_month
    att_age_raw = pi.attained_age
    attained_age = att_age_raw if att_age_raw is not None else (issue_age + policy_year - 1)

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
    accum_glp_raw = pi.accumulated_glp_target
    accumulated_glp = float(accum_glp_raw) if accum_glp_raw is not None else 0.0
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
    paid_raw = pi.premium_td
    premiums_paid = float(paid_raw) if paid_raw is not None else 0.0
    ytd_raw = pi.premium_ytd
    premiums_ytd = float(ytd_raw) if ytd_raw is not None else 0.0
    cost_basis_raw = pi.cost_basis
    cost_basis = float(cost_basis_raw) if cost_basis_raw is not None else 0.0

    # ── Loans ─────────────────────────────────────────────────
    reg_loan_prin = float(pi.total_regular_loan_principal or 0)
    reg_loan_acc = float(pi.total_regular_loan_accrued or 0)
    pref_loan_prin = float(pi.total_preferred_loan_principal or 0)
    pref_loan_acc = float(pi.total_preferred_loan_accrued or 0)
    var_loan_prin = float(pi.total_variable_loan_principal or 0)
    var_loan_acc = float(pi.total_variable_loan_accrued or 0)
    var_loan_rate_raw = getattr(pi, "variable_loan_charge_rate", None)
    var_loan_charge_rate = float(var_loan_rate_raw) if var_loan_rate_raw is not None else None

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

    substandard_by_phase = {}
    try:
        for rating in pi.get_substandard_ratings():
            substandard_by_phase.setdefault(rating.coverage_phase, []).append(rating)
    except Exception:
        substandard_by_phase = {}

    for cov in base_covs:
        seg_face = float(cov.face_amount) if cov.face_amount else 0.0
        seg_orig_face = float(cov.orig_amount) if cov.orig_amount else seg_face
        seg_units = float(cov.units) if cov.units else seg_face / 1000.0
        try:
            raw_seg_band = pi.cov_band(cov.cov_pha_nbr)
        except Exception:
            raw_seg_band = rates_db.get_band(plancode, face_amount)
        seg_band = raw_seg_band if raw_seg_band is not None else 1

        # Get rate sex from coverage record
        try:
            seg_rate_sex = _translate_sex(cov.sex_code)
        except Exception:
            seg_rate_sex = rate_sex

        seg_rate_class = cov.rate_class or rate_class
        seg_table = cov.table_rating if cov.table_rating is not None else 0
        seg_table_cease = None
        seg_flat = float(cov.flat_extra) if cov.flat_extra else 0.0
        seg_flat_cease = cov.flat_cease_date
        for rating in substandard_by_phase.get(cov.cov_pha_nbr, []):
            if rating.type_code == "T" and rating.table_rating_numeric and rating.table_rating_numeric > 0:
                seg_table = rating.table_rating_numeric
                seg_table_cease = rating.flat_cease_date
            elif rating.type_code == "F":
                if rating.flat_amount:
                    seg_flat = float(rating.flat_amount)
                seg_flat_cease = rating.flat_cease_date

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
            table_cease_date=seg_table_cease,
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

    as_of_date = valuation_date or date.today()
    for b in raw_benefits:
        if b.cease_date and b.cease_date < as_of_date:
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

    # ── Build rider list ──────────────────────────────────────
    riders = []
    rider_counts = {}
    try:
        raw_riders = pi.get_riders()
    except Exception:
        raw_riders = []

    for rider in raw_riders:
        rider_plancode = rider.plancode or ""
        if not rider_plancode or rider_plancode == plancode:
            continue
        if _coverage_is_terminated(rider, as_of_date):
            continue
        rider_counts[rider_plancode] = rider_counts.get(rider_plancode, 0) + 1
        rider_face = float(rider.face_amount) if rider.face_amount else 0.0
        rider_units = float(rider.units) if rider.units else rider_face / 1000.0
        raw_rider_band = rates_db.get_band(rider_plancode, rider_face)
        rider_band = raw_rider_band if raw_rider_band is not None else 1
        riders.append(RiderInfo(
            coverage_phase=rider.cov_pha_nbr,
            occurrence=rider_counts[rider_plancode],
            plancode=rider_plancode,
            issue_date=rider.issue_date,
            issue_age=rider.issue_age or 0,
            rate_sex=rider.sex_code or "",
            rate_class=rider.rate_class or "",
            face_amount=rider_face,
            units=rider_units,
            vpu=float(rider.vpu) if rider.vpu else 1000.0,
            band=int(rider_band),
            table_rating=rider.table_rating or 0,
            flat_extra=float(rider.flat_extra) if rider.flat_extra else 0.0,
            maturity_date=rider.maturity_date,
            status=rider.cov_status or "",
            premium_rate=float(rider.premium_rate) if rider.premium_rate else None,
            coi_rate=float(rider.coi_rate) if rider.coi_rate else None,
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
        system_coi_charge=system_coi_charge,
        system_expense_charge=system_expense_charge,
        system_other_charge=system_other_charge,
        system_monthly_deduction=system_monthly_deduction,
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
        accumulated_glp=accumulated_glp,
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
        preferred_loans_available=bool(pi.preferred_loans_available),
        variable_loan_principal=var_loan_prin,
        variable_loan_accrued=var_loan_acc,
        variable_loan_charge_rate=var_loan_charge_rate,
        withdrawals_to_date=withdrawals,
        shadow_account_value=shadow_av,
        ccv_active=ccv_active,
        ccv_units=ccv_units,
        ccv_coi_rate=ccv_coi_rate,
        segments=segments,
        benefits=benefits,
        riders=riders,
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


def _completed_months(start: date, end: date) -> int:
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(months, 0)


def _coverage_is_terminated(coverage, as_of_date: date) -> bool:
    status = str(
        getattr(coverage, "nxt_chg_typ_cd", "")
        or getattr(coverage, "cov_status", "")
        or ""
    ).strip()
    cease_date = getattr(coverage, "nxt_chg_dt", None)
    terminate_date = getattr(coverage, "terminate_date", None)

    if terminate_date and terminate_date <= as_of_date:
        return True
    if status == "0":
        return cease_date is None or cease_date <= as_of_date
    return False


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
