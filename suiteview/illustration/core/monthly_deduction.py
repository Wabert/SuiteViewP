"""Monthly deduction — Stage 2 of the monthly pipeline.

Follows RERUN CalcEngine cols 405-516.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from suiteview.illustration.core.corridor_rates import get_corridor_factor
from suiteview.illustration.core.rate_loader import IllustrationRates, get_rate
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData


def _round_near(value: float, decimals: int = 2) -> float:
    """Round half-up (normal rounding, not banker's)."""
    d = Decimal(str(value))
    return float(d.quantize(Decimal(10) ** -decimals, rounding=ROUND_HALF_UP))


@dataclass
class DeductionResult:
    """Intermediate output of calculate_deduction()."""

    nar_av: float = 0.0
    standard_db: float = 0.0
    corridor_rate: float = 0.0
    gross_db: float = 0.0
    corr_amount: float = 0.0

    # Per-segment death benefit discount
    discounted_db_cov1: float = 0.0
    discounted_db_corr: float = 0.0
    discounted_db: float = 0.0

    # Per-segment NAR (FIFO: AV applied to cov1 first, corridor last)
    nar_cov1: float = 0.0
    nar_corr: float = 0.0
    nar: float = 0.0

    # Per-segment COI (corridor uses cov1 COI rate)
    coi_rate: float = 0.0
    coi_charge_cov1: float = 0.0
    coi_charge_corr: float = 0.0
    coi_charge: float = 0.0

    epu_rate: float = 0.0
    epu_charge: float = 0.0
    mfee_charge: float = 0.0
    av_charge: float = 0.0
    # Benefit charges (Step 2 riders/benefits)
    pw_charge: float = 0.0          # Premium Waiver (type 3 subtype 9)
    benefit_charges: float = 0.0    # Total of all benefit charges
    total_deduction: float = 0.0
    av_after_deduction: float = 0.0


def calculate_deduction(
    av_after_premium: float,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    rate_year: int,
    attained_age: int,
    premiums_to_date: float,
    monthly_mtp: float = 0.0,
) -> DeductionResult:
    """Calculate monthly deduction charges.

    Args:
        av_after_premium: AV after premium application (mAV).
        policy: Policy data.
        config: Plancode configuration.
        rates: Pre-loaded rate arrays.
        rate_year: Current policy year for rate table lookup.
        attained_age: Current attained age for corridor lookup.
        premiums_to_date: Cumulative premiums (for DBO C).
        monthly_mtp: Monthly minimum target premium (for PW charge basis).

    Returns:
        DeductionResult with all deduction-stage outputs.
    """
    mAV = av_after_premium

    # ── 3.2.1 NAR AV (col 406) ───────────────────────────────
    nar_av = max(0.0, mAV)

    # ── 3.2.2 Standard death benefit (col 407) ────────────────
    face = policy.face_amount
    dbo = policy.db_option

    if dbo == "A":
        standard_db = face
    elif dbo == "B":
        standard_db = face + nar_av
    elif dbo == "C":
        standard_db = face + max(0.0, premiums_to_date - policy.withdrawals_to_date)
    else:
        standard_db = face

    # ── 3.2.3 Gross DB — corridor check (cols 408-411) ───────
    corr_rate = get_corridor_factor(policy.plancode, attained_age)
    gross_db = max(standard_db, corr_rate * nar_av) if corr_rate > 0 else standard_db
    corr_amount = gross_db - standard_db

    # ── 3.2.4 Discounted DB — per segment (cols 418-422) ────
    guar_rate = policy.guaranteed_interest_rate
    discount_factor = round((1.0 + guar_rate) ** (1.0 / 12.0), 7)

    # Cov1: standard death benefit
    if dbo == "A":
        discounted_db_cov1 = face / discount_factor
    elif dbo == "B":
        discounted_db_cov1 = (face + nar_av) / discount_factor
    elif dbo == "C":
        prem_adj = max(0.0, premiums_to_date - policy.withdrawals_to_date)
        discounted_db_cov1 = (face + prem_adj) / discount_factor
    else:
        discounted_db_cov1 = face / discount_factor

    # Corridor: treated as a separate coverage segment
    discounted_db_corr = corr_amount / discount_factor if corr_amount > 0 else 0.0

    discounted_db = discounted_db_cov1 + discounted_db_corr

    # ── 3.2.5 NAR — FIFO (cols 423-426) ──────────────────────
    # Apply AV to cov1 first; any remainder reduces corridor NAR
    nar_cov1 = max(0.0, discounted_db_cov1 - nar_av)
    remaining_av = max(0.0, nar_av - discounted_db_cov1)
    nar_corr = max(0.0, discounted_db_corr - remaining_av)
    nar = nar_cov1 + nar_corr

    # ── 3.2.6 COI charge — per segment (col 427) ─────────────
    coi_rate_raw = get_rate(rates, "coi", rate_year)

    # Substandard adjustment
    seg = policy.base_segment
    if seg and seg.table_rating > 0:
        tbl_factor = config.table_rating_factor
        flat_extra_monthly = seg.flat_extra / 12.0 if seg.flat_extra else 0.0
        adjusted_coi = (
            coi_rate_raw * (1.0 + tbl_factor * seg.table_rating) + flat_extra_monthly
        )
    elif seg and seg.flat_extra and seg.flat_extra > 0:
        flat_extra_monthly = seg.flat_extra / 12.0
        adjusted_coi = coi_rate_raw + flat_extra_monthly
    else:
        adjusted_coi = coi_rate_raw

    # Cov1 COI on cov1 NAR
    coi_charge_cov1 = (nar_cov1 / 1000.0) * adjusted_coi

    # Corridor COI uses the newest segment's rate (cov1 for M1)
    coi_charge_corr = (nar_corr / 1000.0) * adjusted_coi

    coi_charge = coi_charge_cov1 + coi_charge_corr

    # ── 3.2.7 EPU charge (col 496) ───────────────────────────
    epu_rate = 0.0
    epu_charge = 0.0

    if config.epu_code == "Table":
        epu_rate = get_rate(rates, "epu", rate_year)
        if config.epu_sa_basis == "CurrentSA":
            epu_charge = _round_near((face / 1000.0) * epu_rate, 2)
        elif config.epu_sa_basis == "OriginalSA":
            orig_face = seg.original_face_amount if seg else face
            epu_charge = _round_near((orig_face / 1000.0) * epu_rate, 2)
    else:
        try:
            epu_flat = float(config.epu_code)
        except (ValueError, TypeError):
            epu_flat = 0.0
        epu_charge = _round_near(epu_flat * policy.units, 2)

    # ── 3.2.8 Monthly fee (col 498) ──────────────────────────
    if config.mfee == "Table":
        mfee_charge = get_rate(rates, "mfee", rate_year)
    else:
        try:
            mfee_charge = float(config.mfee)
        except (ValueError, TypeError):
            mfee_charge = 0.0

    # ── 3.2.9 AV charge (col 503) — monthly rate, NOT /12 ───
    av_charge = 0.0
    if config.poav_code == "Table":
        poav_rate = get_rate(rates, "poav", rate_year)
        av_charge = max(0.0, mAV * poav_rate)

    # ── 3.2.10 Benefit charges ────────────────────────────────
    # Computed AFTER base deduction — PW waives greater of MTP or base deduction
    pw_charge = 0.0
    benefit_charges = 0.0

    base_deduction = coi_charge + epu_charge + mfee_charge + av_charge

    for ben in policy.benefits:
        if not ben.is_active:
            continue
        if (ben.benefit_type or "").startswith("#"):
            continue
        ben_key = (ben.benefit_type or "") + (ben.benefit_subtype or "")
        ben_rates = rates.benefit_coi.get(ben_key, [])
        if not ben_rates:
            continue

        # Rate indexed by policy year (benefit issued at policy inception)
        idx = rate_year if rate_year < len(ben_rates) else len(ben_rates) - 1
        if idx < 1:
            idx = 1
        ben_coi_rate = float(ben_rates[idx]) if ben_rates[idx] is not None else 0.0

        if ben_key == "39":  # Premium Waiver — charge on greater of MTP or base deduction
            charge = ben_coi_rate * max(monthly_mtp, base_deduction)
            pw_charge = charge
        else:
            # Generic benefit: units-based charge
            charge = (ben.units / 1000.0) * ben_coi_rate

        benefit_charges += charge

    # ── 3.2.11 Total deduction (cols 515-516) ────────────────
    total_deduction = base_deduction + benefit_charges
    av_after_deduction = mAV - total_deduction

    return DeductionResult(
        nar_av=nar_av,
        standard_db=standard_db,
        corridor_rate=corr_rate,
        gross_db=gross_db,
        corr_amount=corr_amount,
        discounted_db_cov1=discounted_db_cov1,
        discounted_db_corr=discounted_db_corr,
        discounted_db=discounted_db,
        nar_cov1=nar_cov1,
        nar_corr=nar_corr,
        nar=nar,
        coi_rate=adjusted_coi,
        coi_charge_cov1=coi_charge_cov1,
        coi_charge_corr=coi_charge_corr,
        coi_charge=coi_charge,
        epu_rate=epu_rate,
        epu_charge=epu_charge,
        mfee_charge=mfee_charge,
        av_charge=av_charge,
        pw_charge=pw_charge,
        benefit_charges=benefit_charges,
        total_deduction=total_deduction,
        av_after_deduction=av_after_deduction,
    )
