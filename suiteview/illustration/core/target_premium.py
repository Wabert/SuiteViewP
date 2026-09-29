"""Minimum / Commission Target Premium (vMTP / vCTP) — RERUN CalcEngine JG / KQ.

Computes the annual target premiums from rates, exactly as RERUN does when
``vPolicyChangeIndicator`` fires (and as admin does at issue):

All returned headline premiums are annual dollars. Coverage, rider and benefit
rates are annual target rates per 1,000 or per unit according to the source
rate table; the monthly MTP used by the engine is ``TRUNC(annual / 12, 2)``.
Table-rating target rates are required when a table rating is active; ``None``
means unavailable, not zero. Waiver target rates 39/3# are stored as
percentages and converted to multipliers only in the calculation.

    per coverage segment (HW..HZ / JQ..JT):
        ROUND(SA·rate/1000, 2)
      + ROUND(tableRating·tblRate·SA/1000, 2)        (CTP caps tblRate at 6)
      + ROUND((12·TRUNC(flat/12,2))·SA/1000, 2)
    + benefit targets (CCV: rate·SA/1000; others: units·rate)
    + Stipulated Premium Waiver / PWoT (IK): units·pwstRate·(1 + factor·table)
    + Premium Waiver of Charges / PWoC (IV): pwRate·(target w/o PW, MTP basis)
      ·(1 + factor·table)
      — the PW component of vCTP is the SAME MTP-basis value, ROUNDed (KP=IV).

FFL products (plancode CompanySub = "FFL", RERUN sblnFFL) replace both waiver
targets with the "FFL Premium Waivers" basis calc (CalcEngine IW..JD):

    IW  vMin_Base       = Σcov currentCOIRate·SA/1000     (at the change month)
    IX  vMin_Base_Table = Σcov currentCOIRate·table·SA·factor/1000
    IY  vMin_Base_Flat  = TotalSA·flat1                   (RERUN as-is; no /1000, /12)
    IZ  PWoC MinBasis   = (Σbenefit + Σrider MTPs)/12 + IW + IX + IY + monthly fee
    JB  PWoC_MTP (IV)   = TRUNC(pwRate·IZ·(1 + factor·table), 2)
    JA  PWoT MinBasis   = Σcov MTPs + Σbenefit MTPs + Σrider MTPs + JB  (no CCV, no PWoT)
    JC  PWoT_wTable     = TRUNC(x/(1−x), 5),  x = pwstRate/100·(1 + table·factor)
    JD  PWoT_MTP (IK)   = TRUNC(JA·JC, 2)
    KE  PWoT CTP        = JC·vMTP                          (vs units·rate non-FFL)

    vMTP = MTP components + IV                       (IV at full precision)
    vCTP = CTP components + ROUND(IV, 2)
    vMonthlyMTP = TRUNC(vMTP/12, 2)                  (truncation happens at use)

Validated against the U0688012 fixture: computed vMTP/12 -> 150.13 (DB value)
and vCTP -> 2043.64 (DB value) exactly, and the face-change ratios match the
captured RERUN references (increase 1.7337, decrease 0.9832).

Rate sources (local rates.sqlite / UL_Rates):
    Select_RATE_MTP / Select_RATE_TBL1MTP / Select_RATE_CTP / Select_RATE_TBL1CTP
        keyed by (plancode, segment issue age, sex, rateclass, band)
    Select_RATE_BENMTP / Select_RATE_BENCTP
        keyed by (plancode, benefit key, POLICY issue age, sex, rateclass, band)

Waivers 39 / 3# store target rates as percentages (5.5 means 5.5%).
Convert those rates to multipliers for calculation only; retain the raw rate
in the detail snapshot. Other waiver units, including FFL 3F, are unchanged.

SA_Basis consolidates the workbook's target/EPU basis and target band lock.
OriginalSA locks MTP rates to each coverage's issue band. CTP always uses the
CURRENT total specified-amount band, as do unlocked CurrentSA MTP rates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Dict, Optional

from suiteview.core.band_rules import rider_bands_as_base
from suiteview.illustration.constants import (
    MONTHS_PER_YEAR,
    PER_THOUSAND,
    RATE_CODE_TABLE,
    SA_BASIS_ORIGINAL,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    IllustrationPolicyData,
    rider_active_on,
)

# Child Term Rider target — RERUN Rates_Control hardcodes 7.80/unit/yr
# (HA12/HB12); no MTP/CTP table rows exist for CTR plancodes in UL_Rates.
CTR_TARGET_RATE = 7.80
# "Uses CTR with MTP=0" (Rates_Control GZ19:GZ34): base plancodes whose CTR
# contributes no MTP (the CTP side stays 7.80).
CTR_MTP_ZERO_PLANCODES = frozenset({
    "1U145700", "1U146600", "1U147200", "1U147600", "1U146000",
    "1U146700", "1U147300", "1U147900", "1U148000", "1U148100",
})


def _round2(value: float) -> float:
    return float(Decimal(f"{value:.12f}").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _trunc2(value: float) -> float:
    return float(Decimal(f"{value:.12f}").quantize(Decimal("0.01"), rounding=ROUND_DOWN))


def truncate_monthly_mtp(value: float) -> float:
    """Truncate monthly MTP without losing a cent to binary float noise."""
    return _trunc2(value)


def _trunc5(value: float) -> float:
    return float(Decimal(f"{value:.12f}").quantize(Decimal("0.00001"), rounding=ROUND_DOWN))


def _active(cease_date: Optional[date], as_of: Optional[date]) -> bool:
    if cease_date is None or as_of is None:
        return True
    return as_of <= cease_date


def _years_since(start: Optional[date], as_of: Optional[date]) -> int:
    """1-based year duration at ``as_of`` (year 1 = first policy/coverage year)."""
    if start is None or as_of is None:
        return 1
    years = as_of.year - start.year
    if (as_of.month, as_of.day) < (start.month, start.day):
        years -= 1
    return max(1, years + 1)


def target_actives_signature(
    policy: IllustrationPolicyData, as_of: Optional[date]
) -> tuple:
    """Hashable snapshot of every date-gated component of the target premiums.

    Two months with equal signatures produce identical compute_target_premiums
    results for an unchanged coverage state, so the engine only recomputes the
    MTP/CTP detail when this changes (a rider/benefit/substandard charge
    crossing its cease date) or when a policy change moves the coverage.
    """
    seg_flags = tuple(
        (
            s.coverage_phase,
            s.table_rating > 0 and _active(s.table_cease_date, as_of),
            bool(s.flat_extra) and s.flat_extra > 0 and _active(s.flat_cease_date, as_of),
        )
        for s in policy.segments
    )
    ben_keys = tuple(sorted(
        (ben.benefit_type or "") + (ben.benefit_subtype or "")
        for ben in policy.benefits
        if ben.is_active
        and not (ben.benefit_type or "").startswith("#")
        and not (ben.pay_up_date is not None and as_of is not None and as_of >= ben.pay_up_date)
    ))
    rider_keys = tuple(sorted(
        rider.export_key
        for rider in policy.riders
        if rider.is_active and rider.plancode and rider_active_on(rider, policy, as_of)
    ))
    return (seg_flags, ben_keys, rider_keys)


def _schedule_rate(schedule, index: int) -> float:
    """Rate array lookup — arrays are 1-indexed by duration, last value carries."""
    if not schedule or len(schedule) < 2:
        return 0.0
    if index < 1:
        index = 1
    if index >= len(schedule):
        return float(schedule[-1] or 0.0)
    return float(schedule[index] or 0.0)


@dataclass
class TargetPremiumResult:
    """Annual target premiums plus per-component detail for auditing."""

    mtp_annual: float = 0.0
    ctp_annual: float = 0.0
    mtp_by_coverage: Dict[int, float] = field(default_factory=dict)
    ctp_by_coverage: Dict[int, float] = field(default_factory=dict)
    mtp_benefits: Dict[str, float] = field(default_factory=dict)
    ctp_benefits: Dict[str, float] = field(default_factory=dict)
    # Rider targets keyed by RiderInfo.export_key (CTR hardcoded 7.80/unit/yr;
    # spouse/other term riders from their own plancode's MTP/CTP tables).
    mtp_riders: Dict[str, float] = field(default_factory=dict)
    ctp_riders: Dict[str, float] = field(default_factory=dict)
    pw_component: float = 0.0   # IV — full precision, MTP basis
    target_band: int = 0

    # Rate detail for the Values tab (CalcEngine HO..HV / JI..JP / IU).
    mtp_rates_by_coverage: Dict[int, float] = field(default_factory=dict)
    mtp_tbl_rates_by_coverage: Dict[int, float] = field(default_factory=dict)
    ctp_rates_by_coverage: Dict[int, float] = field(default_factory=dict)
    ctp_tbl_rates_by_coverage: Dict[int, float] = field(default_factory=dict)
    pw_rate: float = 0.0        # PW MTPR — raw database rate (percent for 39 / 3#)
    mtp_wo_pw: float = 0.0      # IT
    ctp_wo_pw: float = 0.0      # KN basis (cov + benefit CTPs before PW)

    # Stipulated Premium Waiver / PWoT (benefit type 4).
    pwst_rate: float = 0.0          # IJ — PWSTP MTPR
    pwst_ctp_rate: float = 0.0      # KD — PWSTP CTPR (non-FFL)
    pwst_component: float = 0.0     # IK — PWoT MTP
    pwst_ctp_component: float = 0.0  # KE — PWoT CTP
    # Joint survivor plans: CyberLife calculates MTP/CTP with a VP/MS target
    # model that is not available, so the stored record targets are held.
    held_at_record: bool = False

    # FFL premium waiver bases (CalcEngine IW..JD) — zero for non-FFL products.
    ffl_min_base: float = 0.0       # IW
    ffl_min_base_table: float = 0.0  # IX
    ffl_min_base_flat: float = 0.0  # IY
    ffl_pwoc_basis: float = 0.0     # IZ
    ffl_pwot_basis: float = 0.0     # JA
    ffl_pwot_factor: float = 0.0    # JC

    @property
    def mtp_monthly(self) -> float:
        """vMonthlyMTP = TRUNC(vMTP/12, 2)."""
        return truncate_monthly_mtp(self.mtp_annual / MONTHS_PER_YEAR)


@dataclass
class CoverageTargetTotals:
    """Coverage target totals and the current specified-amount band."""

    mtp_sum: float = 0.0
    ctp_sum: float = 0.0
    current_band: int = 0


@dataclass
class BenefitTargetWork:
    """Intermediate benefit and waiver target components."""

    pw_rate: float = 0.0
    pw_multiplier: float = 0.0
    pwst_rate: float = 0.0
    pwst_ctp_rate: float = 0.0
    pwst_units: float = 0.0
    pwst_key: str = ""
    mtp_generic: float = 0.0
    ctp_generic: float = 0.0
    mtp_ccv: float = 0.0
    ctp_ccv: float = 0.0


@dataclass
class RiderTargetTotals:
    """Rider target totals."""

    mtp_sum: float = 0.0
    ctp_sum: float = 0.0


def _segment_target(
    sa: float,
    rate: float,
    tbl_rate: float,
    table_rating: int,
    flat_extra: float,
    cap_tbl_rate: bool,
) -> float:
    """One coverage segment's target premium (CalcEngine HW / JQ).

    The substandard term multiplies the table RATING (e.g. 2 for Table B) by the
    per-table rate from TBL1MTP/TBL1CTP — the plancode's 25% factor is built into
    that rate, not applied here. CTP caps the per-table rate at 6 (JQ MIN(6,...)).
    """
    tbl = min(6.0, tbl_rate) if cap_tbl_rate else tbl_rate
    flat_monthly = _trunc2(flat_extra / MONTHS_PER_YEAR) if flat_extra else 0.0
    return (
        _round2(sa * rate / PER_THOUSAND)
        + _round2(table_rating * tbl * sa / PER_THOUSAND)
        + _round2(MONTHS_PER_YEAR * flat_monthly * sa / PER_THOUSAND)
    )


def _ffl_min_base(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates_db,
    current_band: int,
    as_of: Optional[date],
) -> tuple[float, float]:
    """FFL vMin_Base / vMin_Base_Table (CalcEngine IW / IX).

    Current-scale COI select rate per coverage at its duration for the as-of
    month, applied to the specified amount. RERUN freezes IW between policy
    changes; we recompute per call, which matches because targets are only
    computed at issue/inforce and on policy changes.
    """
    iw = 0.0
    ix = 0.0
    for seg in policy.segments:
        if seg.face_amount <= 0:
            continue
        cov_year = _years_since(seg.issue_date, as_of)
        if seg.issue_age + cov_year - 1 >= config.premium_cease_age:
            continue
        # PolicyRates EH..EJ band: original band only when dynamic banding is
        # off ("0"), else the current total-SA band (FD).
        band = seg.original_band if config.dynamic_banding == 0 else current_band
        schedule = rates_db.get_rates(
            "COI", policy.plancode, seg.issue_age, seg.rate_sex,
            seg.rate_class, scale=1, band=band,
        ) or []
        rate = _schedule_rate(schedule, cov_year)
        table = (
            seg.table_rating
            if seg.table_rating > 0 and _active(seg.table_cease_date, as_of)
            else 0
        )
        iw += rate * seg.face_amount / PER_THOUSAND
        ix += rate * table * seg.face_amount * config.table_rating_factor / PER_THOUSAND
    return iw, ix


def _ffl_monthly_fee(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates_db,
    current_band: int,
    as_of: Optional[date],
) -> float:
    """FFL monthly expense fee term of the PWoC basis (PolicyRates FE)."""
    policy_year = _years_since(policy.issue_date, as_of)
    if policy.issue_age + policy_year - 1 >= config.premium_cease_age:
        return 0.0
    if config.mfee == RATE_CODE_TABLE:
        base = policy.base_segment
        schedule = rates_db.get_rates(
            "MFEE", policy.plancode, base.issue_age, base.rate_sex,
            base.rate_class, scale=1, band=current_band,
        ) or []
        return _schedule_rate(schedule, policy_year)
    try:
        return float(config.mfee)
    except (ValueError, TypeError):
        return 0.0


def _current_target_band(policy: IllustrationPolicyData, rates_db) -> int:
    base = policy.base_segment
    current_band = rates_db.get_band(
        policy.plancode,
        policy.band_specified_amount,
        issue_date=policy.issue_date,
    )
    return int(current_band) if current_band is not None else base.band


def _add_coverage_targets(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates_db,
    result: TargetPremiumResult,
    as_of: Optional[date],
) -> CoverageTargetTotals:
    from suiteview.illustration.core.rate_loader import RateLookupError

    totals = CoverageTargetTotals(current_band=_current_target_band(policy, rates_db))
    result.target_band = totals.current_band
    for seg in policy.segments:
        if seg.face_amount <= 0:
            continue
        mtp_band = (
            seg.original_band if config.sa_basis == SA_BASIS_ORIGINAL
            else totals.current_band
        )
        sa = (
            seg.original_face_amount if config.sa_basis == SA_BASIS_ORIGINAL
            else seg.face_amount
        )
        table = (
            seg.table_rating
            if seg.table_rating > 0 and _active(seg.table_cease_date, as_of)
            else 0
        )
        flat = (
            seg.flat_extra
            if seg.flat_extra and seg.flat_extra > 0
            and _active(seg.flat_cease_date, as_of)
            else 0.0
        )
        args = (policy.plancode, seg.issue_age, seg.rate_sex, seg.rate_class)
        mtp_rate = rates_db.get_mtp(*args, mtp_band) or 0.0
        mtp_tbl_rate = rates_db.get_tbl1_mtp(*args, mtp_band)
        ctp_rate = rates_db.get_ctp(*args, totals.current_band) or 0.0
        ctp_tbl_rate = rates_db.get_tbl1_ctp(*args, totals.current_band)
        _require_table_target_rates(
            policy, seg, table, mtp_tbl_rate, ctp_tbl_rate, mtp_band,
            totals.current_band, RateLookupError,
        )
        mtp_tbl_rate = mtp_tbl_rate if mtp_tbl_rate is not None else 0.0
        ctp_tbl_rate = ctp_tbl_rate if ctp_tbl_rate is not None else 0.0
        mtp_val = _segment_target(
            sa, mtp_rate, mtp_tbl_rate, table, flat, cap_tbl_rate=False,
        )
        ctp_val = _segment_target(
            sa, ctp_rate, ctp_tbl_rate, table, flat, cap_tbl_rate=True,
        )
        phase = seg.coverage_phase
        result.mtp_rates_by_coverage[phase] = mtp_rate
        result.mtp_tbl_rates_by_coverage[phase] = mtp_tbl_rate
        result.ctp_rates_by_coverage[phase] = ctp_rate
        result.ctp_tbl_rates_by_coverage[phase] = ctp_tbl_rate
        result.mtp_by_coverage[phase] = mtp_val
        result.ctp_by_coverage[phase] = ctp_val
        totals.mtp_sum += mtp_val
        totals.ctp_sum += ctp_val
    return totals


def _require_table_target_rates(
    policy: IllustrationPolicyData,
    seg,
    table: int,
    mtp_tbl_rate: Optional[float],
    ctp_tbl_rate: Optional[float],
    mtp_band: int,
    current_band: int,
    error_type,
) -> None:
    for name, value, band in (
        ("TBL1MTP", mtp_tbl_rate, mtp_band),
        ("TBL1CTP", ctp_tbl_rate, current_band),
    ):
        if table > 0 and value is None:
            raise error_type(
                f"Required {name} rate is unavailable for plancode "
                f"{policy.plancode}, coverage phase {seg.coverage_phase}, "
                f"issue age {seg.issue_age}, sex {seg.rate_sex}, "
                f"rate class {seg.rate_class}, band {band}, table rating {table}."
            )


def _add_benefit_targets(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates_db,
    result: TargetPremiumResult,
    current_band: int,
    as_of: Optional[date],
) -> BenefitTargetWork:
    base = policy.base_segment
    total_face = policy.total_face
    ben_band = base.original_band if config.sa_basis == SA_BASIS_ORIGINAL else current_band
    work = BenefitTargetWork()
    for ben in policy.benefits:
        ben_type = ben.benefit_type or ""
        if not _benefit_counts_for_target(ben, ben_type, as_of):
            continue
        ben_key = ben_type + (ben.benefit_subtype or "")
        ben_args = (
            policy.plancode, policy.issue_age, base.rate_sex, base.rate_class,
        )
        ben_mtp_rate = rates_db.get_ben_mtp(*ben_args, ben_band, ben_key) or 0.0
        ben_ctp_rate = rates_db.get_ben_ctp(*ben_args, current_band, ben_key) or 0.0
        if ben_type == "3":
            work.pw_rate = ben_mtp_rate
            work.pw_multiplier = (
                ben_mtp_rate / 100.0 if ben_key in ("39", "3#") else ben_mtp_rate
            )
            continue
        if ben_type == "4":
            work.pwst_rate = ben_mtp_rate
            work.pwst_ctp_rate = ben_ctp_rate
            work.pwst_units = ben.units or 0.0
            work.pwst_key = ben_key
            continue
        _add_nonwaiver_benefit_target(
            work, result, ben, ben_type, ben_key, ben_mtp_rate,
            ben_ctp_rate, total_face,
        )
    return work


def _benefit_counts_for_target(ben, ben_type: str, as_of: Optional[date]) -> bool:
    if not ben.is_active or ben_type.startswith("#"):
        return False
    return not (
        ben.pay_up_date is not None and as_of is not None and as_of >= ben.pay_up_date
    )


def _add_nonwaiver_benefit_target(
    work: BenefitTargetWork,
    result: TargetPremiumResult,
    ben,
    ben_type: str,
    ben_key: str,
    ben_mtp_rate: float,
    ben_ctp_rate: float,
    total_face: float,
) -> None:
    if ben_type == "A":
        mtp_val = ben_mtp_rate * total_face / PER_THOUSAND
        ctp_val = ben_ctp_rate * total_face / PER_THOUSAND
        work.mtp_ccv += mtp_val
        work.ctp_ccv += ctp_val
    else:
        mtp_val = (ben.units or 0.0) * ben_mtp_rate
        ctp_val = (ben.units or 0.0) * ben_ctp_rate
        work.mtp_generic += mtp_val
        work.ctp_generic += ctp_val
    result.mtp_benefits[ben_key] = mtp_val
    result.ctp_benefits[ben_key] = ctp_val


def _add_rider_targets(
    policy: IllustrationPolicyData,
    rates_db,
    result: TargetPremiumResult,
    current_band: int,
    as_of: Optional[date],
) -> RiderTargetTotals:
    totals = RiderTargetTotals()
    for rider in policy.riders:
        if not rider.is_active or not rider.plancode:
            continue
        if not rider_active_on(rider, policy, as_of):
            continue
        units = rider.units or 0.0
        if (rider.cov_type or "").upper() == "CTR":
            mtp_rate_r = (
                0.0 if policy.plancode in CTR_MTP_ZERO_PLANCODES else CTR_TARGET_RATE
            )
            ctp_rate_r = CTR_TARGET_RATE
        else:
            if rider_bands_as_base(rider.plancode):
                r_band = int(current_band)
            else:
                r_band = rates_db.get_band(rider.plancode, rider.face_amount)
                r_band = int(r_band) if r_band is not None else rider.band
            r_args = (
                rider.plancode, rider.issue_age, rider.rate_sex,
                rider.rate_class, r_band,
            )
            mtp_rate_r = rates_db.get_mtp(*r_args) or 0.0
            ctp_rate_r = rates_db.get_ctp(*r_args) or 0.0
        mtp_val = units * mtp_rate_r
        ctp_val = units * ctp_rate_r
        if not mtp_val and not ctp_val:
            continue
        result.mtp_riders[rider.export_key] = mtp_val
        result.ctp_riders[rider.export_key] = ctp_val
        totals.mtp_sum += mtp_val
        totals.ctp_sum += ctp_val
    return totals


def _finish_waiver_targets(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates_db,
    result: TargetPremiumResult,
    coverage: CoverageTargetTotals,
    benefits: BenefitTargetWork,
    riders: RiderTargetTotals,
    as_of: Optional[date],
) -> None:
    base = policy.base_segment
    total_face = policy.total_face
    base_table = (
        base.table_rating
        if base.table_rating > 0 and _active(base.table_cease_date, as_of)
        else 0
    )
    factor = config.table_rating_factor
    pwst_active = bool(benefits.pwst_key)
    pw_component = 0.0
    pwst_component = 0.0
    pwst_ctp_component = 0.0

    if config.is_ffl:
        pw_component, pwst_component = _finish_ffl_waivers(
            policy, config, rates_db, result, coverage.current_band, benefits,
            riders, base_table, total_face, as_of,
        )
    elif pwst_active:
        pwst_component = (
            benefits.pwst_units * benefits.pwst_rate * (1.0 + factor * base_table)
        )
        pwst_ctp_component = (
            benefits.pwst_units * benefits.pwst_ctp_rate
            * (1.0 + factor * base_table)
        )

    mtp_wo_pw = (
        coverage.mtp_sum + benefits.mtp_generic + benefits.mtp_ccv
        + riders.mtp_sum + pwst_component
    )
    if not config.is_ffl and benefits.pw_rate > 0.0:
        pw_component = benefits.pw_multiplier * mtp_wo_pw * (1.0 + factor * base_table)
    result.mtp_annual = mtp_wo_pw + pw_component
    if config.is_ffl and pwst_active:
        pwst_ctp_component = result.ffl_pwot_factor * result.mtp_annual
    ctp_wo_pw = (
        coverage.ctp_sum + benefits.ctp_generic + benefits.ctp_ccv
        + riders.ctp_sum + pwst_ctp_component
    )
    if benefits.pw_rate > 0.0:
        result.mtp_benefits["39"] = pw_component
        result.ctp_benefits["39"] = _round2(pw_component)
    if pwst_active:
        result.mtp_benefits[benefits.pwst_key] = pwst_component
        result.ctp_benefits[benefits.pwst_key] = pwst_ctp_component

    result.pw_rate = benefits.pw_rate
    result.pwst_rate = benefits.pwst_rate
    result.pwst_ctp_rate = benefits.pwst_ctp_rate
    result.pwst_component = pwst_component
    result.pwst_ctp_component = pwst_ctp_component
    result.mtp_wo_pw = mtp_wo_pw
    result.ctp_wo_pw = ctp_wo_pw
    result.pw_component = pw_component
    result.ctp_annual = ctp_wo_pw + _round2(pw_component)


def _finish_ffl_waivers(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates_db,
    result: TargetPremiumResult,
    current_band: int,
    benefits: BenefitTargetWork,
    riders: RiderTargetTotals,
    base_table: int,
    total_face: float,
    as_of: Optional[date],
) -> tuple[float, float]:
    base = policy.base_segment
    factor = config.table_rating_factor
    iw, ix = _ffl_min_base(policy, config, rates_db, current_band, as_of)
    base_flat = (
        base.flat_extra
        if base.flat_extra and base.flat_extra > 0
        and _active(base.flat_cease_date, as_of)
        else 0.0
    )
    iy = total_face * base_flat
    mfee_monthly = _ffl_monthly_fee(policy, config, rates_db, current_band, as_of)
    pwoc_basis = (
        (benefits.mtp_generic + riders.mtp_sum) / MONTHS_PER_YEAR
        + iw + ix + iy + mfee_monthly
    )
    pw_component = 0.0
    if benefits.pw_rate > 0.0:
        pw_component = _trunc2(
            benefits.pw_multiplier * pwoc_basis * (1.0 + factor * base_table)
        )
    pwot_basis = (
        sum(result.mtp_by_coverage.values())
        + benefits.mtp_generic + riders.mtp_sum + pw_component
    )
    pwot_factor = 0.0
    pwst_component = 0.0
    if benefits.pwst_key:
        x = benefits.pwst_rate / 100.0 * (1.0 + base_table * factor)
        if x < 1.0:
            pwot_factor = _trunc5(x / (1.0 - x))
        pwst_component = _trunc2(pwot_basis * pwot_factor)
    result.ffl_min_base = iw
    result.ffl_min_base_table = ix
    result.ffl_min_base_flat = iy
    result.ffl_pwoc_basis = pwoc_basis
    result.ffl_pwot_basis = pwot_basis
    result.ffl_pwot_factor = pwot_factor
    return pw_component, pwst_component


def compute_target_premiums(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    as_of: Optional[date] = None,
) -> TargetPremiumResult:
    """Compute annual vMTP / vCTP from rates for the policy's CURRENT coverage state.

    Call after mutating segments for a policy change to get the recomputed
    targets (RERUN recomputes when vPolicyChangeIndicator fires). Reads the
    rates DB (cached at the Rates class level); works offline under
    SUITEVIEW_LOCAL_DATA.
    """
    from suiteview.core.rates import Rates

    rates_db = Rates()
    result = TargetPremiumResult()
    if not policy.segments:
        return result
    if policy.is_joint_survivor:
        # VP/MS targets: hold the record values (policy.mtp is monthly, ctp annual).
        result.mtp_annual = float(policy.mtp or 0.0) * 12.0
        result.ctp_annual = float(policy.ctp or 0.0)
        result.held_at_record = True
        return result

    coverage = _add_coverage_targets(policy, config, rates_db, result, as_of)
    current_band = coverage.current_band
    benefits = _add_benefit_targets(
        policy, config, rates_db, result, current_band, as_of
    )
    riders = _add_rider_targets(policy, rates_db, result, current_band, as_of)
    _finish_waiver_targets(
        policy, config, rates_db, result, coverage, benefits, riders, as_of
    )
    return result


def build_target_detail_snapshots(
    policy: IllustrationPolicyData,
    result: TargetPremiumResult,
) -> tuple[Dict[str, object], Dict[str, object]]:
    """MTP / CTP per-component snapshots keyed by the RERUN display names.

    Mirrors CalcEngine HO..JG (MTP) and JI..KQ (CTP). Every base coverage
    segment gets its own Cov n slot (same convention as the Monthly Deduction
    group, which lists all segments); APB is not modeled, so its slots stay 0.
    Each active rider gets its own MTP/CTP column keyed by its export key.
    Benefit slots: PW = type 3 (PWoC), PWSTP = type 4 (PWoT), GIR/GIO =
    type+subtype 76, CCV = type A; other unmapped benefit targets land in
    "Other Benefits" so nothing silently disappears.
    """
    segments = sorted(
        (s for s in policy.segments if getattr(s, "is_base", True)),
        key=lambda s: s.coverage_phase,
    )
    mtp: Dict[str, object] = {}
    ctp: Dict[str, object] = {}
    # One slot per base coverage segment (mirrors the Monthly Deduction group,
    # which lists every segment); always at least Cov 1 even when the policy
    # carries no explicit segments.
    for index in range(1, max(len(segments), 1) + 1):
        seg = segments[index - 1] if index - 1 < len(segments) else None
        phase = seg.coverage_phase if seg else None
        mtp[f"MTP Rate Cov {index}"] = result.mtp_rates_by_coverage.get(phase, 0.0)
        mtp[f"MTP Rate Cov {index} Tbl"] = result.mtp_tbl_rates_by_coverage.get(phase, 0.0)
        mtp[f"MTP Cov {index}"] = result.mtp_by_coverage.get(phase, 0.0)
        ctp[f"CTP Rate Cov {index}"] = result.ctp_rates_by_coverage.get(phase, 0.0)
        ctp[f"CTP Rate Cov {index} Tbl"] = result.ctp_tbl_rates_by_coverage.get(phase, 0.0)
        ctp[f"CTP Cov {index}"] = result.ctp_by_coverage.get(phase, 0.0)
    mtp["MTP APB"] = 0.0
    ctp["CTP APB"] = 0.0

    ccv_keys = {k for k in result.mtp_benefits if k.startswith("A")}
    named = {"39": "PW", "76": "GIR"}
    def _ben(values: Dict[str, float], slot: str) -> float:
        if slot == "CCV":
            return sum(values.get(k, 0.0) for k in ccv_keys)
        return sum(v for k, v in values.items() if named.get(k) == slot)
    for label, slot in (("CCV", "CCV"), ("GIR", "GIR")):
        mtp[f"{label} MTP"] = _ben(result.mtp_benefits, slot)
        ctp[f"{label} CTP"] = _ben(result.ctp_benefits, slot)
    other_keys = [
        k for k in result.mtp_benefits
        if k not in named and k not in ccv_keys and not k.startswith("4")
    ]
    mtp["Other Benefits MTP"] = sum(result.mtp_benefits[k] for k in other_keys)
    ctp["Other Benefits CTP"] = sum(result.ctp_benefits.get(k, 0.0) for k in other_keys)
    # Per-rider targets (IG..II analog — CTR/STR, spouse term riders). One
    # column per rider so each is visible, not rolled into a single sum.
    for key, value in result.mtp_riders.items():
        mtp[f"MTP Rider {key.upper()}"] = value
    for key, value in result.ctp_riders.items():
        ctp[f"CTP Rider {key.upper()}"] = value

    mtp["PWSTP MTPR"] = result.pwst_rate          # IJ
    mtp["PWSTP MTP"] = result.pwst_component      # IK
    ctp["PWSTP CTP"] = result.pwst_ctp_component  # KE
    if result.ffl_pwoc_basis or result.ffl_pwot_basis:
        # FFL Premium Waivers section (IW..JD) — shown only for FFL products.
        # These MTP intermediates feed the PWoC/PWoT waiver targets.
        mtp["Min_Base"] = result.ffl_min_base              # IW
        mtp["Min_Base_Table"] = result.ffl_min_base_table  # IX
        mtp["Min_Base_Flat"] = result.ffl_min_base_flat    # IY
        mtp["PWoC_MinBasis"] = result.ffl_pwoc_basis       # IZ
        mtp["PWoT_MinBasis"] = result.ffl_pwot_basis       # JA
        mtp["FFL PWoT Factor"] = result.ffl_pwot_factor    # JC

    mtp["MTP w/o PW"] = result.mtp_wo_pw          # IT
    mtp["PW MTPR"] = result.pw_rate               # IU
    mtp["PW MTP"] = result.pw_component           # IV
    mtp["vMTP"] = result.mtp_annual               # JG
    ctp["CTP w/o PW"] = result.ctp_wo_pw          # KN basis
    ctp["CTP PW"] = _round2(result.pw_component)  # KP = ROUND(IV, 2)
    ctp["vCTP"] = result.ctp_annual               # KQ
    ctp["Target Band"] = result.target_band
    return mtp, ctp


def floor_monthly_cent(value: float) -> float:
    """RERUN's monthly-normalized annual floor: INT(x/12*100)*12/100.

    Floors an annual amount so the monthly twelfth is an exact cent amount.
    Decimal arithmetic — binary floats put already-exact values like 52004.28
    a hair below their cent boundary and a raw floor() drops a cent.
    """
    monthly_cents = (Decimal(f"{value:.10f}") * 100 / 12).to_integral_value(rounding=ROUND_FLOOR)
    return float(monthly_cents * 12) / 100.0
