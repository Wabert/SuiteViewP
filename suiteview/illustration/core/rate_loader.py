"""Load projection rate schedules for an IllustrationPolicyData basis.

Rate loading is intentionally a copy/read boundary:

* `load_rates` does not project; it resolves the rate schedules the engine will
  read for the supplied policy/config basis.
* Band initialization is the only policy mutation here. Issue and rollback
  scenarios need their edited starting bands resolved before schedule lookup.
* Current, guaranteed and guideline runs differ only by the explicit COI and
  expense scale arguments documented on `load_rates`.
* Missing required COI/shadow schedules and missing BENCOI schedules for
  chargeable benefits raise `RateLookupError`; optional rider schedules remain
  empty so the validation layer can report them.
* UL/IUL rates come from UL_Rates schema ``rates`` through `ULRates`; ISWL through
  `iswl_rates.load_iswl_rates`. EPU, MFEE and the premium loads are always the schema
  rates (none loaded = no charge).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from suiteview.core.band_rules import rider_bands_as_base
from suiteview.core.joint_survivor_coi import JointBasis, load_joint_basis
from suiteview.illustration.core.poav_rates import load_poav_schedule
from suiteview.illustration.core.ul_rates import SHADOW, ULRates
from suiteview.illustration.models.policy_data import (
    IllustrationPolicyData,
    benefit_rate_issue_age,
    benefit_rate_keys,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig


PREFERRED_RATECLASS_FALLBACKS = {
    "R": "N",
    "P": "N",
    "T": "N",
    "Q": "S",
}


CCV_BENEFIT_TYPE = "A"
_RATE_MATCH_TOLERANCE = 1e-6


class RateLookupError(RuntimeError):
    """A required illustration rate schedule could not be found."""


class MissingRate:
    """A schedule year whose rate is not loaded (e.g. an IAF that ends before maturity).

    Kept in place so the schedule still runs to maturity, but any use as a number raises
    ``RateLookupError`` naming the year: the current month can calculate while a
    projection that reaches the year stops loudly, never extrapolating or charging 0.
    """

    __slots__ = ("message",)

    def __init__(self, message: str):
        self.message = message

    def _fail(self, *_args):
        raise RateLookupError(self.message)

    __float__ = __int__ = __index__ = __round__ = __neg__ = __abs__ = _fail
    __add__ = __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = _fail
    __truediv__ = __rtruediv__ = __floordiv__ = __rfloordiv__ = __pow__ = __rpow__ = _fail
    __lt__ = __le__ = __gt__ = __ge__ = _fail

    def __bool__(self) -> bool:
        return True

    def __repr__(self) -> str:
        return f"MissingRate({self.message!r})"


# Benefit types that always carry a monthly COI charge. Others (A, V, U, ...)
# are informational and legitimately have no BENCOI schedule.
CHARGEABLE_BENEFIT_TYPES = frozenset({"1", "2", "3", "4", "7"})
# A benefit constructed at zero premium: $0 in every duration.
ZERO_PREMIUM_SCHEDULE = (None, 0.0)


@dataclass(frozen=True)
class BenefitRateOverride:
    """A benefit COI schedule replaced by the rate stored on the policy record.

    ``database_rate`` is the UL_Rates BENCOI rate for the benefit's current
    duration under ``rate_class``; ``policy_rate`` is the LH_SPM_BNF rate the
    illustration charges instead, level for every duration.
    """

    schedule_key: str
    database_rate: float
    policy_rate: float
    rate_class: str


def load_coverage_coi_rates(
    rates_db: ULRates,
    *,
    plancode: str,
    issue_age: int,
    sex: str,
    rateclass: str,
    scale,
    band: int,
    issue_date=None,
) -> List:
    """Load COI rates, applying the approved preferred-class fallback.

    ``issue_date`` is the coverage issue date: current COI scales are calendar
    dated, so each coverage year reads the scale in effect on its start."""
    requested_class = (rateclass or "").strip().upper()
    lookup_classes = [requested_class]
    fallback_class = PREFERRED_RATECLASS_FALLBACKS.get(requested_class)
    if fallback_class is not None:
        lookup_classes.append(fallback_class)

    for lookup_class in lookup_classes:
        schedule = rates_db.get_rates(
            "COI",
            plancode,
            issue_age,
            sex,
            lookup_class,
            scale=scale,
            band=band,
            issue_date=issue_date,
        )
        if schedule:
            return schedule

    attempted = " then ".join(
        f"rate class {lookup_class or '<blank>'}" for lookup_class in lookup_classes
    )
    scale_text = "S (shadow account)" if scale == SHADOW else scale
    source = (
        "" if rates_db.is_loaded(plancode)
        else f" Plancode {plancode or '<blank>'} is not loaded in UL_Rates schema rates."
    )
    raise RateLookupError(
        "Required COI rate schedule was not found. "
        f"Lookup: plancode {plancode or '<blank>'}, issue age {issue_age}, "
        f"sex {sex or '<blank>'}, {attempted}, band {band}, scale {scale_text}.{source}"
    )


def load_segment_coi(
    rates_db: ULRates, plancode: str, segment, *, scale: int, band: int,
    joint_bases: Optional[Dict[int, JointBasis]] = None,
) -> List:
    """A base segment's COI schedule: the blended JointCOI for joint survivor
    phases, otherwise the plan's IAF COI (with the preferred-class fallback).

    ``joint_bases`` (``IllustrationRates.segment_joint``) receives a joint
    phase's basis, the year-by-year detail behind its schedule; a single-life
    phase's entry is removed.
    """
    if segment.joint_lives is None:
        if joint_bases is not None:
            joint_bases.pop(segment.coverage_phase, None)
        return load_coverage_coi_rates(
            rates_db, plancode=plancode, issue_age=segment.issue_age,
            sex=segment.rate_sex, rateclass=segment.rate_class, scale=scale, band=band,
            issue_date=segment.issue_date,
        )
    company = rates_db.joint_survivor_company(plancode)
    if company is None:
        raise RateLookupError(
            f"Segment {segment.coverage_phase} carries joint lives, but {plancode} is not a "
            "joint survivor plan in UL_Rates rates.PLAN_ATTR (LIVES=3).")
    lives = segment.joint_lives
    basis = load_joint_basis(
        rates_db, company, plancode, lives.primary, lives.joint, lives.ratings)
    if joint_bases is not None:
        joint_bases[segment.coverage_phase] = basis
    # COI scale 1 = current, 0 = guaranteed (same convention as the IAF COI).
    return [None] + list(basis.schedule.current if scale == 1 else basis.schedule.guaranteed)


def load_segment_scr(
    rates_db: ULRates, plancode: str, segment, config: PlancodeConfig, *, state: str = None,
) -> List:
    """Per-unit surrender charge schedule for a base segment.

    Percent-of-surrender-target plans (CyberLife SCR rule 6) convert
    ``pct(year) x stored ST target`` to a per-unit rate on the segment's units
    at load, so a later face decrease reduces the charge pro rata (the VP/MS
    target recalculation is not available).
    """
    schedule = config.scr_pct_of_surrender_target
    if schedule is None:
        return rates_db.get_rates(
            "SCR", plancode, segment.issue_age, segment.rate_sex, segment.rate_class,
            band=segment.band, state=state, issue_date=segment.issue_date,
        ) or []
    if segment.surrender_target is None:
        raise RateLookupError(
            f"Coverage phase {segment.coverage_phase}: {plancode} surrender charges are a "
            "percent of the stored surrender target (LH_COV_TARGET 'ST'), which is missing.")
    if not segment.units:
        return [None] + [0.0] * len(schedule)
    per_unit = segment.surrender_target / segment.units
    return [None] + [pct * per_unit for pct in schedule] + [0.0]


@dataclass
class IllustrationRates:
    """Pre-loaded rate arrays for a single policy segment.

    All arrays are 1-indexed by duration. Access: rates.coi[duration].
    """

    # Duration-based arrays
    coi: List = field(default_factory=list)
    segment_coi: Dict[int, List] = field(default_factory=dict)
    # Joint survivor phases: the basis behind segment_coi (both lives' JS_Q,
    # rated q and survival steps by coverage year), keyed by coverage phase.
    segment_joint: Dict[int, JointBasis] = field(default_factory=dict)

    # Ratchet banding (RERUN CalcEngine PP-QX): the COI schedules for BOTH bands
    # per base segment, plus the band-2 break amount. Populated only when the
    # plancode is ratchet-banded (config.rachet_banding); empty otherwise.
    segment_coi_band1: Dict[int, List] = field(default_factory=dict)
    segment_coi_band2: Dict[int, List] = field(default_factory=dict)
    band_break: float = 0.0
    epu: List = field(default_factory=list)
    segment_epu: Dict[int, List] = field(default_factory=dict)
    # The band each segment_epu schedule was loaded at (epu_band), so a re-band
    # reloads the EPU only when that band moves.
    segment_epu_band: Dict[int, int] = field(default_factory=dict)
    scr: List = field(default_factory=list)
    segment_scr: Dict[int, List] = field(default_factory=dict)
    mfee: List = field(default_factory=list)
    gint: List = field(default_factory=list)
    tpp: List = field(default_factory=list)
    epp: List = field(default_factory=list)
    poav: List = field(default_factory=list)
    # Active assumption scales are retained so coverage segments created or
    # rebanded during a projection load rates on the same basis as the run.
    # COI: 1 = current, 0 = guaranteed maximum. Expense: 1 = current,
    # 0 = guaranteed (EPU, MFEE, PoAV, and premium loads).
    coi_scale: int = 1
    expense_scale: int = 1

    # Shadow account (CCV) rates — schema ``rates`` scale S on the base plancode
    # when the policy has a shadow account. Names match the get_rate() keys used
    # in core.shadow_calc.
    shadow_coi: List = field(default_factory=list)
    shadow_epu: List = field(default_factory=list)
    shadow_tpp: List = field(default_factory=list)
    shadow_epp: List = field(default_factory=list)
    shadow_tpr: List = field(default_factory=list)       # MTP scalar as constant array
    shadow_tpr_tbl1: List = field(default_factory=list)  # MTP_TBL1 scalar as constant array
    shadow_int: List = field(default_factory=list)       # SHADOW_INT (required)
    shadow_dbd: List = field(default_factory=list)       # DB_DISCOUNT scale S (required)
    # Waiver-of-deduction (39) uplift of the shadow target, as a fraction (BENMTP '39'
    # rate / 100), and the waiver's cease date; 0.0 when the plan or policy has none.
    shadow_target_waiver_pct: float = 0.0
    shadow_target_waiver_cease: Optional[date] = None

    # Benefit COI rates — keyed by combined type+subtype string (e.g. "39" for PW)
    # Each value is a 1-indexed list by policy year (benefit duration)
    benefit_coi: Dict[str, List] = field(default_factory=dict)
    # Benefit schedules replaced by the policy record's stored rate, keyed like
    # benefit_coi (see load_benefit_schedule).
    benefit_rate_overrides: Dict[str, BenefitRateOverride] = field(default_factory=dict)
    # Benefit schedule keys the plan's CyberLife PDF defines at zero premium; their
    # benefit_coi schedule is an explicit $0 (see load_benefit_schedule).
    zero_premium_benefits: set = field(default_factory=set)

    # Rider COI rates — keyed by RiderInfo.export_key (plancode_occurrence)
    rider_rates: Dict[str, List] = field(default_factory=dict)

    # Single values
    mtp: float = 0.0
    ctp: float = 0.0

    # ISWL fixed-premium basis (iswl_rates.ISWLRateBasis); None for UL-family plans.
    iswl: Optional[object] = None
    # UL rule-5 percent-of-account-value surrender charge (iswl_rates.ULPctOfAVSurrender);
    # None when the plan's surrender charge is per unit.
    pct_scr: Optional[object] = None


def mfee_schedule(rates_db: ULRates, plancode: str, segment, *, scale: int, band) -> List:
    """Monthly fee by coverage year: schema MFEE (none loaded = no fee)."""
    return rates_db.get_rates(
        "MFEE", plancode, segment.issue_age, segment.rate_sex, segment.rate_class,
        scale=scale, band=band, issue_date=segment.issue_date,
    ) or []


def premium_load_schedules(rates_db: ULRates, plancode: str, segment, *, scale: int,
                           band) -> tuple[List, List]:
    """Target (PREMLOAD_PCT) and excess (PREMLOAD_EXS, else PREMLOAD_PCT) load schedules
    (none loaded = no percentage load)."""
    cell = dict(issue_age=segment.issue_age, sex=segment.rate_sex, rateclass=segment.rate_class,
                scale=scale, band=band, issue_date=segment.issue_date)
    return (rates_db.get_rates("TPP", plancode, **cell) or [],
            rates_db.get_rates("EPP", plancode, **cell) or [])


# Shadow-account schedules the engine cannot run without; other rates (including
# the optional shadow EPU and premium loads) read as 0 when not loaded.
REQUIRED_SHADOW_RATES = frozenset({"shadow_coi", "shadow_int", "shadow_dbd", "shadow_tpr", "shadow_tpr_tbl1"})


def _safe_rate(arr: list, index: int, rate_name: str = "rate") -> float:
    """Access a 1-indexed rate array, returning the last value past its end."""
    required = rate_name in REQUIRED_SHADOW_RATES
    if not arr or len(arr) < 2:
        if not required:
            return 0.0
        raise RateLookupError(f"Required {rate_name} rate schedule is unavailable.")
    if index < 1:
        index = 1
    if index >= len(arr):
        return float(arr[-1])
    val = arr[index]
    if val is None:
        if not required:
            return 0.0
        raise RateLookupError(f"Required {rate_name} rate is unavailable for duration {index}.")
    return float(val)


def get_rate(rates_obj: IllustrationRates, rate_name: str, index: int) -> float:
    """Get a rate value by name and index with safe bounds handling."""
    arr = getattr(rates_obj, rate_name, [])
    return _safe_rate(arr, index, rate_name)


def _load_rider_coi_rates(rates_db: ULRates, rider) -> List:
    if rider_bands_as_base(rider.plancode):
        # Base-banding rider (e.g. 1U144A00): keep the policy's combined band set
        # in illustration_policy_service — do NOT re-derive from the rider's own
        # face. See core.band_rules.
        band = rider.band if rider.band is not None else 1
    else:
        band = rates_db.get_band(rider.plancode, rider.face_amount, issue_date=rider.issue_date)
        if band is None:
            band = rider.band if rider.band is not None else 1
    rider.band = int(band)
    return load_coverage_coi_rates(
        rates_db,
        plancode=rider.plancode,
        issue_age=rider.issue_age,
        sex=rider.rate_sex,
        rateclass=rider.rate_class,
        scale=1,
        band=rider.band,
        issue_date=rider.issue_date,
    )


def _benefit_rate_coverage(policy, benefit, segment):
    """The coverage segment whose sex/class/band key a benefit's BENCOI lookup."""
    return policy.segment_for_phase(benefit.coverage_phase) or segment


def _load_benefit_coi_rates(rates_db: ULRates, policy, benefit, segment) -> List:
    benefit_key = (benefit.benefit_type or "") + (benefit.benefit_subtype or "")
    # CyberLife looks up the benefit renewal rate by the assigned coverage's
    # attained age. Derive the rate-table issue age from that coverage phase
    # (falling back to the base segment) rather than the benefit's stored age.
    coverage = _benefit_rate_coverage(policy, benefit, segment)
    issue_age = benefit_rate_issue_age(policy, benefit)
    return rates_db.get_rates(
        "BENCOI",
        policy.plancode,
        issue_age=issue_age,
        sex=coverage.rate_sex,
        rateclass=coverage.rate_class,
        scale=1,
        band=coverage.band,
        benefit_type=benefit_key,
        issue_date=coverage.issue_date,
    ) or []


def _ccv_policy_rate_override(
    policy, benefit, segment, schedule_key: str, schedule: List,
) -> Optional[BenefitRateOverride]:
    """Detect a charged CCV benefit whose stored rate disagrees with UL_Rates.

    CCV charges (EXECUL plans) are level by issue age and keyed on the
    coverage's current rate class. A past rate-class change on the coverage
    (e.g. smoker -> nonsmoker) can leave the CCV benefit on its original
    class's rate, so the policy record — not the database — is what CyberLife
    charges. Only a stored, nonzero rate on a benefit with a database schedule
    qualifies; the comparison uses the benefit's current duration.
    """
    if (benefit.benefit_type or "") != CCV_BENEFIT_TYPE or not schedule:
        return None
    if benefit.coi_rate is None or benefit.coi_rate <= 0:
        return None
    from suiteview.illustration.core.monthly_deduction import benefit_rate_year

    duration = benefit_rate_year(benefit, policy, policy.valuation_date, policy.policy_year)
    database_rate = _safe_rate(schedule, duration)
    policy_rate = float(benefit.coi_rate)
    if abs(policy_rate - database_rate) <= _RATE_MATCH_TOLERANCE:
        return None
    return BenefitRateOverride(
        schedule_key=schedule_key,
        database_rate=database_rate,
        policy_rate=policy_rate,
        rate_class=_benefit_rate_coverage(policy, benefit, segment).rate_class,
    )


def load_benefit_schedule(
    result: IllustrationRates, rates_db: ULRates, policy, benefit, segment, schedule_key: str,
) -> None:
    """Load one benefit's COI schedule into ``result.benefit_coi[schedule_key]``.

    A charged CCV benefit whose stored policy rate differs from UL_Rates is
    charged at the policy rate for every duration and recorded in
    ``result.benefit_rate_overrides`` so the UI can say so. A benefit the plan's
    CyberLife PDF constructs at zero premium (``ULRates.zero_premium_benefits``) gets an
    explicit $0 schedule instead of a BENCOI lookup.
    """
    benefit_code = (benefit.benefit_type or "") + (benefit.benefit_subtype or "")
    if benefit_code in rates_db.zero_premium_benefits(policy.plancode):
        result.benefit_rate_overrides.pop(schedule_key, None)
        result.zero_premium_benefits.add(schedule_key)
        result.benefit_coi[schedule_key] = list(ZERO_PREMIUM_SCHEDULE)
        return
    result.zero_premium_benefits.discard(schedule_key)
    schedule = _load_benefit_coi_rates(rates_db, policy, benefit, segment)
    override = _ccv_policy_rate_override(policy, benefit, segment, schedule_key, schedule)
    if override is not None:
        schedule = [None] + [override.policy_rate] * (len(schedule) - 1)
        result.benefit_rate_overrides[schedule_key] = override
    else:
        result.benefit_rate_overrides.pop(schedule_key, None)
        schedule = _non_renewing_schedule(benefit, schedule)
    result.benefit_coi[schedule_key] = schedule


def benefit_rate_is_level(benefit) -> bool:
    """A non-renewing benefit (RNL_RT_IND 0) keeps its issue rate for life."""
    return not getattr(benefit, "renews", True)


def _non_renewing_schedule(benefit, schedule: List) -> List:
    """CyberLife holds a non-renewing benefit at its issue rate for every duration:
    the stored BNF_ANN_PPU_AMT (the issue rate in cents, e.g. NU1L2A00 WPLA 0.02 where
    BENCOI has 0.0166) or, when none is stored, the schedule's benefit-issue-year rate
    (1A130A29 3I 0.0117 at issue age 31, not 0.0967 at attained age 71)."""
    if len(schedule) < 2 or not benefit_rate_is_level(benefit):
        return schedule
    stored = float(benefit.coi_rate) if benefit.coi_rate and benefit.coi_rate > 0 else None
    level = stored if stored is not None else schedule[1]
    if level is None:
        return schedule
    return [None] + [level] * (len(schedule) - 1)


def load_rates(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    coi_scale: int = 1,
    expense_scale: int = 1,
) -> IllustrationRates:
    """Load all rate arrays for the policy's base segment.

    Rates come from UL_Rates schema ``rates`` through ``ULRates`` (schema reads
    are cached process-wide).

    Two independent scale axes drive the three run situations:

    - ``coi_scale``     — the mortality (COI) scale: 1 = current (illustrated),
                          0 = guaranteed maximum.
    - ``expense_scale`` — the expense scale governing EPU, MFEE, PoAV, and the
                          premium loads (TPP target / EPP excess): 1 = current,
                          0 = guaranteed.

    The three situations:

    1. Current illustration values  → ``coi_scale=1, expense_scale=1`` (default).
    2. Guaranteed illustration values → ``coi_scale=0, expense_scale=0``.
    3. Guideline (7702) calculations → ``coi_scale=0, expense_scale=1``.

    ISWL plancodes (``config.is_iswl``) load their fixed-premium basis through
    ``iswl_rates.load_iswl_rates``.
    """
    seg = policy.base_segment
    if seg is None:
        return IllustrationRates()
    _validate_scales(coi_scale, expense_scale)
    if config.is_iswl:
        from suiteview.illustration.core.iswl_rates import load_iswl_rates

        return load_iswl_rates(policy, config, coi_scale=coi_scale, expense_scale=expense_scale)
    rates_db = ULRates(policy.company_code)
    _initialize_dynamic_bands(policy, rates_db)
    segment_rates = _load_base_segment_rate_maps(
        policy, config, rates_db, coi_scale=coi_scale, expense_scale=expense_scale)
    result = _base_rate_bundle(
        policy, config, rates_db, seg, segment_rates,
        coi_scale=coi_scale, expense_scale=expense_scale)
    _load_ratchet_rates(result, policy, config, rates_db, coi_scale)
    _load_pct_of_av_surrender(result, policy, config, rates_db)
    _load_poav_rates(result, config, seg, expense_scale)
    _load_shadow_rates(result, policy, config, rates_db, seg)
    _load_benefit_rates(result, policy, rates_db, seg)
    _load_rider_rates(result, policy, rates_db)
    return result


def _validate_scales(coi_scale: int, expense_scale: int) -> None:
    if coi_scale not in (0, 1):
        raise ValueError(f"COI scale must be 0 or 1, got {coi_scale}")
    if expense_scale not in (0, 1):
        raise ValueError(f"Expense scale must be 0 or 1, got {expense_scale}")


def _load_pct_of_av_surrender(result: IllustrationRates, policy: IllustrationPolicyData,
                              config: PlancodeConfig, rates_db: ULRates) -> None:
    """UL rule-5 plans charge a percentage of the account value (schema ``SCR_PCT``)."""
    if not getattr(config, "ul_pct_of_av_surrender_charge", False):
        return
    from suiteview.illustration.core.iswl_rates import load_ul_pct_of_av_surrender

    result.pct_scr = load_ul_pct_of_av_surrender(policy, config, rates_db)


def _initialize_dynamic_bands(policy: IllustrationPolicyData, rates_db: ULRates) -> None:
    if policy.run_from_issue and not getattr(policy, "_issue_bands_initialized", False):
        initialize_issue_bands(policy, rates_db)
    elif policy.rollback_date is not None or policy.starting_coverage_amounts_are_manual:
        initialize_rollback_bands(policy, rates_db)


def _load_base_segment_rate_maps(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates_db: ULRates,
    *,
    coi_scale: int,
    expense_scale: int,
) -> dict[str, Dict[int, List]]:
    segment_coi: Dict[int, List] = {}
    segment_joint: Dict[int, JointBasis] = {}
    segment_epu: Dict[int, List] = {}
    segment_epu_band: Dict[int, int] = {}
    segment_scr: Dict[int, List] = {}
    for base_seg in policy.segments:
        segment_coi[base_seg.coverage_phase] = load_segment_coi(
            rates_db, policy.plancode, base_seg, scale=coi_scale, band=base_seg.band,
            joint_bases=segment_joint,
        )
        segment_epu_band[base_seg.coverage_phase] = epu_band(rates_db, policy, base_seg.band)
        segment_epu[base_seg.coverage_phase] = rates_db.get_rates(
            "EPU", policy.plancode, base_seg.issue_age, base_seg.rate_sex,
            base_seg.rate_class, scale=expense_scale, band=segment_epu_band[base_seg.coverage_phase],
            issue_date=base_seg.issue_date,
        ) or []
        segment_scr[base_seg.coverage_phase] = load_segment_scr(
            rates_db, policy.plancode, base_seg, config, state=policy.issue_state,
        )
    return {"coi": segment_coi, "joint": segment_joint, "epu": segment_epu,
            "epu_band": segment_epu_band, "scr": segment_scr}


def _base_rate_bundle(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates_db: ULRates,
    seg,
    segment_rates: dict[str, Dict[int, List]],
    *,
    coi_scale: int,
    expense_scale: int,
) -> IllustrationRates:
    tpp, epp = premium_load_schedules(
        rates_db, policy.plancode, seg, scale=expense_scale, band=seg.band)
    return IllustrationRates(
        coi=segment_rates["coi"].get(seg.coverage_phase, []),
        segment_coi=segment_rates["coi"],
        segment_joint=segment_rates["joint"],
        epu=segment_rates["epu"].get(seg.coverage_phase, []),
        segment_epu=segment_rates["epu"],
        segment_epu_band=segment_rates["epu_band"],
        scr=segment_rates["scr"].get(seg.coverage_phase, []),
        segment_scr=segment_rates["scr"],
        mfee=mfee_schedule(rates_db, policy.plancode, seg, scale=expense_scale, band=seg.band),
        gint=rates_db.get_rates("GINT", policy.plancode) or [],
        tpp=tpp,
        epp=epp,
        mtp=rates_db.get_mtp(
            policy.plancode, seg.issue_age, seg.rate_sex,
            seg.rate_class,
            seg.original_band if config.sa_basis == "OriginalSA" else seg.band,
            issue_date=seg.issue_date,
        ) or 0.0,
        ctp=rates_db.get_ctp(
            policy.plancode, seg.issue_age, seg.rate_sex,
            seg.rate_class, seg.band, issue_date=seg.issue_date,
        ) or 0.0,
        coi_scale=coi_scale,
        expense_scale=expense_scale,
    )


def _load_ratchet_rates(
    result: IllustrationRates,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates_db: ULRates,
    coi_scale: int,
) -> None:
    if not config.rachet_banding:
        return
    for base_seg in policy.segments:
        result.segment_coi_band1[base_seg.coverage_phase] = load_coverage_coi_rates(
            rates_db, plancode=policy.plancode, issue_age=base_seg.issue_age,
            sex=base_seg.rate_sex, rateclass=base_seg.rate_class,
            scale=coi_scale, band=1, issue_date=base_seg.issue_date,
        ) or []
        result.segment_coi_band2[base_seg.coverage_phase] = load_coverage_coi_rates(
            rates_db, plancode=policy.plancode, issue_age=base_seg.issue_age,
            sex=base_seg.rate_sex, rateclass=base_seg.rate_class,
            scale=coi_scale, band=2, issue_date=base_seg.issue_date,
        ) or []
    result.band_break = rates_db.get_band_break(
        policy.plancode, band=2, issue_date=policy.issue_date) or 0.0


def _load_poav_rates(
    result: IllustrationRates,
    config: PlancodeConfig,
    seg,
    expense_scale: int,
) -> None:
    if config.poav_table != "0":
        result.poav = load_poav_schedule(
            config.poav_table,
            seg.band,
            scale=expense_scale,
        )


def _shadow_band(policy: IllustrationPolicyData, config: PlancodeConfig, rates_db: ULRates, seg) -> int:
    """Band of the shadow rate cell.

    ``ShadowIssueBand`` (SGUL): the shadow COI band is the band of the face issued at
    policy issue; later face changes do not move it, whether a withdrawal cuts a level
    face or the owner asks for a decrease:
      * UE057740: 100,000 issued, 98,304 after withdrawals, CyberLife RT_BAN_CD now A.
        Band 2 reproduces XP from issue (+0.30); band 1 leaves the replay at -68.06.
      * UE059231: requested decrease 150,000 -> 50,000 on 5/7/2026 (RT_BAN_CD A). The
        replay drifts -0.25/month on band 1 (-0.74 by 9/2026) and is exact on band 2.
    The issued face is the base (non-COLA) coverage issued with the policy, so an
    increase does not raise the shadow band either (no evidence; the lower band is the
    conservative choice).
    """
    band = seg.original_band
    if not (config.shadow_issue_band and seg.is_base):
        return band
    issued = sum(
        float(s.original_face_amount or s.face_amount or 0.0)
        for s in policy.segments
        if s.is_base and not getattr(s, "is_cola", False)
        and (s.issue_date is None or policy.issue_date is None or s.issue_date <= policy.issue_date)
    )
    if issued <= 0.0:
        return band
    at_issue = rates_db.get_band(policy.plancode, issued, issue_date=policy.issue_date)
    return int(at_issue) if at_issue is not None else band


def _load_shadow_rates(
    result: IllustrationRates,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates_db: ULRates,
    seg,
) -> None:
    """Shadow account rates: schema ``rates`` scale S on the base plancode's cells.

    COI, SHADOW_INT and DB_DISCOUNT are required (``RateLookupError`` when missing).
    EPU, the premium loads and the shadow target are optional: a plan without them on
    scale S has no such shadow charge or target."""
    if not policy.has_shadow_account:
        return
    if not config.shadow_plancode and not config.shadow_availability:
        raise RateLookupError(
            f"Policy has an active shadow account, but plancode {policy.plancode} "
            "has no shadow-account configuration."
        )
    plancode = policy.plancode
    cell = dict(issue_age=seg.issue_age, sex=seg.rate_sex, rateclass=seg.rate_class,
                scale=SHADOW, band=_shadow_band(policy, config, rates_db, seg), issue_date=seg.issue_date)
    result.shadow_coi = load_coverage_coi_rates(rates_db, plancode=plancode, **cell)
    for attr, rate_type in (("shadow_int", "SHADOW_INT"), ("shadow_dbd", "DBD")):
        schedule = rates_db.get_rates(rate_type, plancode, **cell)
        if not schedule:
            _raise_missing_shadow_schedule(rates_db, rate_type, plancode, cell)
        setattr(result, attr, schedule)
    for attr, rate_type in (("shadow_epu", "EPU"), ("shadow_tpp", "TPP"), ("shadow_epp", "EPP")):
        setattr(result, attr, rates_db.get_rates(rate_type, plancode, **cell) or [])
    _load_shadow_single_values(result, config, rates_db, seg, plancode)
    _load_shadow_target_waiver(result, policy, config, rates_db, seg)


def _load_shadow_target_waiver(result, policy, config, rates_db, seg) -> None:
    """Waiver-of-deduction (39) uplift of the shadow target (``ShadowTargetWaiverUplift``).

    LTGUL spec: "The CCV target premium will be increased by the rider target premium."
    The 39 rider's target is its BENMTP rate as a percent of the base target, as on the
    regular target.  Required when the flag is on and the policy carries the waiver.
    """
    if not config.shadow_target_waiver_uplift or not result.shadow_tpr:
        return
    waiver = next((b for b in policy.benefits
                   if b.is_active and (b.benefit_type or "") + (b.benefit_subtype or "") == "39"), None)
    if waiver is None:
        return
    band = seg.original_band if config.sa_basis == "OriginalSA" else seg.band
    rate = rates_db.get_ben_mtp(policy.plancode, seg.issue_age, seg.rate_sex, seg.rate_class, band, "39",
                                issue_date=seg.issue_date)
    if rate is None:
        raise RateLookupError(
            f"Required waiver (39) BENMTP rate for the shadow target is unavailable for plancode "
            f"{policy.plancode}, issue age {seg.issue_age}, sex {seg.rate_sex}, "
            f"rate class {seg.rate_class}, band {band}."
        )
    result.shadow_target_waiver_pct = rate / 100.0
    result.shadow_target_waiver_cease = waiver.cease_date


def _load_shadow_single_values(result, config, rates_db, seg, plancode: str) -> None:
    args = (plancode, seg.issue_age, seg.rate_sex, seg.rate_class, seg.original_band)
    target_basis = config.shadow_target_rate_basis
    if target_basis == "CTP":
        shadow_target = rates_db.get_ctp(*args, issue_date=seg.issue_date, scale=SHADOW)
        shadow_tbl1 = rates_db.get_tbl1_ctp(*args, issue_date=seg.issue_date, scale=SHADOW)
    else:
        shadow_target = rates_db.get_mtp(*args, issue_date=seg.issue_date, scale=SHADOW)
        shadow_tbl1 = rates_db.get_tbl1_mtp(*args, issue_date=seg.issue_date, scale=SHADOW)
    if shadow_target is None:
        # No scale S target rate: the plan has no shadow target premium.
        result.shadow_tpr = []
        result.shadow_tpr_tbl1 = []
        return
    result.shadow_tpr = [None, shadow_target]
    if seg.table_rating > 0 and shadow_tbl1 is None:
        raise RateLookupError(
            f"Required shadow {target_basis}_TBL1 rate is unavailable for plancode {plancode} (scale S), "
            f"coverage phase {seg.coverage_phase}, issue age {seg.issue_age}, "
            f"sex {seg.rate_sex}, rate class {seg.rate_class}, "
            f"band {seg.original_band}, table rating {seg.table_rating}."
        )
    result.shadow_tpr_tbl1 = [None, shadow_tbl1] if shadow_tbl1 is not None else []


def _raise_missing_shadow_schedule(rates_db, rate_type: str, plancode: str, cell: dict) -> None:
    source = (
        "" if rates_db.is_loaded(plancode)
        else f" Plancode {plancode or '<blank>'} is not loaded in UL_Rates schema rates."
    )
    raise RateLookupError(
        f"Required shadow {rate_type} rate schedule was not found. "
        f"Lookup: plancode {plancode or '<blank>'}, issue age {cell.get('issue_age')}, "
        f"sex {cell.get('sex') or '<blank>'}, rate class {cell.get('rateclass') or '<blank>'}, "
        f"band {cell.get('band')}, scale S (shadow account).{source}"
    )


def _load_benefit_rates(
    result: IllustrationRates,
    policy: IllustrationPolicyData,
    rates_db: ULRates,
    seg,
) -> None:
    rate_keys = benefit_rate_keys(policy.benefits)
    for ben in policy.benefits:
        if not ben.is_active:
            continue
        if (ben.benefit_type or "").startswith("#"):
            continue
        base_key = (ben.benefit_type or "") + (ben.benefit_subtype or "")
        if not base_key:
            continue
        schedule_key = rate_keys[id(ben)]
        if schedule_key in result.benefit_coi:
            continue
        load_benefit_schedule(result, rates_db, policy, ben, seg, schedule_key)
        if not result.benefit_coi[schedule_key] and _benefit_charge_pending(ben, policy):
            coverage = _benefit_rate_coverage(policy, ben, seg)
            raise RateLookupError(
                f"No BENCOI rates in UL_Rates schema rates for chargeable benefit "
                f"{base_key} on plancode {policy.plancode}: coverage phase "
                f"{ben.coverage_phase}, issue age {benefit_rate_issue_age(policy, ben)}, "
                f"sex {coverage.rate_sex}, rate class {coverage.rate_class}, "
                f"band {coverage.band}. The benefit would otherwise be charged $0."
            )


def _benefit_charge_pending(ben, policy: IllustrationPolicyData) -> bool:
    """Whether an active benefit still charges a COI on or after the valuation date.

    Types in ``CHARGEABLE_BENEFIT_TYPES`` always carry a COI; others (A0, V1-V3,
    U0/U1, ...) are informational and legitimately have no BENCOI schedule.
    """
    if (ben.benefit_type or "").strip() not in CHARGEABLE_BENEFIT_TYPES:
        return False
    as_of = policy.valuation_date
    return not (ben.pay_up_date is not None and as_of is not None and as_of >= ben.pay_up_date)


def _load_rider_rates(result: IllustrationRates, policy: IllustrationPolicyData, rates_db: ULRates) -> None:
    for rider in policy.riders:
        if not rider.is_active or not rider.plancode:
            continue
        result.rider_rates[rider.export_key] = _load_rider_coi_rates(rates_db, rider)


def _unbanded_as_one(band) -> int:
    """``ULRates.get_band`` is None only for a plan without ``PLAN_BAND`` rows; band 1
    then reaches the plan's cells through the cell lookup's band ``0`` fallback."""
    return int(band) if band is not None else 1


def epu_band(rates_db, policy: IllustrationPolicyData, band: int) -> int:
    """The EPU band: ``band`` unless terminated base-plan phases are still on the record,
    which CyberLife counts in the EPU band (``policy.epu_band_specified_amount``)."""
    if not policy.terminated_base_face:
        return band
    raw = rates_db.get_band(
        policy.plancode, policy.epu_band_specified_amount, issue_date=policy.issue_date)
    return int(raw) if raw else band


def initialize_rollback_bands(policy: IllustrationPolicyData, rates_db: ULRates) -> None:
    """Resolve edited current bands without rewriting the original surrender basis."""
    policy.band = _unbanded_as_one(rates_db.get_band(
        policy.plancode, policy.band_specified_amount, issue_date=policy.issue_date))
    for segment in policy.segments:
        segment.band = policy.band
    for rider in policy.riders:
        if rider_bands_as_base(rider.plancode):
            rider.band = policy.band
        else:
            rider.band = _unbanded_as_one(rates_db.get_band(
                rider.plancode, rider.face_amount, issue_date=rider.issue_date))


def initialize_issue_bands(policy: IllustrationPolicyData, rates_db: ULRates) -> None:
    """Resolve edited issue bands at the existing database boundary, once per basis.

    At issue, original and current amounts coincide for every dynamic-banding
    configuration. Later engine changes must not rewrite this original band.
    """
    policy.band = _unbanded_as_one(rates_db.get_band(
        policy.plancode, policy.band_specified_amount, issue_date=policy.issue_date,
    ))
    for segment in policy.segments:
        segment.band = segment.original_band = policy.band
    for rider in policy.riders:
        if rider_bands_as_base(rider.plancode):
            rider.band = policy.band
        else:
            rider.band = _unbanded_as_one(rates_db.get_band(
                rider.plancode, rider.face_amount, issue_date=rider.issue_date))
    policy._issue_bands_initialized = True
