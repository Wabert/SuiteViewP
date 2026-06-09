"""Monthly deduction — Stage 2 of the monthly pipeline.

Follows RERUN CalcEngine cols 405-516.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Dict

from suiteview.illustration.core.corridor_rates import get_corridor_factor
from suiteview.illustration.core.rate_loader import IllustrationRates, get_rate
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData


def _round_near(value: float, decimals: int = 2) -> float:
    """Round half-up (normal rounding, not banker's)."""
    d = Decimal(f"{value:.12f}")
    return float(d.quantize(Decimal(10) ** -decimals, rounding=ROUND_HALF_UP))


def _trunc2(value: float) -> float:
    """Truncate to 2 decimals toward zero — matches RERUN TRUNC(x, 2)."""
    return float(Decimal(f"{value:.12f}").quantize(Decimal("0.01"), rounding=ROUND_DOWN))


def _rate_from_schedule(schedule, index: int) -> float:
    if not schedule or len(schedule) < 2:
        return 0.0
    if index < 1:
        index = 1
    if index >= len(schedule):
        return float(schedule[-1] or 0.0)
    return float(schedule[index] or 0.0)


def _charge_active(cease_date: date | None, projection_date: date | None) -> bool:
    if cease_date is None or projection_date is None:
        return True
    return projection_date <= cease_date


def _adjusted_coi_rate(
    raw_rate: float,
    segment,
    config: PlancodeConfig,
    projection_date: date | None = None,
) -> float:
    if segment is None:
        return raw_rate
    table_rating = (
        segment.table_rating
        if segment.table_rating > 0 and _charge_active(segment.table_cease_date, projection_date)
        else 0
    )
    flat_extra = (
        segment.flat_extra
        if segment.flat_extra and segment.flat_extra > 0 and _charge_active(segment.flat_cease_date, projection_date)
        else 0.0
    )
    # RERUN truncates the monthly flat extra to cents: TRUNC(flat/12, 2).
    return raw_rate * (1.0 + config.table_rating_factor * table_rating) + _trunc2(flat_extra / 12.0)


def _coverage_year(segment, projection_date: date | None, fallback_year: int) -> int:
    if segment is None or segment.issue_date is None or projection_date is None:
        return fallback_year
    years = projection_date.year - segment.issue_date.year
    if (projection_date.month, projection_date.day) < (segment.issue_date.month, segment.issue_date.day):
        years -= 1
    return max(1, years + 1)


def _policy_anniversary_rate_year(
    issue_date: date | None,
    policy: IllustrationPolicyData,
    projection_date: date | None,
    fallback_year: int,
) -> int:
    if issue_date is None or policy.issue_date is None or projection_date is None:
        return fallback_year

    def policy_anniversary_count(as_of: date) -> int:
        count = as_of.year - policy.issue_date.year
        if (as_of.month, as_of.day) < (policy.issue_date.month, policy.issue_date.day):
            count -= 1
        return max(0, count)

    elapsed_policy_anniversaries = (
        policy_anniversary_count(projection_date)
        - policy_anniversary_count(issue_date)
    )
    return max(1, elapsed_policy_anniversaries + 1)


def _coi_rate_year(segment, policy: IllustrationPolicyData, projection_date: date | None, fallback_year: int) -> int:
    issue_date = segment.issue_date if segment is not None else None
    return _policy_anniversary_rate_year(issue_date, policy, projection_date, fallback_year)


def _rider_rate_year(rider, policy: IllustrationPolicyData, projection_date: date | None, fallback_year: int) -> int:
    return _policy_anniversary_rate_year(rider.issue_date, policy, projection_date, fallback_year)


def _benefit_rate_year(benefit, policy: IllustrationPolicyData, projection_date: date | None, fallback_year: int) -> int:
    return _policy_anniversary_rate_year(benefit.issue_date, policy, projection_date, fallback_year)


@dataclass
class DeductionResult:
    """Intermediate output of calculate_deduction()."""

    nar_av: float = 0.0
    standard_db: float = 0.0
    corridor_rate: float = 0.0
    gross_db: float = 0.0
    corr_amount: float = 0.0

    # Per-segment death benefit discount
    db_by_coverage: Dict[str, float] = field(default_factory=dict)
    discounted_db_by_coverage: Dict[str, float] = field(default_factory=dict)
    discounted_db_cov1: float = 0.0
    discounted_db_corr: float = 0.0
    discounted_db: float = 0.0
    total_db: float = 0.0
    total_discounted_db: float = 0.0

    # Per-segment NAR (FIFO: AV applied to cov1 first, corridor last)
    nar_by_coverage: Dict[str, float] = field(default_factory=dict)
    nar_cov1: float = 0.0
    nar_corr: float = 0.0
    nar: float = 0.0
    total_nar: float = 0.0

    # Per-segment COI (corridor uses cov1 COI rate)
    coi_rates_by_coverage: Dict[str, float] = field(default_factory=dict)
    coi_charges_by_coverage: Dict[str, float] = field(default_factory=dict)
    coi_rate: float = 0.0
    coi_charge_cov1: float = 0.0
    coi_charge_corr: float = 0.0
    coi_charge: float = 0.0
    total_coi_charge: float = 0.0

    epu_rate: float = 0.0
    epu_charge: float = 0.0
    epu_rates_by_coverage: Dict[str, float] = field(default_factory=dict)
    epu_charges_by_coverage: Dict[str, float] = field(default_factory=dict)
    mfee_charge: float = 0.0
    av_charge: float = 0.0
    # Benefit charges (Step 2 riders/benefits)
    pw_charge: float = 0.0          # Premium Waiver (type 3 subtype 9)
    benefit_charges: float = 0.0    # Total of all benefit charges
    benefit_amounts: Dict[str, float] = field(default_factory=dict)
    benefit_rates: Dict[str, float] = field(default_factory=dict)
    benefit_charge_detail: Dict[str, float] = field(default_factory=dict)
    rider_charges: float = 0.0
    rider_amounts: Dict[str, float] = field(default_factory=dict)
    rider_rates: Dict[str, float] = field(default_factory=dict)
    rider_charge_detail: Dict[str, float] = field(default_factory=dict)
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
    projection_date: date | None = None,
    bln_round_charge: bool = False,
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
    face = policy.total_face
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
    corr_rate = get_corridor_factor(
        policy.plancode,
        attained_age,
        config.corridor_code,
    )
    gross_db = max(standard_db, corr_rate * nar_av) if corr_rate > 0 else standard_db
    corr_amount = gross_db - standard_db

    # ── 3.2.4 Discounted DB — per segment (cols 418-422) ────
    guar_rate = policy.guaranteed_interest_rate
    discount_factor = round((1.0 + guar_rate) ** (1.0 / 12.0), 7)

    segments = policy.segments or [policy.base_segment]
    segments = [segment for segment in segments if segment is not None]
    prem_adj = max(0.0, premiums_to_date - policy.withdrawals_to_date) if dbo == "C" else 0.0
    first_segment_addition = nar_av if dbo == "B" else prem_adj if dbo == "C" else 0.0

    discounted_base_segments = []
    if segments:
        for index, segment in enumerate(segments):
            segment_db = segment.face_amount
            if index == 0:
                segment_db += first_segment_addition
            discounted_base_segments.append((segment, segment_db, segment_db / discount_factor))
    else:
        fallback_db = face + first_segment_addition
        discounted_base_segments.append((None, fallback_db, fallback_db / discount_factor))

    db_by_coverage = {
        f"cov{index}": segment_db
        for index, (_, segment_db, _) in enumerate(discounted_base_segments, start=1)
    }
    discounted_db_by_coverage = {
        f"cov{index}": discounted_db_segment
        for index, (_, _, discounted_db_segment) in enumerate(discounted_base_segments, start=1)
    }
    discounted_db_cov1 = discounted_db_by_coverage.get("cov1", 0.0)

    # Corridor: treated as a separate coverage segment
    discounted_db_corr = corr_amount / discount_factor if corr_amount > 0 else 0.0

    discounted_db = sum(discounted_db_by_coverage.values()) + discounted_db_corr

    # ── 3.2.5 NAR — FIFO (cols 423-426) ──────────────────────
    # Apply AV to base coverage 1 first, then each increase, then corridor.
    remaining_av = nar_av
    segment_nars = []
    for segment, _, discounted_db_segment in discounted_base_segments:
        segment_nar = max(0.0, discounted_db_segment - remaining_av)
        remaining_av = max(0.0, remaining_av - discounted_db_segment)
        segment_nars.append((segment, segment_nar))

    nar_by_coverage = {
        f"cov{index}": segment_nar
        for index, (_, segment_nar) in enumerate(segment_nars, start=1)
    }
    nar_cov1 = nar_by_coverage.get("cov1", 0.0)
    nar_corr = max(0.0, discounted_db_corr - remaining_av)
    nar = sum(nar_by_coverage.values()) + nar_corr

    # ── 3.2.6 COI charge — per segment (col 427) ─────────────
    seg = policy.base_segment
    first_segment_coi_year = _coi_rate_year(seg, policy, projection_date, rate_year)
    first_segment_raw_coi = get_rate(rates, "coi", first_segment_coi_year)
    adjusted_coi = _adjusted_coi_rate(first_segment_raw_coi, seg, config, projection_date)

    coi_rates_by_coverage: Dict[str, float] = {}
    coi_charges_by_coverage: Dict[str, float] = {}
    for index, (segment, segment_nar) in enumerate(segment_nars, start=1):
        segment_schedule = rates.coi if segment is None else rates.segment_coi.get(segment.coverage_phase, rates.coi)
        segment_rate_year = _coi_rate_year(segment, policy, projection_date, rate_year)
        segment_raw_coi = _rate_from_schedule(segment_schedule, segment_rate_year)
        segment_adjusted_coi = _adjusted_coi_rate(segment_raw_coi, segment, config, projection_date)
        segment_coi_charge = (segment_nar / 1000.0) * segment_adjusted_coi
        if bln_round_charge:
            segment_coi_charge = _round_near(segment_coi_charge, 2)
        key = f"cov{index}"
        coi_rates_by_coverage[key] = segment_adjusted_coi
        coi_charges_by_coverage[key] = segment_coi_charge

    coi_charge_cov1 = coi_charges_by_coverage.get("cov1", 0.0)
    coi_charge_corr = (nar_corr / 1000.0) * adjusted_coi
    coi_charge = sum(coi_charges_by_coverage.values()) + coi_charge_corr

    # ── 3.2.7 EPU charge (col 496) ───────────────────────────
    epu_rate = 0.0
    epu_charge = 0.0
    epu_rates_by_coverage: Dict[str, float] = {}
    epu_charges_by_coverage: Dict[str, float] = {}

    epu_segments = segments if segments else [None]

    if config.epu_code == "Table":
        for index, segment in enumerate(epu_segments, start=1):
            segment_schedule = rates.epu if segment is None else rates.segment_epu.get(segment.coverage_phase, rates.epu)
            segment_rate_year = _coverage_year(segment, projection_date, rate_year)
            segment_epu_rate = _rate_from_schedule(segment_schedule, segment_rate_year)
            if config.epu_sa_basis == "CurrentSA":
                segment_basis = segment.face_amount if segment else face
            elif config.epu_sa_basis == "OriginalSA":
                segment_basis = segment.original_face_amount if segment else face
            else:
                segment_basis = segment.face_amount if segment else face
            segment_epu_charge = (segment_basis / 1000.0) * segment_epu_rate
            if bln_round_charge:
                segment_epu_charge = _round_near(segment_epu_charge, 2)
            key = f"cov{index}"
            epu_rates_by_coverage[key] = segment_epu_rate
            epu_charges_by_coverage[key] = segment_epu_charge
        epu_rate = epu_rates_by_coverage.get("cov1", 0.0)
        epu_charge = sum(epu_charges_by_coverage.values())
    else:
        try:
            epu_flat = float(config.epu_code)
        except (ValueError, TypeError):
            epu_flat = 0.0
        for index, segment in enumerate(epu_segments, start=1):
            segment_units = segment.units if segment else policy.units
            key = f"cov{index}"
            epu_rates_by_coverage[key] = epu_flat
            segment_epu_charge = epu_flat * segment_units
            if bln_round_charge:
                segment_epu_charge = _round_near(segment_epu_charge, 2)
            epu_charges_by_coverage[key] = segment_epu_charge
        epu_rate = epu_rates_by_coverage.get("cov1", 0.0)
        epu_charge = sum(epu_charges_by_coverage.values())

    if bln_round_charge:
        coi_charge = _round_near(coi_charge, 2)
        epu_charge = _round_near(epu_charge, 2)

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
    benefit_amounts: Dict[str, float] = {}
    benefit_rates: Dict[str, float] = {}
    benefit_charge_detail: Dict[str, float] = {}
    rider_charges = 0.0
    rider_amounts: Dict[str, float] = {}
    rider_rates: Dict[str, float] = {}
    rider_charge_detail: Dict[str, float] = {}

    base_deduction = coi_charge + epu_charge + mfee_charge + av_charge

    for rider in policy.riders:
        if not rider.is_active:
            continue
        rider_key = rider.export_key
        rider_rate_schedule = rates.rider_rates.get(rider_key, [])
        rider_rate = 0.0
        if rider_rate_schedule:
            rider_rate_year = _rider_rate_year(rider, policy, projection_date, rate_year)
            rider_rate = _rate_from_schedule(rider_rate_schedule, rider_rate_year)
        elif rider.coi_rate is not None:
            rider_rate = float(rider.coi_rate)
        elif rider.premium_rate is not None:
            rider_rate = float(rider.premium_rate)

        # Apply rider substandard (table rating + flat extra), mirroring RERUN
        # RR = RO*(1 + factor*table) + TRUNC(flat/12, 2). The base COI applies the
        # same adjustment; the rider previously used the raw rate, undercharging
        # any table-rated/flat-extra rider.
        rider_table = rider.table_rating if rider.table_rating else 0
        rider_flat = rider.flat_extra if rider.flat_extra else 0.0
        rider_rate = (
            rider_rate * (1.0 + config.table_rating_factor * rider_table)
            + _trunc2(rider_flat / 12.0)
        )

        rider_amount = rider.face_amount
        rider_charge = rider.units * rider_rate
        if bln_round_charge:
            rider_charge = _round_near(rider_charge, 2)
        rider_amounts[rider_key] = rider_amount
        rider_rates[rider_key] = rider_rate
        rider_charge_detail[rider_key] = rider_charge
        rider_charges += rider_charge

    non_pw_benefit_charges = 0.0
    for ben in sorted(policy.benefits, key=lambda benefit: (benefit.benefit_type or "") == "3"):
        if not ben.is_active:
            continue
        if (ben.benefit_type or "").startswith("#"):
            continue
        ben_type = ben.benefit_type or ""
        ben_subtype = ben.benefit_subtype or ""
        ben_key = (ben.benefit_type or "") + (ben.benefit_subtype or "")
        ben_rates = rates.benefit_coi.get(ben_key, [])

        # COI duration is item-specific, but rates update on policy anniversaries.
        ben_coi_rate = 0.0
        if ben_rates:
            benefit_rate_year = _benefit_rate_year(ben, policy, projection_date, rate_year)
            ben_coi_rate = _rate_from_schedule(ben_rates, benefit_rate_year)
        elif ben.coi_rate is not None:
            ben_coi_rate = float(ben.coi_rate)

        substandard_factor = ben.rating_factor if ben.rating_factor and ben.rating_factor > 0 else 1.0
        adjusted_rate = ben_coi_rate * substandard_factor

        if ben_type == "3":
            benefit_amount = max(monthly_mtp, base_deduction + rider_charges + non_pw_benefit_charges)
            charge = adjusted_rate * benefit_amount
            pw_charge = charge
        else:
            benefit_amount = ben.benefit_amount
            charge = ben.units * adjusted_rate

        if bln_round_charge:
            charge = _round_near(charge, 2)
            if ben_type == "3":
                pw_charge = charge

        benefit_amounts[ben_key] = benefit_amount
        benefit_rates[ben_key] = adjusted_rate
        benefit_charge_detail[ben_key] = charge
        benefit_charges += charge
        if ben_type != "3":
            non_pw_benefit_charges += charge

    # ── 3.2.11 Total deduction (cols 515-516) ────────────────
    total_deduction = base_deduction + benefit_charges + rider_charges
    if bln_round_charge:
        total_deduction = _round_near(total_deduction, 2)
    av_after_deduction = mAV - total_deduction

    return DeductionResult(
        nar_av=nar_av,
        standard_db=standard_db,
        corridor_rate=corr_rate,
        gross_db=gross_db,
        corr_amount=corr_amount,
        db_by_coverage=db_by_coverage,
        discounted_db_by_coverage=discounted_db_by_coverage,
        discounted_db_cov1=discounted_db_cov1,
        discounted_db_corr=discounted_db_corr,
        discounted_db=discounted_db,
        total_db=gross_db,
        total_discounted_db=discounted_db,
        nar_by_coverage=nar_by_coverage,
        nar_cov1=nar_cov1,
        nar_corr=nar_corr,
        nar=nar,
        total_nar=nar,
        coi_rates_by_coverage=coi_rates_by_coverage,
        coi_charges_by_coverage=coi_charges_by_coverage,
        coi_rate=adjusted_coi,
        coi_charge_cov1=coi_charge_cov1,
        coi_charge_corr=coi_charge_corr,
        coi_charge=coi_charge,
        total_coi_charge=coi_charge,
        epu_rate=epu_rate,
        epu_charge=epu_charge,
        epu_rates_by_coverage=epu_rates_by_coverage,
        epu_charges_by_coverage=epu_charges_by_coverage,
        mfee_charge=mfee_charge,
        av_charge=av_charge,
        pw_charge=pw_charge,
        benefit_charges=benefit_charges,
        benefit_amounts=benefit_amounts,
        benefit_rates=benefit_rates,
        benefit_charge_detail=benefit_charge_detail,
        rider_charges=rider_charges,
        rider_amounts=rider_amounts,
        rider_rates=rider_rates,
        rider_charge_detail=rider_charge_detail,
        total_deduction=total_deduction,
        av_after_deduction=av_after_deduction,
    )
