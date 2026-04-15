"""Shadow Account (CCV) calculation — parallel mini-engine.

Follows RERUN CalcEngine cols WP–XX (614–648).

The shadow account tracks a hypothetical AV using its own rates,
used to determine the Cash Continuation Value (CCV) benefit.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from suiteview.illustration.core.rate_loader import IllustrationRates, get_rate
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData


def _round_near(value: float, decimals: int = 2) -> float:
    d = Decimal(str(value))
    return float(d.quantize(Decimal(10) ** -decimals, rounding=ROUND_HALF_UP))


@dataclass
class ShadowResult:
    """Output of one month of shadow account calculation."""

    shadow_bav: float = 0.0
    shadow_wd_charges: float = 0.0
    shadow_sa: float = 0.0
    shadow_target_prem: float = 0.0
    shadow_prem_under_target: float = 0.0
    shadow_prem_over_target: float = 0.0
    shadow_target_load: float = 0.0
    shadow_excess_load: float = 0.0
    shadow_prem_load: float = 0.0
    shadow_net_prem: float = 0.0
    shadow_nar_av: float = 0.0
    shadow_db: float = 0.0
    shadow_coi_rate: float = 0.0
    shadow_coi: float = 0.0
    shadow_dbd_rate: float = 0.0
    shadow_nar: float = 0.0
    shadow_epu_rate: float = 0.0
    shadow_epu: float = 0.0
    shadow_mfee: float = 0.0
    shadow_rider_charges: float = 0.0
    shadow_md: float = 0.0
    shadow_av: float = 0.0
    shadow_days: int = 0
    shadow_int_rate: float = 0.0
    shadow_eff_rate: float = 0.0
    shadow_interest: float = 0.0
    shadow_eav: float = 0.0
    shadow_eav_less_debt: float = 0.0


def calculate_shadow(
    prev_shadow_eav: float,
    gross_premium: float,
    premiums_ytd: float,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    rate_year: int,
    attained_age: int,
    days_in_month: int,
    policy_debt: float,
    is_inforce: bool = False,
) -> ShadowResult:
    """Calculate one month of the shadow account.

    Args:
        prev_shadow_eav: Previous month's shadow EAV (0 for first month).
        gross_premium: Applied total premium this month (same as regular side).
        premiums_ytd: Year-to-date premiums AFTER this month's premium.
        policy: Policy data (for face, DBO, flags, substandard info).
        config: Plancode configuration (shadow rates/codes).
        rates: Pre-loaded rate arrays (includes shadow_coi).
        rate_year: Current policy year for rate lookups.
        attained_age: Current attained age.
        days_in_month: Days in this month (from interest calc).
        policy_debt: Total loan debt (for EAV-less-debt).
        is_inforce: True for the inforce snapshot month.

    Returns:
        ShadowResult with all shadow fields populated.
    """
    if not policy.has_shadow_account:
        return ShadowResult()

    seg = policy.base_segment

    # ── BAV (col WP) ─────────────────────────────────────────
    # Inforce row: 0 (prev_shadow_eav will be 0 from MonthlyState default)
    shadow_bav = prev_shadow_eav

    # ── WD/Charges (col WQ) ──────────────────────────────────
    # Force-outs and policy change AV reductions — 0 for basic illustration
    shadow_wd_charges = 0.0

    # ── Shadow SA (col WR) ───────────────────────────────────
    shadow_sa = policy.face_amount  # vCurrentSA

    # ── SA for rate basis ─────────────────────────────────────
    # sShadow_SA_Basis: 1 = OriginalSA, 2 = CurrentSA
    if config.shadow_sa_basis == 1:
        sa_for_basis = seg.original_face_amount if seg else policy.face_amount
    else:
        sa_for_basis = policy.face_amount

    # ── Shadow Target Premium (col WU) ───────────────────────
    # shadow_tp = ROUND(sa_basis/1000 * (TPR + TPRTBL1*table + flat1 + flat2), 2) + CTR_CTP + PWSTP_CTP
    # For EXECUL: shadow_target = "0" → TPR=0, TPRTBL1=0, so shadow_tp = 0
    if config.shadow_target == "Table":
        tpr = get_rate(rates, "shadow_tpr", rate_year)
        tpr_tbl1 = get_rate(rates, "shadow_tpr_tbl1", rate_year)
        table_cov1 = seg.table_rating if seg else 0
        flat1 = (seg.flat_extra / 12.0) if seg and seg.flat_extra else 0.0
        flat2 = 0.0  # Second flat extra — not implemented
        shadow_target_prem = _round_near(
            sa_for_basis / 1000.0 * (tpr + tpr_tbl1 * table_cov1 + flat1 + flat2), 2
        )
    else:
        shadow_target_prem = 0.0

    # ── Premium split under/over target (cols WX/WY) ─────────
    applied_prem = gross_premium
    prem_ytd_before = premiums_ytd - applied_prem  # YTD before this premium

    prem_under = max(min(shadow_target_prem - prem_ytd_before, applied_prem), 0.0)
    prem_over = min(applied_prem, premiums_ytd - shadow_target_prem) if premiums_ytd > shadow_target_prem else 0.0
    prem_over = max(prem_over, 0.0)

    # ── Premium load rates (cols WZ/XA) ──────────────────────
    if config.shadow_prem_load_code == "Table":
        tpp_pct = get_rate(rates, "shadow_tpp", rate_year)
        epp_pct = get_rate(rates, "shadow_epp", rate_year)
    else:
        flat_pct = float(config.shadow_prem_load_code)
        tpp_pct = flat_pct
        epp_pct = flat_pct

    # ── Premium loads (cols XB/XC/XD) ─────────────────────────
    target_load = prem_under * tpp_pct
    excess_load = prem_over * epp_pct
    shadow_prem_load = target_load + excess_load

    # ── Net premium (col XE) ─────────────────────────────────
    shadow_net_prem = applied_prem - shadow_prem_load

    # ── Shadow NAR_AV (col XF) ───────────────────────────────
    # NOT floored at 0 (per RERUN note)
    shadow_nar_av = shadow_bav - shadow_wd_charges + shadow_net_prem

    # ── Shadow DB (col XG) ───────────────────────────────────
    if policy.db_option == "B":
        shadow_db = shadow_nar_av + shadow_sa
    else:
        shadow_db = shadow_sa

    # ── Shadow COI rate (col XH/XI) ──────────────────────────
    shadow_coi_rate_raw = get_rate(rates, "shadow_coi", rate_year)

    # Substandard adjustment: rate * (1 + table_factor * table) + flat extras
    table_cov1 = seg.table_rating if seg else 0
    table_factor = config.table_rating_factor
    base_flat1 = (seg.flat_extra / 12.0) if seg and seg.flat_extra else 0.0
    base_flat1 = float(Decimal(str(base_flat1)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    base_flat2 = 0.0  # Second flat extra — not yet implemented

    shadow_coi_rate = (
        shadow_coi_rate_raw * (1.0 + table_factor * table_cov1)
        + base_flat1
        + base_flat2
    )

    # ── Shadow DBD rate (col XJ) ─────────────────────────────
    if config.shadow_dbd_rate == "Table":
        shadow_dbd_rate = get_rate(rates, "shadow_dbd", rate_year)
    else:
        shadow_dbd_rate = float(config.shadow_dbd_rate)

    # ── Shadow NAR (col XK) ──────────────────────────────────
    # NAR = DB / (1 + dbd_rate)^(1/12) - NAR_AV
    shadow_nar = shadow_db / (1.0 + shadow_dbd_rate) ** (1.0 / 12.0) - shadow_nar_av

    # ── Shadow COI (col XL) ──────────────────────────────────
    shadow_coi = _round_near(shadow_nar / 1000.0 * shadow_coi_rate, 2)

    # ── Shadow EPU (cols XM/XN) ──────────────────────────────
    if config.shadow_epu_code == "Table":
        shadow_epu_rate = get_rate(rates, "shadow_epu", rate_year)
    else:
        shadow_epu_rate = float(config.shadow_epu_code)

    shadow_epu = shadow_epu_rate * sa_for_basis / 1000.0

    # ── Shadow MFEE (col XO) ─────────────────────────────────
    shadow_mfee = config.shadow_mfee

    # ── Rider charges (col XP) ───────────────────────────────
    # vRiderBenefitCharge - CCV_charge (all rider charges except CCV)
    # Not yet implemented — 0 for now
    shadow_rider_charges = 0.0

    # ── Shadow MD (col XQ) ───────────────────────────────────
    shadow_md = shadow_coi + shadow_epu + shadow_mfee + shadow_rider_charges

    # ── Shadow AV (col XR) ───────────────────────────────────
    if is_inforce:
        shadow_av = policy.shadow_account_value
    else:
        shadow_av = shadow_nar_av - shadow_md

    # ── Interest (cols XS-XV) ─────────────────────────────────
    shadow_days = days_in_month

    if config.shadow_int_rate_code == "Table":
        shadow_int_rate = get_rate(rates, "shadow_int", rate_year)
    else:
        shadow_int_rate = float(config.shadow_int_rate_code)

    shadow_eff_rate = (1.0 + shadow_int_rate) ** (shadow_days / 365.0) - 1.0
    shadow_interest = max(0.0, shadow_eff_rate * shadow_av)

    # ── Shadow EAV (col XW) ──────────────────────────────────
    # Active only if CCV benefit active (or inherent), and age <= cease_age - 1
    if attained_age > (config.shadow_cease_age - 1):
        shadow_eav = 0.0
    else:
        shadow_eav = _round_near(shadow_av + shadow_interest, 2)

    # ── Shadow EAV less debt (col XX) ─────────────────────────
    if config.shadow_loan_impact == "Reduce":
        shadow_eav_less_debt = shadow_eav - policy_debt
    else:
        shadow_eav_less_debt = shadow_eav

    return ShadowResult(
        shadow_bav=shadow_bav,
        shadow_wd_charges=shadow_wd_charges,
        shadow_sa=shadow_sa,
        shadow_target_prem=shadow_target_prem,
        shadow_prem_under_target=prem_under,
        shadow_prem_over_target=prem_over,
        shadow_target_load=target_load,
        shadow_excess_load=excess_load,
        shadow_prem_load=shadow_prem_load,
        shadow_net_prem=shadow_net_prem,
        shadow_nar_av=shadow_nar_av,
        shadow_db=shadow_db,
        shadow_coi_rate=shadow_coi_rate,
        shadow_coi=shadow_coi,
        shadow_dbd_rate=shadow_dbd_rate,
        shadow_nar=shadow_nar,
        shadow_epu_rate=shadow_epu_rate,
        shadow_epu=shadow_epu,
        shadow_mfee=shadow_mfee,
        shadow_rider_charges=shadow_rider_charges,
        shadow_md=shadow_md,
        shadow_av=shadow_av,
        shadow_days=shadow_days,
        shadow_int_rate=shadow_int_rate,
        shadow_eff_rate=shadow_eff_rate,
        shadow_interest=shadow_interest,
        shadow_eav=shadow_eav,
        shadow_eav_less_debt=shadow_eav_less_debt,
    )
