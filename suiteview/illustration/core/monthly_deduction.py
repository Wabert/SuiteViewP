"""Monthly deduction — stage 2 of the monthly pipeline.

Follows RERUN CalcEngine cols 405-516. Dollar amounts are monthly dollars unless
named annual; COI/EPU/rider rates are monthly rates per 1,000 of net amount at
risk or specified amount. Death benefit and corridor calculations use the
pre-interest account value supplied by the pipeline. Coverage table ratings and
flat extras are applied only while active on the projection date; flat extras
are truncated to monthly cents before being converted to per-1,000 charges.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Dict

from suiteview.core.benefit_rate_rules import benefit_charge_factor
from suiteview.illustration.constants import (
    DB_OPTION_INCREASING,
    DB_OPTION_LEVEL,
    DB_OPTION_RETURN_OF_PREMIUM,
    MONTHS_PER_YEAR,
    PER_THOUSAND,
    SA_BASIS_ORIGINAL,
)
from suiteview.illustration.core.corridor_rates import corridor_factor
from suiteview.illustration.core.rate_loader import IllustrationRates, get_rate
from suiteview.illustration.core.skipped_coverage import epu_schedule_year
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
    benefit_rate_keys,
    rider_active_on,
)


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
    """Whether a substandard charge (table rating / flat extra) is still active.

    STRICT: the charge ceases AT the supplied cease-date anniversary, so it is
    NOT applied on (or after) ``cease_date``. This helper remains for
    substandard coverage charges; benefit premiums use ``pay_up_date`` directly.
    An inclusive ``<=`` here would charge the flat extra/table rating for one
    extra anniversary month.
    """
    if cease_date is None or projection_date is None:
        return True
    return projection_date < cease_date


def target_waiver_charge(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rate: float,
    projection_date: date | None,
) -> tuple[float, float]:
    """Return PWoT annual target amount and cent-rounded monthly charge.

    The target already reflects the insured's rating, so CyberLife applies no
    table factor to the per-100 rate (Albert F06, 26/000272626 and
    26/000299857; Robert 2026-10-01). ``projection_date`` is kept for the
    shared call signature.
    """
    if config.pwot_coi_basis not in (2, 3):
        raise ValueError("Target-based PWoT requires MTP (2) or CTP (3).")
    amount = policy.mtp * MONTHS_PER_YEAR if config.pwot_coi_basis == 2 else policy.ctp
    return amount, _round_near(amount * rate / 100.0, 2)


def _segment_matured(segment, projection_date: date | None) -> bool:
    """Whether a base coverage segment has reached its own maturity date.

    An increase segment issued off-anniversary (with a bumped issue age) can
    mature before the policy. On/after its maturity date it stops accruing COI
    and EPU charges instead of riding the last rate to the policy's maturity —
    mirroring RERUN, whose per-coverage rate tables end at the coverage maturity.
    """
    if segment is None or projection_date is None:
        return False
    maturity_date = getattr(segment, "maturity_date", None)
    return maturity_date is not None and projection_date >= maturity_date


def _segment_not_yet_issued(segment, projection_date: date | None) -> bool:
    """Whether a coverage segment's issue date is after the projection month.

    CyberLife carries scheduled coverage phases (e.g. a future increase) with a
    future issue date; until that date they add no death benefit, NAR, COI or
    EPU (fix E04, 26/000324822 phase 12).
    """
    if segment is None or projection_date is None:
        return False
    issue_date = getattr(segment, "issue_date", None)
    return issue_date is not None and issue_date > projection_date


def _segment_charge_inactive(segment, projection_date: date | None) -> bool:
    return _segment_matured(segment, projection_date) or _segment_not_yet_issued(
        segment, projection_date)


def _pending_segments(policy: IllustrationPolicyData, projection_date: date | None) -> list[bool]:
    """Per base segment: issued after ``projection_date`` (the base never is)."""
    segments = [segment for segment in (policy.segments or [policy.base_segment]) if segment is not None]
    return [
        index > 0 and _segment_not_yet_issued(segment, projection_date)
        for index, segment in enumerate(segments)
    ]


def in_force_face(policy: IllustrationPolicyData, projection_date: date | None) -> float:
    """Total base face excluding coverage segments not yet issued on ``projection_date``."""
    pending = _pending_segments(policy, projection_date)
    if not any(pending):
        return policy.total_face
    segments = [segment for segment in (policy.segments or [policy.base_segment]) if segment is not None]
    return sum(segment.face_amount for segment, skip in zip(segments, pending) if not skip)


def _at_or_after_policy_maturity(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    attained_age: int,
) -> bool:
    maturity_ages = [
        age
        for age in (policy.maturity_age, config.maturity_age)
        if age is not None and age > 0
    ]
    return bool(maturity_ages and attained_age >= min(maturity_ages))


def premiums_and_charges_ceased(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    attained_age: int,
) -> bool:
    """No premium, and no COI/EPU/benefit/rider charge: at maturity, or from the plan's
    ``charge_cease_age`` (paid up: only the scheduled MFEE is still deducted, the AV
    earns interest and the DB stays in force)."""
    return config.charges_ceased(attained_age) or _at_or_after_policy_maturity(
        policy, config, attained_age)


def _corridor_coverage_key(
    segment_nars: list[tuple[CoverageSegment | None, float]],
    projection_date: date | None,
) -> str | None:
    """Select the last active segment in the engine's oldest-to-newest order."""
    for index in range(len(segment_nars) - 1, -1, -1):
        segment, _ = segment_nars[index]
        if segment is not None:
            if (
                segment.face_amount <= 0
                or segment.status == "T"
                or _segment_charge_inactive(segment, projection_date)
            ):
                continue
        return f"cov{index + 1}"
    return None


def _adjusted_coi_rate(
    raw_rate: float,
    segment,
    config: PlancodeConfig,
    projection_date: date | None = None,
    round_5: bool = False,
) -> float:
    """Substandard-adjusted COI rate.

    RERUN rounds the FIRST coverage's adjusted rate to 5 decimals (CalcEngine
    ``OY = ROUND(rate*(1+factor*table)+flat, 5)``) but leaves cov 2/3 (OZ/PA)
    at full precision — pass ``round_5=True`` for cov 1 only.
    """
    if segment is None:
        return raw_rate
    if config.is_iswl:
        # ISWL substandard ratings are paid in the fixed premium, not charged in the
        # COI (verified on table-rated 13447734; CyberDoc B10 makes substandard COI optional).
        # CyberLife charges NAR x the IAF annual rate / 12 unrounded: RERUN's 5-decimal
        # round is a UL rule (80136200 15902845: 55,790.84 x 2.38/12 = 11.0652 -> 11.07;
        # 0.19833 gives 11.06).
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
    adjusted = raw_rate * (1.0 + config.table_rating_factor * table_rating) + _trunc2(
        flat_extra / MONTHS_PER_YEAR
    )
    return _round_near(adjusted, 5) if round_5 else adjusted


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


def benefit_rate_year(benefit, policy: IllustrationPolicyData, projection_date: date | None, fallback_year: int) -> int:
    """Benefit COI schedule duration on ``projection_date`` (policy-anniversary steps)."""
    return _policy_anniversary_rate_year(benefit.issue_date, policy, projection_date, fallback_year)


@dataclass
class RatchetCOIResult:
    """Output of _ratchet_coi() — the ratchet-banded base COI override."""

    charges_by_coverage: Dict[str, float] = field(default_factory=dict)
    charge_corr: float = 0.0
    total: float = 0.0
    cov1_band1_rate: float = 0.0
    band1_nar: Dict[str, float] = field(default_factory=dict)
    band2_nar: Dict[str, float] = field(default_factory=dict)
    band1_rates: Dict[str, float] = field(default_factory=dict)
    band2_rates: Dict[str, float] = field(default_factory=dict)


def _ratchet_coi(
    segment_nars,
    nar_corr: float,
    rates: IllustrationRates,
    config: PlancodeConfig,
    policy: IllustrationPolicyData,
    projection_date: date | None,
    rate_year: int,
    bln_round_charge: bool,
) -> RatchetCOIResult:
    """Ratchet-banding base COI charge (RERUN CalcEngine cols PP-QX).

    Unlike the regular COI — where every dollar of a segment's NAR is charged at
    that segment's single banded rate — ratchet banding splits the *total* NAR at
    a single break point: all NAR up to ``rates.band_break`` (filled across
    segments in FIFO order, corridor last) is charged at the band-1 rate, and the
    excess at the band-2 rate. Only the earliest UL plans (~1983) are coded this
    way; ``config.rachet_banding`` gates it.

    Each base segment carries band-1 and band-2 COI schedules (loaded by
    rate_loader). Per RERUN: charge = band1_NAR·band1_rate/1000 +
    band2_NAR·band2_rate/1000 (QT-QV). The band rates are substandard-adjusted
    like the regular block (OY-PA): per-segment table rating, ROUND(.,5) on cov 1.
    The corridor (QW) uses the last active segment's substandard-adjusted band
    rates against the band-1/band-2 corridor NAR (QO/QS).

    Mirrors RERUN v20.0, in which the original PP-QX quirks were corrected so the
    ratchet block matches the regular block: corridor uses the substandard rates
    (PV-PX/PY-QA, not raw PP-PR/PS-PU) and the band-2 corridor NAR QS (not OS);
    each segment uses its own table rating; cov-1 rate is rounded to 5 decimals
    and a zero raw rate yields a zero adjusted rate.
    """
    band_break = rates.band_break
    # Total NAR per slot, in FIFO fill order: base segments first, corridor last.
    nar_slots = [nar for (_, nar) in segment_nars] + [nar_corr]

    # Fill band 1 up to the break across slots (RERUN QL-QO); excess is band 2.
    band1_slots = []
    cumulative = 0.0
    for nar in nar_slots:
        room = max(0.0, band_break - cumulative)
        band1_slots.append(min(nar, room))
        cumulative += nar
    band2_slots = [nar - b1 for nar, b1 in zip(nar_slots, band1_slots)]

    result = RatchetCOIResult()
    for index, (segment, _) in enumerate(segment_nars, start=1):
        phase = segment.coverage_phase if segment is not None else None
        seg_year = _coi_rate_year(segment, policy, projection_date, rate_year)
        b1_raw = _rate_from_schedule(rates.segment_coi_band1.get(phase, []), seg_year)
        b2_raw = _rate_from_schedule(rates.segment_coi_band2.get(phase, []), seg_year)
        # ROUND(.,5) on cov 1 (RERUN PV/PY ≡ regular OY); zero raw rate → 0
        # adjusted rate (RERUN IF(rate=0,0,...)), so a flat extra never rides on a
        # zero base rate.
        b1_rate = _adjusted_coi_rate(b1_raw, segment, config, projection_date, round_5=(index == 1)) if b1_raw else 0.0
        b2_rate = _adjusted_coi_rate(b2_raw, segment, config, projection_date, round_5=(index == 1)) if b2_raw else 0.0
        if _segment_charge_inactive(segment, projection_date):
            b1_rate = 0.0
            b2_rate = 0.0
        b1_nar = band1_slots[index - 1]
        b2_nar = band2_slots[index - 1]
        charge = (b1_nar / PER_THOUSAND) * b1_rate + (b2_nar / PER_THOUSAND) * b2_rate
        if bln_round_charge:
            charge = _round_near(charge, 2)
        key = f"cov{index}"
        result.charges_by_coverage[key] = charge
        result.band1_nar[key] = b1_nar
        result.band2_nar[key] = b2_nar
        result.band1_rates[key] = b1_rate
        result.band2_rates[key] = b2_rate

    # Corridor (RERUN QW, corrected): the last active base segment's
    # substandard-adjusted band rates against the band-1/band-2 corridor NAR.
    # Reuse the rates already computed for that segment above.
    last_key = _corridor_coverage_key(segment_nars, projection_date)
    corr_b1_rate = result.band1_rates[last_key] if last_key is not None else 0.0
    corr_b2_rate = result.band2_rates[last_key] if last_key is not None else 0.0
    corr_b1_nar = band1_slots[-1]
    corr_b2_nar = band2_slots[-1]
    charge_corr = (
        (corr_b1_nar / PER_THOUSAND) * corr_b1_rate
        + (corr_b2_nar / PER_THOUSAND) * corr_b2_rate
    )
    if bln_round_charge:
        charge_corr = _round_near(charge_corr, 2)

    result.band1_nar["corr"] = corr_b1_nar
    result.band2_nar["corr"] = corr_b2_nar
    result.band1_rates["corr"] = corr_b1_rate
    result.band2_rates["corr"] = corr_b2_rate
    result.charge_corr = charge_corr
    result.total = sum(result.charges_by_coverage.values()) + charge_corr
    result.cov1_band1_rate = result.band1_rates.get("cov1", 0.0)
    return result


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

    # Per-segment COI (corridor uses the latest active segment's rate)
    coi_rates_by_coverage: Dict[str, float] = field(default_factory=dict)
    coi_charges_by_coverage: Dict[str, float] = field(default_factory=dict)
    coi_rate: float = 0.0
    coi_rate_corr: float = 0.0
    coi_charge_cov1: float = 0.0
    coi_charge_corr: float = 0.0
    coi_charge: float = 0.0
    total_coi_charge: float = 0.0

    # Ratchet banding (RERUN CalcEngine PP-QX) — populated only when the plancode
    # is ratchet-banded. NAR up to band_break is charged at the band-1 rate, the
    # excess at the band-2 rate. Keys mirror coi_charges_by_coverage plus "corr".
    ratchet_active: bool = False
    band_break: float = 0.0
    coi_band1_nar_by_coverage: Dict[str, float] = field(default_factory=dict)
    coi_band2_nar_by_coverage: Dict[str, float] = field(default_factory=dict)
    coi_band1_rates_by_coverage: Dict[str, float] = field(default_factory=dict)
    coi_band2_rates_by_coverage: Dict[str, float] = field(default_factory=dict)

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


@dataclass
class DeathBenefitBasis:
    """Death-benefit and discounted coverage basis before NAR allocation."""

    mAV: float
    nar_av: float
    face: float
    dbo: str
    standard_db: float
    corridor_rate: float
    gross_db: float
    corr_amount: float
    discount_factor: float
    segments: list
    discounted_base_segments: list
    db_by_coverage: Dict[str, float]
    discounted_db_by_coverage: Dict[str, float]
    discounted_db_cov1: float
    discounted_db_corr: float
    discounted_db: float


@dataclass
class NarAllocation:
    """FIFO net-amount-at-risk allocation across coverages and corridor."""

    segment_nars: list
    nar_by_coverage: Dict[str, float]
    nar_cov1: float
    nar_corr: float
    nar: float


@dataclass
class CoiChargeBreakdown:
    """Base COI charges, including optional ratchet-band details."""

    rates_by_coverage: Dict[str, float] = field(default_factory=dict)
    charges_by_coverage: Dict[str, float] = field(default_factory=dict)
    rate_cov1: float = 0.0
    rate_corr: float = 0.0
    charge_cov1: float = 0.0
    charge_corr: float = 0.0
    charge_total: float = 0.0
    ratchet_active: bool = False
    band_break: float = 0.0
    band1_nar_by_coverage: Dict[str, float] = field(default_factory=dict)
    band2_nar_by_coverage: Dict[str, float] = field(default_factory=dict)
    band1_rates_by_coverage: Dict[str, float] = field(default_factory=dict)
    band2_rates_by_coverage: Dict[str, float] = field(default_factory=dict)


@dataclass
class ExpenseChargeBreakdown:
    """Monthly EPU, policy-fee and account-value expense charges."""

    epu_rate: float = 0.0
    epu_charge: float = 0.0
    epu_rates_by_coverage: Dict[str, float] = field(default_factory=dict)
    epu_charges_by_coverage: Dict[str, float] = field(default_factory=dict)
    mfee_charge: float = 0.0
    av_charge: float = 0.0


@dataclass
class BenefitChargeBreakdown:
    """Rider and benefit charges added after the base deduction."""

    pw_charge: float = 0.0
    benefit_charges: float = 0.0
    benefit_amounts: Dict[str, float] = field(default_factory=dict)
    benefit_rates: Dict[str, float] = field(default_factory=dict)
    benefit_charge_detail: Dict[str, float] = field(default_factory=dict)
    rider_charges: float = 0.0
    rider_amounts: Dict[str, float] = field(default_factory=dict)
    rider_rates: Dict[str, float] = field(default_factory=dict)
    rider_charge_detail: Dict[str, float] = field(default_factory=dict)


def _build_death_benefit_basis(
    mAV: float,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    attained_age: int,
    premiums_to_date: float,
    projection_date: date | None = None,
    corridor_rate: float | None = None,
) -> DeathBenefitBasis:
    """Build standard/corridor death benefit and discounted coverage slices.

    ``corridor_rate`` overrides the plan's GPT corridor factor (the CVAT minimum
    death benefit ratio from ``cvat_nsp.CvatCorridor``).

    Segments not yet issued at ``projection_date`` keep their coverage slot
    with zero death benefit."""
    nar_av = max(0.0, mAV)
    segments = [segment for segment in (policy.segments or [policy.base_segment]) if segment is not None]
    pending = _pending_segments(policy, projection_date)
    face = in_force_face(policy, projection_date)
    dbo = policy.db_option
    if dbo == DB_OPTION_LEVEL:
        standard_db = face
    elif dbo == DB_OPTION_INCREASING:
        standard_db = face + nar_av
    elif dbo == DB_OPTION_RETURN_OF_PREMIUM:
        standard_db = face + _return_of_premium(premiums_to_date, policy)
    else:
        standard_db = face

    corr_rate = corridor_rate if corridor_rate is not None else corridor_factor(config, attained_age)
    gross_db = (
        max(standard_db, float(math.floor(corr_rate * nar_av + 1e-6)))
        if corr_rate > 0 else standard_db
    )
    corr_amount = gross_db - standard_db
    discount_factor = round((1.0 + config.dbd) ** (1.0 / MONTHS_PER_YEAR), 7)
    prem_adj = (
        _return_of_premium(premiums_to_date, policy)
        if dbo == DB_OPTION_RETURN_OF_PREMIUM else 0.0
    )
    first_addition = (
        nar_av if dbo == DB_OPTION_INCREASING
        else prem_adj if dbo == DB_OPTION_RETURN_OF_PREMIUM else 0.0
    )
    discounted_base_segments = _discount_base_segments(
        segments, face, first_addition, discount_factor, pending)
    db_by_coverage = {
        f"cov{index}": segment_db
        for index, (_, segment_db, _) in enumerate(discounted_base_segments, start=1)
    }
    discounted_db_by_coverage = {
        f"cov{index}": discounted_db_segment
        for index, (_, _, discounted_db_segment) in enumerate(discounted_base_segments, start=1)
    }
    discounted_db_corr = corr_amount / discount_factor if corr_amount > 0 else 0.0
    return DeathBenefitBasis(
        mAV=mAV, nar_av=nar_av, face=face, dbo=dbo, standard_db=standard_db,
        corridor_rate=corr_rate, gross_db=gross_db, corr_amount=corr_amount,
        discount_factor=discount_factor, segments=segments,
        discounted_base_segments=discounted_base_segments,
        db_by_coverage=db_by_coverage,
        discounted_db_by_coverage=discounted_db_by_coverage,
        discounted_db_cov1=discounted_db_by_coverage.get("cov1", 0.0),
        discounted_db_corr=discounted_db_corr,
        discounted_db=sum(discounted_db_by_coverage.values()) + discounted_db_corr,
    )


def _return_of_premium(premiums_to_date: float, policy: IllustrationPolicyData) -> float:
    """Option C death-benefit addition: premiums less NET withdrawals. The in-force
    withdrawals total is gross of the per-withdrawal fee (1U145500 UIP50722: six $25
    fees, CyberLife NAR 150 higher than premiums less TOT_WTD_AMT). After a skipped-coverage
    reinstatement only the basis since the latest REN_DT counts (UIP88048)."""
    return policy.option_c_premium_base(premiums_to_date, policy.withdrawals_to_date)


def _discount_base_segments(
    segments, face: float, first_addition: float, discount_factor: float,
    pending: list[bool] | None = None,
) -> list:
    """Discount base coverage death benefits one month for NAR calculation."""
    if not segments:
        fallback_db = face + first_addition
        return [(None, fallback_db, fallback_db / discount_factor)]
    result = []
    for index, segment in enumerate(segments):
        if pending and pending[index]:
            result.append((segment, 0.0, 0.0))
            continue
        segment_db = segment.face_amount + (first_addition if index == 0 else 0.0)
        result.append((segment, segment_db, segment_db / discount_factor))
    return result


def _allocate_nar(basis: DeathBenefitBasis) -> NarAllocation:
    """Allocate account value FIFO against discounted DB slices."""
    remaining_av = basis.nar_av
    segment_nars = []
    for segment, _, discounted_db_segment in basis.discounted_base_segments:
        segment_nar = max(0.0, discounted_db_segment - remaining_av)
        remaining_av = max(0.0, remaining_av - discounted_db_segment)
        segment_nars.append((segment, segment_nar))
    nar_by_coverage = {
        f"cov{index}": segment_nar
        for index, (_, segment_nar) in enumerate(segment_nars, start=1)
    }
    nar_corr = max(0.0, basis.discounted_db_corr - remaining_av)
    nar = sum(nar_by_coverage.values()) + nar_corr
    return NarAllocation(
        segment_nars=segment_nars,
        nar_by_coverage=nar_by_coverage,
        nar_cov1=nar_by_coverage.get("cov1", 0.0),
        nar_corr=nar_corr,
        nar=nar,
    )


def _maturity_deduction_result(basis: DeathBenefitBasis, nar: NarAllocation) -> DeductionResult:
    """Return the no-charge maturity-row deduction result."""
    return _charge_cease_deduction_result(basis, nar, 0.0)


def _charge_cease_deduction_result(
    basis: DeathBenefitBasis, nar: NarAllocation, mfee_charge: float,
) -> DeductionResult:
    """Deduction once COI, EPU, %-of-AV, benefit and rider charges have ceased: only the
    plan's scheduled monthly policy fee (schema MFEE) is still taken (0 at maturity).

    CyberLife keeps deducting the per-policy expense after the IMUL age-100 COI cease
    (1U143800 U0580868 / 1U144500 U0598462: MV_EXP 5.00, COI 0).
    """
    return DeductionResult(
        nar_av=basis.nar_av,
        standard_db=basis.standard_db,
        corridor_rate=basis.corridor_rate,
        gross_db=basis.gross_db,
        corr_amount=basis.corr_amount,
        db_by_coverage=basis.db_by_coverage,
        discounted_db_by_coverage=basis.discounted_db_by_coverage,
        discounted_db_cov1=basis.discounted_db_cov1,
        discounted_db_corr=basis.discounted_db_corr,
        discounted_db=basis.discounted_db,
        total_db=basis.gross_db,
        total_discounted_db=basis.discounted_db,
        nar_by_coverage=nar.nar_by_coverage,
        nar_cov1=nar.nar_cov1,
        nar_corr=nar.nar_corr,
        nar=nar.nar,
        total_nar=nar.nar,
        mfee_charge=mfee_charge,
        total_deduction=mfee_charge,
        av_after_deduction=basis.mAV - mfee_charge,
    )


def _calculate_coi_charges(
    nar: NarAllocation,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    rate_year: int,
    projection_date: date | None,
    bln_round_charge: bool,
) -> CoiChargeBreakdown:
    """Calculate base COI charges and ratchet-band override if applicable."""
    seg = policy.base_segment
    base_schedule = rates.segment_coi.get(seg.coverage_phase, rates.coi) if seg else rates.coi
    base_year = _coi_rate_year(seg, policy, projection_date, rate_year)
    adjusted_coi = _adjusted_coi_rate(
        _rate_from_schedule(base_schedule, base_year), seg, config,
        projection_date, round_5=True)
    rates_by_coverage, charges_by_coverage = {}, {}
    for index, (segment, segment_nar) in enumerate(nar.segment_nars, start=1):
        schedule = rates.coi if segment is None else rates.segment_coi.get(segment.coverage_phase, rates.coi)
        rate_year_i = _coi_rate_year(segment, policy, projection_date, rate_year)
        rate = _adjusted_coi_rate(
            _rate_from_schedule(schedule, rate_year_i), segment, config,
            projection_date, round_5=(index == 1))
        if _segment_charge_inactive(segment, projection_date):
            rate = 0.0
        charge = (segment_nar / PER_THOUSAND) * rate
        charges_by_coverage[f"cov{index}"] = _round_near(charge, 2) if bln_round_charge else charge
        rates_by_coverage[f"cov{index}"] = rate
    corridor_key = _corridor_coverage_key(nar.segment_nars, projection_date)
    rate_corr = rates_by_coverage[corridor_key] if corridor_key is not None else 0.0
    charge_corr = (nar.nar_corr / PER_THOUSAND) * rate_corr
    total = sum(charges_by_coverage.values()) + charge_corr
    result = CoiChargeBreakdown(
        rates_by_coverage=rates_by_coverage,
        charges_by_coverage=charges_by_coverage,
        rate_cov1=adjusted_coi,
        rate_corr=rate_corr,
        charge_cov1=charges_by_coverage.get("cov1", 0.0),
        charge_corr=charge_corr,
        charge_total=total,
    )
    return _apply_ratchet_if_needed(
        result, nar, policy, config, rates, rate_year, projection_date, bln_round_charge)


def _apply_ratchet_if_needed(
    result: CoiChargeBreakdown,
    nar: NarAllocation,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    rate_year: int,
    projection_date: date | None,
    bln_round_charge: bool,
) -> CoiChargeBreakdown:
    """Replace regular COI charges with ratchet-banded charges when configured."""
    if not (config.rachet_banding and getattr(rates, "band_break", 0.0) > 0):
        if bln_round_charge:
            result.charge_total = _round_near(result.charge_total, 2)
        return result
    rc = _ratchet_coi(
        nar.segment_nars, nar.nar_corr, rates, config, policy,
        projection_date, rate_year, bln_round_charge,
    )
    return CoiChargeBreakdown(
        rates_by_coverage=dict(rc.band1_rates),
        charges_by_coverage=rc.charges_by_coverage,
        rate_cov1=rc.cov1_band1_rate,
        rate_corr=rc.band1_rates["corr"],
        charge_cov1=rc.charges_by_coverage.get("cov1", 0.0),
        charge_corr=rc.charge_corr,
        charge_total=_round_near(rc.total, 2) if bln_round_charge else rc.total,
        ratchet_active=True,
        band_break=rates.band_break,
        band1_nar_by_coverage=rc.band1_nar,
        band2_nar_by_coverage=rc.band2_nar,
        band1_rates_by_coverage=rc.band1_rates,
        band2_rates_by_coverage=rc.band2_rates,
    )


def _calculate_expense_charges(
    basis: DeathBenefitBasis,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    rate_year: int,
    projection_date: date | None,
    bln_round_charge: bool,
) -> ExpenseChargeBreakdown:
    """Calculate EPU, monthly fee and AV charges."""
    epu = _calculate_epu_charges(
        basis.segments if basis.segments else [None],
        basis.face, policy, config, rates, rate_year, projection_date)
    mfee_charge = _monthly_fee_charge(rates, rate_year)
    av_charge = 0.0
    if config.poav_table != "0":
        av_charge = max(0.0, basis.mAV * get_rate(rates, "poav", rate_year))
    epu.mfee_charge = mfee_charge
    epu.av_charge = av_charge
    if bln_round_charge:
        epu.epu_charge = _round_near(epu.epu_charge, 2)
    return epu


def _calculate_epu_charges(
    epu_segments,
    face: float,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    rate_year: int,
    projection_date: date | None,
) -> ExpenseChargeBreakdown:
    """Calculate per-coverage EPU charges (schema EPU; none loaded = no charge).

    The schedule year discounts the most recent skipped-coverage period (see
    ``skipped_coverage.epu_schedule_year``); nothing else shifts with it."""
    result = ExpenseChargeBreakdown()
    reinstatement = policy.latest_skipped_coverage_period
    for index, segment in enumerate(epu_segments, start=1):
        schedule = rates.epu if segment is None else rates.segment_epu.get(segment.coverage_phase, rates.epu)
        epu_rate = _rate_from_schedule(schedule, epu_schedule_year(
            segment.issue_date if segment is not None else policy.issue_date,
            reinstatement, projection_date,
            _coverage_year(segment, projection_date, rate_year)))
        if _segment_charge_inactive(segment, projection_date):
            epu_rate = 0.0
        basis = _epu_segment_basis(segment, face, config)
        charge = _round_near((basis / PER_THOUSAND) * epu_rate, 2)
        result.epu_rates_by_coverage[f"cov{index}"] = epu_rate
        result.epu_charges_by_coverage[f"cov{index}"] = charge
    result.epu_rate = result.epu_rates_by_coverage.get("cov1", 0.0)
    result.epu_charge = sum(result.epu_charges_by_coverage.values())
    return result


def _epu_segment_basis(segment, face: float, config: PlancodeConfig) -> float:
    if config.sa_basis == SA_BASIS_ORIGINAL:
        return segment.original_face_amount if segment else face
    return segment.face_amount if segment else face


def _monthly_fee_charge(rates: IllustrationRates, rate_year: int) -> float:
    return get_rate(rates, "mfee", rate_year)


def _calculate_benefit_charges(
    base_deduction: float,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    rate_year: int,
    monthly_mtp: float,
    projection_date: date | None,
) -> BenefitChargeBreakdown:
    """Calculate riders, benefits and premium-waiver charges."""
    rider_result = _calculate_rider_charges(policy, config, rates, rate_year, projection_date)
    benefit_result = _calculate_policy_benefit_charges(
        base_deduction, rider_result.rider_charges, policy, config, rates,
        rate_year, monthly_mtp, projection_date)
    benefit_result.rider_charges = rider_result.rider_charges
    benefit_result.rider_amounts = rider_result.rider_amounts
    benefit_result.rider_rates = rider_result.rider_rates
    benefit_result.rider_charge_detail = rider_result.rider_charge_detail
    return benefit_result


def _calculate_rider_charges(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    rate_year: int,
    projection_date: date | None,
) -> BenefitChargeBreakdown:
    """Calculate rider charges active on the projection date."""
    result = BenefitChargeBreakdown()
    for rider in policy.riders:
        if not rider_active_on(rider, policy, projection_date):
            continue
        rider_key = rider.export_key
        rider_rate = _rider_charge_rate(rider, policy, rates, rate_year, projection_date)
        rider_rate = (
            rider_rate * (1.0 + config.table_rating_factor * (rider.table_rating or 0))
            + _trunc2((rider.flat_extra or 0.0) / MONTHS_PER_YEAR)
        )
        charge = _round_near(rider.units * rider_rate, 2)
        result.rider_amounts[rider_key] = rider.face_amount
        result.rider_rates[rider_key] = rider_rate
        result.rider_charge_detail[rider_key] = charge
        result.rider_charges += charge
    return result


def _rider_charge_rate(rider, policy, rates, rate_year, projection_date) -> float:
    rider_rates = rates.rider_rates.get(rider.export_key, [])
    if rider_rates:
        return _rate_from_schedule(
            rider_rates, _rider_rate_year(rider, policy, projection_date, rate_year))
    if rider.coi_rate is not None:
        return float(rider.coi_rate)
    if rider.premium_rate is not None:
        return float(rider.premium_rate)
    return 0.0


def _calculate_policy_benefit_charges(
    base_deduction: float,
    rider_charges: float,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    rate_year: int,
    monthly_mtp: float,
    projection_date: date | None,
) -> BenefitChargeBreakdown:
    """Calculate non-rider benefit charges, including premium waivers."""
    result = BenefitChargeBreakdown()
    non_pw_charges = 0.0
    detail_key_by_id = benefit_rate_keys(policy.benefits)
    for ben in sorted(policy.benefits, key=lambda benefit: (benefit.benefit_type or "") == "3"):
        if _skip_benefit_charge(ben, projection_date):
            continue
        detail_key = detail_key_by_id[id(ben)]
        charge_input = _benefit_charge_input(
            ben, detail_key, base_deduction + rider_charges + non_pw_charges,
            policy, config, rates, rate_year, monthly_mtp, projection_date)
        result.benefit_amounts[detail_key] = charge_input["amount"]
        result.benefit_rates[detail_key] = charge_input["rate"]
        result.benefit_charge_detail[detail_key] = charge_input["charge"]
        result.benefit_charges += charge_input["charge"]
        if (ben.benefit_type or "") == "3":
            result.pw_charge = charge_input["charge"]
        if (ben.benefit_type or "") not in ("3", "4"):
            non_pw_charges += charge_input["charge"]
    return result


def _skip_benefit_charge(ben, projection_date: date | None) -> bool:
    if not ben.is_active or (ben.benefit_type or "").startswith("#"):
        return True
    return bool(
        ben.pay_up_date is not None
        and projection_date is not None
        and projection_date >= ben.pay_up_date
    )


def _benefit_charge_input(
    ben,
    detail_key: str,
    monthly_deduction_basis: float,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    rate_year: int,
    monthly_mtp: float,
    projection_date: date | None,
) -> dict:
    """Return amount/rate/charge for one benefit."""
    ben_type = ben.benefit_type or ""
    raw_rate = _benefit_raw_rate(ben, detail_key, policy, rates, rate_year, projection_date)
    factor = ben.rating_factor if ben.rating_factor and ben.rating_factor > 0 else 1.0
    rate = raw_rate * factor
    if ben_type == "3":
        subtype = ben.benefit_subtype or ""
        amount = max(monthly_mtp, monthly_deduction_basis) if subtype in ("9", "#") else monthly_deduction_basis
        charge = rate * amount * benefit_charge_factor(policy.plancode, ben_type + subtype)
    elif ben_type == "4" and config.pwot_coi_basis in (2, 3):
        rate = raw_rate
        amount, charge = target_waiver_charge(policy, config, raw_rate, projection_date)
    else:
        amount = ben.benefit_amount
        charge = ben.units * rate * benefit_charge_factor(policy.plancode, ben_type + (ben.benefit_subtype or ""))
    return {"amount": amount, "rate": rate, "charge": _round_near(charge, 2)}


def _benefit_raw_rate(ben, detail_key: str, policy, rates, rate_year, projection_date) -> float:
    """Return the unadjusted benefit COI rate for the projection date."""
    ben_rates = rates.benefit_coi.get(detail_key, [])
    if ben_rates:
        return _rate_from_schedule(
            ben_rates, benefit_rate_year(ben, policy, projection_date, rate_year))
    if ben.coi_rate is not None:
        return float(ben.coi_rate)
    return 0.0


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
    corridor_rate: float | None = None,
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
        corridor_rate: CVAT minimum death benefit ratio; None uses the GPT ``CORR``.

    Returns:
        DeductionResult with all deduction-stage outputs.
    """
    basis = _build_death_benefit_basis(
        av_after_premium, policy, config, attained_age, premiums_to_date,
        projection_date, corridor_rate)
    nar = _allocate_nar(basis)
    # Before any COI lookup: an ISWL COI past its last loaded age raises (MissingRate).
    if _at_or_after_policy_maturity(policy, config, attained_age):
        return _maturity_deduction_result(basis, nar)
    if config.charges_ceased(attained_age):
        return _charge_cease_deduction_result(basis, nar, _monthly_fee_charge(rates, rate_year))

    coi = _calculate_coi_charges(
        nar, policy, config, rates, rate_year, projection_date,
        bln_round_charge,
    )
    expenses = _calculate_expense_charges(
        basis, policy, config, rates, rate_year, projection_date,
        bln_round_charge,
    )
    base_deduction = (
        coi.charge_total + expenses.epu_charge
        + expenses.mfee_charge + expenses.av_charge
    )
    benefits = (
        # ISWL benefit and rider premiums come out of the gross premium, not the AV.
        BenefitChargeBreakdown() if config.is_iswl else _calculate_benefit_charges(
            base_deduction, policy, config, rates, rate_year, monthly_mtp,
            projection_date,
        )
    )
    total_deduction = (
        base_deduction + benefits.benefit_charges + benefits.rider_charges
    )
    if bln_round_charge:
        total_deduction = _round_near(total_deduction, 2)
    return DeductionResult(
        nar_av=basis.nar_av,
        standard_db=basis.standard_db,
        corridor_rate=basis.corridor_rate,
        gross_db=basis.gross_db,
        corr_amount=basis.corr_amount,
        db_by_coverage=basis.db_by_coverage,
        discounted_db_by_coverage=basis.discounted_db_by_coverage,
        discounted_db_cov1=basis.discounted_db_cov1,
        discounted_db_corr=basis.discounted_db_corr,
        discounted_db=basis.discounted_db,
        total_db=basis.gross_db,
        total_discounted_db=basis.discounted_db,
        nar_by_coverage=nar.nar_by_coverage,
        nar_cov1=nar.nar_cov1,
        nar_corr=nar.nar_corr,
        nar=nar.nar,
        total_nar=nar.nar,
        coi_rates_by_coverage=coi.rates_by_coverage,
        coi_charges_by_coverage=coi.charges_by_coverage,
        coi_rate=coi.rate_cov1,
        coi_rate_corr=coi.rate_corr,
        coi_charge_cov1=coi.charge_cov1,
        coi_charge_corr=coi.charge_corr,
        coi_charge=coi.charge_total,
        total_coi_charge=coi.charge_total,
        ratchet_active=coi.ratchet_active,
        band_break=coi.band_break,
        coi_band1_nar_by_coverage=coi.band1_nar_by_coverage,
        coi_band2_nar_by_coverage=coi.band2_nar_by_coverage,
        coi_band1_rates_by_coverage=coi.band1_rates_by_coverage,
        coi_band2_rates_by_coverage=coi.band2_rates_by_coverage,
        epu_rate=expenses.epu_rate,
        epu_charge=expenses.epu_charge,
        epu_rates_by_coverage=expenses.epu_rates_by_coverage,
        epu_charges_by_coverage=expenses.epu_charges_by_coverage,
        mfee_charge=expenses.mfee_charge,
        av_charge=expenses.av_charge,
        pw_charge=benefits.pw_charge,
        benefit_charges=benefits.benefit_charges,
        benefit_amounts=benefits.benefit_amounts,
        benefit_rates=benefits.benefit_rates,
        benefit_charge_detail=benefits.benefit_charge_detail,
        rider_charges=benefits.rider_charges,
        rider_amounts=benefits.rider_amounts,
        rider_rates=benefits.rider_rates,
        rider_charge_detail=benefits.rider_charge_detail,
        total_deduction=total_deduction,
        av_after_deduction=basis.mAV - total_deduction,
    )
