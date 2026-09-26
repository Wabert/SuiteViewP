"""Shadow Account (CCV) calculation — parallel mini-engine.

Follows RERUN CalcEngine cols WP–XX (614–648).

The shadow account tracks a hypothetical AV using its own rates,
used to determine the Cash Continuation Value (CCV) benefit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from suiteview.illustration.constants import (
    DAYS_PER_YEAR,
    DB_OPTION_INCREASING,
    MONTHS_PER_YEAR,
    PER_THOUSAND,
    RATE_CODE_TABLE,
)
from suiteview.illustration.core.monthly_deduction import _charge_active
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
    shadow_days: float = 0.0
    shadow_int_rate: float = 0.0
    shadow_eff_rate: float = 0.0
    shadow_interest: float = 0.0
    shadow_eav: float = 0.0
    shadow_eav_less_debt: float = 0.0


@dataclass(frozen=True)
class ShadowInput:
    """Inputs for one CCV shadow-account month.

    Premium and YTD amounts are dollars after the regular-side premium step.
    ``days_in_month`` is actual calendar days; ``display_days_in_month`` carries
    the option-aware 365/12 vs exact-days count used for interest display.
    """

    prev_shadow_eav: float
    gross_premium: float
    premiums_ytd: float
    policy: IllustrationPolicyData
    config: PlancodeConfig
    rates: IllustrationRates
    rate_year: int
    attained_age: int
    days_in_month: int
    policy_debt: float
    is_inforce: bool = False
    shadow_rider_charges: float = 0.0
    projection_date: date | None = None
    display_days_in_month: float | None = None


def _sa_for_shadow_basis(policy: IllustrationPolicyData, config: PlancodeConfig) -> float:
    seg = policy.base_segment
    if config.shadow_sa_basis == 1:
        return seg.original_face_amount if seg else policy.face_amount
    return policy.face_amount


def _shadow_target_premium(
    *,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    rate_year: int,
    sa_for_basis: float,
) -> float:
    if config.shadow_target != RATE_CODE_TABLE:
        return 0.0
    seg = policy.base_segment
    tpr = get_rate(rates, "shadow_tpr", rate_year)
    tpr_tbl1 = get_rate(rates, "shadow_tpr_tbl1", rate_year)
    table_cov1 = seg.table_rating if seg else 0
    flat1 = (seg.flat_extra / MONTHS_PER_YEAR) if seg and seg.flat_extra else 0.0
    flat2 = 0.0  # Second flat extra — not implemented
    return _round_near(
        sa_for_basis / PER_THOUSAND * (tpr + tpr_tbl1 * table_cov1 + flat1 + flat2),
        2,
    )


def _premium_split(
    *,
    gross_premium: float,
    premiums_ytd: float,
    shadow_target_prem: float,
) -> tuple[float, float]:
    applied_prem = gross_premium
    prem_ytd_before = premiums_ytd - applied_prem
    prem_under = max(min(shadow_target_prem - prem_ytd_before, applied_prem), 0.0)
    prem_over = (
        min(applied_prem, premiums_ytd - shadow_target_prem)
        if premiums_ytd > shadow_target_prem else 0.0
    )
    return prem_under, max(prem_over, 0.0)


def _shadow_premium_load_rates(
    config: PlancodeConfig,
    rates: IllustrationRates,
    rate_year: int,
) -> tuple[float, float]:
    if config.shadow_prem_load_code == RATE_CODE_TABLE:
        return (
            get_rate(rates, "shadow_tpp", rate_year),
            get_rate(rates, "shadow_epp", rate_year),
        )
    flat_pct = float(config.shadow_prem_load_code)
    return flat_pct, flat_pct


def _configured_rate(
    configured,
    rates: IllustrationRates,
    rate_key: str,
    rate_year: int,
) -> float:
    return get_rate(rates, rate_key, rate_year) if configured == RATE_CODE_TABLE else float(configured)


def _shadow_death_benefit(
    policy: IllustrationPolicyData,
    shadow_nar_av: float,
    shadow_sa: float,
) -> float:
    if policy.db_option == DB_OPTION_INCREASING:
        return shadow_nar_av + shadow_sa
    return shadow_sa


def _active_table_rating(seg, projection_date: date | None) -> int:
    if not seg or seg.table_rating <= 0:
        return 0
    return seg.table_rating if _charge_active(seg.table_cease_date, projection_date) else 0


def _active_flat_extra(seg, projection_date: date | None) -> float:
    if not seg or not seg.flat_extra or seg.flat_extra <= 0:
        return 0.0
    if not _charge_active(seg.flat_cease_date, projection_date):
        return 0.0
    monthly_flat = seg.flat_extra / MONTHS_PER_YEAR
    return float(Decimal(str(monthly_flat)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    ))


def _shadow_coi_rate(
    *,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    rate_year: int,
    projection_date: date | None,
) -> float:
    seg = policy.base_segment
    shadow_coi_rate_raw = get_rate(rates, "shadow_coi", rate_year)
    table_cov1 = _active_table_rating(seg, projection_date)
    base_flat1 = _active_flat_extra(seg, projection_date)
    base_flat2 = 0.0  # Second flat extra — not yet implemented
    return (
        shadow_coi_rate_raw * (1.0 + config.table_rating_factor * table_cov1)
        + base_flat1
        + base_flat2
    )


def _shadow_interest_values(
    *,
    config: PlancodeConfig,
    rates: IllustrationRates,
    rate_year: int,
    shadow_av: float,
    days_in_month: int,
    display_days_in_month: float | None,
) -> tuple[float, float, float, float]:
    shadow_days = (
        float(display_days_in_month)
        if display_days_in_month is not None else float(days_in_month)
    )
    shadow_int_rate = _configured_rate(
        config.shadow_int_rate_code,
        rates,
        "shadow_int",
        rate_year,
    )
    shadow_eff_rate = (1.0 + shadow_int_rate) ** (shadow_days / DAYS_PER_YEAR) - 1.0
    shadow_interest = max(0.0, shadow_eff_rate * shadow_av)
    return shadow_days, shadow_int_rate, shadow_eff_rate, shadow_interest


def _shadow_eav(
    *,
    config: PlancodeConfig,
    attained_age: int,
    shadow_av: float,
    shadow_interest: float,
) -> float:
    if attained_age > (config.shadow_cease_age - 1):
        return 0.0
    return _round_near(shadow_av + shadow_interest, 2)


def _shadow_eav_less_debt(
    config: PlancodeConfig,
    shadow_eav: float,
    policy_debt: float,
) -> float:
    if config.shadow_loan_impact == "Reduce":
        return shadow_eav - policy_debt
    return shadow_eav


_SHADOW_RESULT_SOURCES = {
    "shadow_bav": "shadow_bav",
    "shadow_wd_charges": "shadow_wd_charges",
    "shadow_sa": "shadow_sa",
    "shadow_target_prem": "shadow_target_prem",
    "shadow_prem_under_target": "prem_under",
    "shadow_prem_over_target": "prem_over",
    "shadow_target_load": "target_load",
    "shadow_excess_load": "excess_load",
    "shadow_prem_load": "shadow_prem_load",
    "shadow_net_prem": "shadow_net_prem",
    "shadow_nar_av": "shadow_nar_av",
    "shadow_db": "shadow_db",
    "shadow_coi_rate": "shadow_coi_rate",
    "shadow_coi": "shadow_coi",
    "shadow_dbd_rate": "shadow_dbd_rate",
    "shadow_nar": "shadow_nar",
    "shadow_epu_rate": "shadow_epu_rate",
    "shadow_epu": "shadow_epu",
    "shadow_mfee": "shadow_mfee",
    "shadow_rider_charges": "shadow_rider_charges",
    "shadow_md": "shadow_md",
    "shadow_av": "shadow_av",
    "shadow_days": "shadow_days",
    "shadow_int_rate": "shadow_int_rate",
    "shadow_eff_rate": "shadow_eff_rate",
    "shadow_interest": "shadow_interest",
    "shadow_eav": "shadow_eav",
    "shadow_eav_less_debt": "shadow_eav_less_debt",
}


def _build_shadow_result(values: dict) -> ShadowResult:
    return ShadowResult(**{
        field: values[source]
        for field, source in _SHADOW_RESULT_SOURCES.items()
    })


def calculate_shadow(inputs: ShadowInput) -> ShadowResult:
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
        days_in_month: Actual calendar days in this month for shadow interest.
        policy_debt: Total loan debt (for EAV-less-debt).
        is_inforce: True for the inforce snapshot month.
        shadow_rider_charges: Regular-side rider and benefit charges, excluding CCV.

    Returns:
        ShadowResult with all shadow fields populated.
    """
    prev_shadow_eav = inputs.prev_shadow_eav
    gross_premium = inputs.gross_premium
    premiums_ytd = inputs.premiums_ytd
    policy = inputs.policy
    config = inputs.config
    rates = inputs.rates
    rate_year = inputs.rate_year
    attained_age = inputs.attained_age
    days_in_month = inputs.days_in_month
    policy_debt = inputs.policy_debt
    is_inforce = inputs.is_inforce
    shadow_rider_charges = inputs.shadow_rider_charges
    projection_date = inputs.projection_date
    display_days_in_month = inputs.display_days_in_month

    if not policy.has_shadow_account:
        return ShadowResult()

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
    sa_for_basis = _sa_for_shadow_basis(policy, config)

    # ── Shadow Target Premium (col WU) ───────────────────────
    # shadow_tp = ROUND(sa_basis/1000 * (TPR + TPRTBL1*table + flat1 + flat2), 2) + CTR_CTP + PWSTP_CTP
    # For EXECUL: shadow_target = "0" → TPR=0, TPRTBL1=0, so shadow_tp = 0
    shadow_target_prem = _shadow_target_premium(
        policy=policy,
        config=config,
        rates=rates,
        rate_year=rate_year,
        sa_for_basis=sa_for_basis,
    )

    # ── Premium split under/over target (cols WX/WY) ─────────
    applied_prem = gross_premium
    prem_under, prem_over = _premium_split(
        gross_premium=gross_premium,
        premiums_ytd=premiums_ytd,
        shadow_target_prem=shadow_target_prem,
    )

    # ── Premium load rates (cols WZ/XA) ──────────────────────
    tpp_pct, epp_pct = _shadow_premium_load_rates(config, rates, rate_year)

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
    shadow_db = _shadow_death_benefit(policy, shadow_nar_av, shadow_sa)

    # ── Shadow COI rate (col XH/XI) ──────────────────────────
    # Substandard adjustment: rate * (1 + table_factor * table) + flat extras.
    # Substandard ceases STRICTLY before its cease date — same rule as the regular
    # COI (monthly_deduction._charge_active): not added on/after the cease
    # anniversary.  Previously the shadow path applied table/flat unconditionally,
    # so the flat never dropped off at the cease date.
    shadow_coi_rate = _shadow_coi_rate(
        policy=policy,
        config=config,
        rates=rates,
        rate_year=rate_year,
        projection_date=projection_date,
    )

    # ── Shadow DBD rate (col XJ) ─────────────────────────────
    shadow_dbd_rate = _configured_rate(
        config.shadow_dbd_rate,
        rates,
        "shadow_dbd",
        rate_year,
    )

    # ── Shadow NAR (col XK) ──────────────────────────────────
    # NAR = DB / (1 + dbd_rate)^(1/12) - NAR_AV
    shadow_nar = (
        shadow_db / (1.0 + shadow_dbd_rate) ** (1.0 / MONTHS_PER_YEAR)
        - shadow_nar_av
    )

    # ── Shadow COI (col XL) ──────────────────────────────────
    shadow_coi = _round_near(shadow_nar / PER_THOUSAND * shadow_coi_rate, 2)

    # ── Shadow EPU (cols XM/XN) ──────────────────────────────
    shadow_epu_rate = _configured_rate(
        config.shadow_epu_code,
        rates,
        "shadow_epu",
        rate_year,
    )

    shadow_epu = shadow_epu_rate * sa_for_basis / PER_THOUSAND

    # ── Shadow MFEE (col XO) ─────────────────────────────────
    shadow_mfee = config.shadow_mfee

    # ── Rider charges (col XP) ───────────────────────────────
    # vRiderBenefitCharge - CCV_charge (regular-side rider/benefit charges except CCV)

    # ── Shadow MD (col XQ) ───────────────────────────────────
    shadow_md = shadow_coi + shadow_epu + shadow_mfee + shadow_rider_charges

    # ── Shadow AV (col XR) ───────────────────────────────────
    if is_inforce:
        shadow_av = policy.shadow_account_value
    else:
        shadow_av = shadow_nar_av - shadow_md

    # ── Interest (cols XS-XV) ─────────────────────────────────
    # RERUN XW = (1+XV)^(XU/365) − 1 where XU is the OPTION-AWARE day count
    # (365/12 with exact-days off), not the actual calendar days.
    shadow_days, shadow_int_rate, shadow_eff_rate, shadow_interest = _shadow_interest_values(
        config=config,
        rates=rates,
        rate_year=rate_year,
        shadow_av=shadow_av,
        days_in_month=days_in_month,
        display_days_in_month=display_days_in_month,
    )

    # ── Shadow EAV (col XW) ──────────────────────────────────
    # Active only if CCV benefit active (or inherent), and age <= cease_age - 1
    shadow_eav = _shadow_eav(
        config=config,
        attained_age=attained_age,
        shadow_av=shadow_av,
        shadow_interest=shadow_interest,
    )

    # ── Shadow EAV less debt (col XX) ─────────────────────────
    shadow_eav_less_debt = _shadow_eav_less_debt(config, shadow_eav, policy_debt)

    return _build_shadow_result(locals())
