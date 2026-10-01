"""Load projection rate schedules for an IllustrationPolicyData basis.

Rate loading is intentionally a copy/read boundary:

* `load_rates` does not project; it resolves the rate schedules the engine will
  read for the supplied policy/config basis.
* Band initialization is the only policy mutation here. Issue and rollback
  scenarios need their edited starting bands resolved before schedule lookup.
* Current, guaranteed and guideline runs differ only by the explicit COI and
  expense scale arguments documented on `load_rates`.
* Missing required COI/shadow schedules raise `RateLookupError`; optional
  rider/benefit schedules remain empty so the validation layer can report them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from suiteview.core.band_rules import rider_bands_as_base
from suiteview.core.joint_survivor_coi import JointBasis, load_joint_basis
from suiteview.core.rates import Rates
from suiteview.illustration.core.poav_rates import load_poav_schedule
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
    rates_db: Rates,
    *,
    plancode: str,
    issue_age: int,
    sex: str,
    rateclass: str,
    scale: int,
    band: int,
) -> List:
    """Load COI rates, applying the approved preferred-class fallback."""
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
        )
        if schedule:
            return schedule

    attempted = " then ".join(
        f"rate class {lookup_class or '<blank>'}" for lookup_class in lookup_classes
    )
    raise RateLookupError(
        "Required COI rate schedule was not found. "
        f"Lookup: plancode {plancode or '<blank>'}, issue age {issue_age}, "
        f"sex {sex or '<blank>'}, {attempted}, band {band}, scale {scale}."
    )


def load_segment_coi(
    rates_db: Rates, plancode: str, segment, *, scale: int, band: int,
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
    rates_db: Rates, plancode: str, segment, config: PlancodeConfig, *, state: str = None,
) -> List:
    """Per-unit surrender charge schedule for a base segment.

    Percent-of-surrender-target plans (CyberLife SCR rule 6) convert
    ``pct(year) x stored ST target`` to a per-unit rate on the segment's units
    at load, so a later face decrease reduces the charge pro rata (the VP/MS
    target recalculation is not available).
    """
    schedule = config.scr_pct_of_surrender_target
    if schedule is None:
        state_kwargs = {"state": state} if state is not None else {}
        return rates_db.get_rates(
            "SCR", plancode, segment.issue_age, segment.rate_sex, segment.rate_class,
            scale=1, band=segment.band, **state_kwargs,
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

    # Loan credit rates (duration-based)
    rlncrg: List = field(default_factory=list)   # Regular loan credit rate — guaranteed
    rlncrd: List = field(default_factory=list)   # Regular loan credit rate — declared
    plncrg: List = field(default_factory=list)   # Preferred loan credit rate — guaranteed
    plncrd: List = field(default_factory=list)   # Preferred loan credit rate — declared

    # Shadow account (CCV) rates — loaded from the ShadowPlancode (e.g.
    # CCV48000) when the policy has a shadow account. Names match the
    # get_rate() keys used in core.shadow_calc.
    shadow_coi: List = field(default_factory=list)
    shadow_epu: List = field(default_factory=list)
    shadow_tpp: List = field(default_factory=list)
    shadow_epp: List = field(default_factory=list)
    shadow_tpr: List = field(default_factory=list)       # MTP scalar as constant array
    shadow_tpr_tbl1: List = field(default_factory=list)  # TBL1MTP scalar as constant array
    shadow_int: List = field(default_factory=list)       # GINT (ShadowIntRateCode="Table")
    shadow_dbd: List = field(default_factory=list)       # DBD  (ShadowDBDRate="Table")

    # Benefit COI rates — keyed by combined type+subtype string (e.g. "39" for PW)
    # Each value is a 1-indexed list by policy year (benefit duration)
    benefit_coi: Dict[str, List] = field(default_factory=dict)
    # Benefit schedules replaced by the policy record's stored rate, keyed like
    # benefit_coi (see load_benefit_schedule).
    benefit_rate_overrides: Dict[str, BenefitRateOverride] = field(default_factory=dict)

    # Rider COI rates — keyed by RiderInfo.export_key (plancode_occurrence)
    rider_rates: Dict[str, List] = field(default_factory=dict)

    # Single values
    mtp: float = 0.0
    ctp: float = 0.0

    # ISWL fixed-premium basis (iswl_rates.ISWLRateBasis); None for UL-family plans.
    iswl: Optional[object] = None


def _safe_rate(arr: list, index: int) -> float:
    """Safely access a 1-indexed rate array, returning last value if index out of range."""
    if not arr or len(arr) < 2:
        return 0.0
    if index < 1:
        index = 1
    if index >= len(arr):
        return float(arr[-1])
    val = arr[index]
    return float(val) if val is not None else 0.0


def get_rate(rates_obj: IllustrationRates, rate_name: str, index: int) -> float:
    """Get a rate value by name and index with safe bounds handling."""
    arr = getattr(rates_obj, rate_name, [])
    return _safe_rate(arr, index)


def _load_rider_coi_rates(rates_db: Rates, rider) -> List:
    if rider_bands_as_base(rider.plancode):
        # Base-banding rider (e.g. 1U144A00): keep the policy's combined band set
        # in illustration_policy_service — do NOT re-derive from the rider's own
        # face. See core.band_rules.
        band = rider.band if rider.band is not None else 1
    else:
        band = rates_db.get_band(rider.plancode, rider.face_amount)
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
    )


def _benefit_rate_coverage(policy, benefit, segment):
    """The coverage segment whose sex/class/band key a benefit's BENCOI lookup."""
    return policy.segment_for_phase(benefit.coverage_phase) or segment


def _load_benefit_coi_rates(rates_db: Rates, policy, benefit, segment) -> List:
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
    result: IllustrationRates, rates_db: Rates, policy, benefit, segment, schedule_key: str,
) -> None:
    """Load one benefit's COI schedule into ``result.benefit_coi[schedule_key]``.

    A charged CCV benefit whose stored policy rate differs from UL_Rates is
    charged at the policy rate for every duration and recorded in
    ``result.benefit_rate_overrides`` so the UI can say so.
    """
    schedule = _load_benefit_coi_rates(rates_db, policy, benefit, segment)
    override = _ccv_policy_rate_override(policy, benefit, segment, schedule_key, schedule)
    if override is not None:
        schedule = [None] + [override.policy_rate] * (len(schedule) - 1)
        result.benefit_rate_overrides[schedule_key] = override
    else:
        result.benefit_rate_overrides.pop(schedule_key, None)
    result.benefit_coi[schedule_key] = schedule


def load_rates(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    coi_scale: int = 1,
    expense_scale: int = 1,
) -> IllustrationRates:
    """Load all rate arrays for the policy's base segment.

    Uses the Rates class to fetch from UL_Rates SQL Server database.
    Rates are cached at the Rates class level.

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

    ISWL plancodes (``config.is_iswl``) load every rate from UL_Rates schema
    ``rates`` instead (``iswl_rates.load_iswl_rates``).
    """
    seg = policy.base_segment
    if seg is None:
        return IllustrationRates()
    _validate_scales(coi_scale, expense_scale)
    if config.is_iswl:
        from suiteview.illustration.core.iswl_rates import load_iswl_rates

        return load_iswl_rates(policy, config, coi_scale=coi_scale, expense_scale=expense_scale)
    rates_db = Rates()
    _initialize_dynamic_bands(policy, rates_db)
    segment_rates = _load_base_segment_rate_maps(
        policy, config, rates_db, coi_scale=coi_scale, expense_scale=expense_scale)
    result = _base_rate_bundle(
        policy, config, rates_db, seg, segment_rates,
        coi_scale=coi_scale, expense_scale=expense_scale)
    _load_ratchet_rates(result, policy, config, rates_db, coi_scale)
    _load_poav_rates(result, config, seg, expense_scale)
    _load_loan_rates(result, policy, rates_db)
    _load_shadow_rates(result, policy, config, rates_db, seg)
    _load_benefit_rates(result, policy, rates_db, seg)
    _load_rider_rates(result, policy, rates_db)
    return result


def _validate_scales(coi_scale: int, expense_scale: int) -> None:
    if coi_scale not in (0, 1):
        raise ValueError(f"COI scale must be 0 or 1, got {coi_scale}")
    if expense_scale not in (0, 1):
        raise ValueError(f"Expense scale must be 0 or 1, got {expense_scale}")


def _initialize_dynamic_bands(policy: IllustrationPolicyData, rates_db: Rates) -> None:
    if policy.run_from_issue and not getattr(policy, "_issue_bands_initialized", False):
        initialize_issue_bands(policy, rates_db)
    elif policy.rollback_date is not None or policy.starting_coverage_amounts_are_manual:
        initialize_rollback_bands(policy, rates_db)


def _load_base_segment_rate_maps(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates_db: Rates,
    *,
    coi_scale: int,
    expense_scale: int,
) -> dict[str, Dict[int, List]]:
    segment_coi: Dict[int, List] = {}
    segment_joint: Dict[int, JointBasis] = {}
    segment_epu: Dict[int, List] = {}
    segment_scr: Dict[int, List] = {}
    for base_seg in policy.segments:
        segment_coi[base_seg.coverage_phase] = load_segment_coi(
            rates_db, policy.plancode, base_seg, scale=coi_scale, band=base_seg.band,
            joint_bases=segment_joint,
        )
        segment_epu[base_seg.coverage_phase] = rates_db.get_rates(
            "EPU", policy.plancode, base_seg.issue_age, base_seg.rate_sex,
            base_seg.rate_class, scale=expense_scale, band=base_seg.band,
        ) or []
        segment_scr[base_seg.coverage_phase] = load_segment_scr(
            rates_db, policy.plancode, base_seg, config, state=policy.issue_state,
        )
    return {"coi": segment_coi, "joint": segment_joint, "epu": segment_epu, "scr": segment_scr}


def _base_rate_bundle(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates_db: Rates,
    seg,
    segment_rates: dict[str, Dict[int, List]],
    *,
    coi_scale: int,
    expense_scale: int,
) -> IllustrationRates:
    return IllustrationRates(
        coi=segment_rates["coi"].get(seg.coverage_phase, []),
        segment_coi=segment_rates["coi"],
        segment_joint=segment_rates["joint"],
        epu=segment_rates["epu"].get(seg.coverage_phase, []),
        segment_epu=segment_rates["epu"],
        scr=segment_rates["scr"].get(seg.coverage_phase, []),
        segment_scr=segment_rates["scr"],
        mfee=rates_db.get_rates(
            "MFEE", policy.plancode, seg.issue_age, seg.rate_sex,
            seg.rate_class, scale=expense_scale, band=seg.band,
        ) or [],
        gint=rates_db.get_rates("GINT", policy.plancode) or [],
        tpp=rates_db.get_rates(
            "TPP", policy.plancode, issue_age=seg.issue_age,
            sex=seg.rate_sex, rateclass=seg.rate_class,
            scale=expense_scale, band=seg.band,
        ) or [],
        epp=rates_db.get_rates(
            "EPP", policy.plancode, issue_age=seg.issue_age,
            sex=seg.rate_sex, rateclass=seg.rate_class,
            scale=expense_scale, band=seg.band,
        ) or [],
        mtp=rates_db.get_mtp(
            policy.plancode, seg.issue_age, seg.rate_sex,
            seg.rate_class,
            seg.original_band if config.sa_basis == "OriginalSA" else seg.band,
        ) or 0.0,
        ctp=rates_db.get_ctp(
            policy.plancode, seg.issue_age, seg.rate_sex,
            seg.rate_class, seg.band,
        ) or 0.0,
        coi_scale=coi_scale,
        expense_scale=expense_scale,
    )


def _load_ratchet_rates(
    result: IllustrationRates,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates_db: Rates,
    coi_scale: int,
) -> None:
    if not config.rachet_banding:
        return
    for base_seg in policy.segments:
        result.segment_coi_band1[base_seg.coverage_phase] = load_coverage_coi_rates(
            rates_db, plancode=policy.plancode, issue_age=base_seg.issue_age,
            sex=base_seg.rate_sex, rateclass=base_seg.rate_class,
            scale=coi_scale, band=1,
        ) or []
        result.segment_coi_band2[base_seg.coverage_phase] = load_coverage_coi_rates(
            rates_db, plancode=policy.plancode, issue_age=base_seg.issue_age,
            sex=base_seg.rate_sex, rateclass=base_seg.rate_class,
            scale=coi_scale, band=2,
        ) or []
    result.band_break = rates_db.get_band_break(policy.plancode, band=2) or 0.0


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


def _load_loan_rates(result: IllustrationRates, policy: IllustrationPolicyData, rates_db: Rates) -> None:
    if not policy.has_loans:
        return
    result.rlncrg = rates_db.get_rates("RLNCRG", policy.plancode) or []
    result.rlncrd = rates_db.get_rates("RLNCRD", policy.plancode) or []
    result.plncrg = rates_db.get_rates("PLNCRG", policy.plancode) or []
    result.plncrd = rates_db.get_rates("PLNCRD", policy.plancode) or []


def _load_shadow_rates(
    result: IllustrationRates,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates_db: Rates,
    seg,
) -> None:
    if not (policy.has_shadow_account and config.shadow_plancode):
        return
    shp = config.shadow_plancode
    result.shadow_coi = load_coverage_coi_rates(
        rates_db, plancode=shp, issue_age=seg.issue_age, sex=seg.rate_sex,
        rateclass=seg.rate_class, scale=1, band=seg.original_band,
    )
    result.shadow_epu = rates_db.get_rates(
        "EPU", shp, seg.issue_age, seg.rate_sex,
        seg.rate_class, scale=1, band=seg.original_band,
    ) or []
    result.shadow_tpp = rates_db.get_rates(
        "TPP", shp, issue_age=seg.issue_age, sex=seg.rate_sex,
        rateclass=seg.rate_class, scale=1, band=seg.original_band,
    ) or []
    result.shadow_epp = rates_db.get_rates(
        "EPP", shp, issue_age=seg.issue_age, sex=seg.rate_sex,
        rateclass=seg.rate_class, scale=1, band=seg.original_band,
    ) or []
    _load_shadow_single_values(result, config, rates_db, seg, shp)


def _load_shadow_single_values(result, config, rates_db, seg, shp: str) -> None:
    shadow_mtp = rates_db.get_mtp(
        shp, seg.issue_age, seg.rate_sex, seg.rate_class, seg.original_band)
    result.shadow_tpr = [None, shadow_mtp] if shadow_mtp is not None else []
    shadow_tbl1 = rates_db.get_tbl1_mtp(
        shp, seg.issue_age, seg.rate_sex, seg.rate_class, seg.original_band)
    if config.shadow_target == "Table" and seg.table_rating > 0 and shadow_tbl1 is None:
        raise RateLookupError(
            f"Required shadow TBL1MTP rate is unavailable for plancode {shp}, "
            f"coverage phase {seg.coverage_phase}, issue age {seg.issue_age}, "
            f"sex {seg.rate_sex}, rate class {seg.rate_class}, "
            f"band {seg.original_band}, table rating {seg.table_rating}."
        )
    result.shadow_tpr_tbl1 = [None, shadow_tbl1] if shadow_tbl1 is not None else []
    if config.shadow_int_rate_code == "Table":
        result.shadow_int = rates_db.get_rates("GINT", shp) or []
    if config.shadow_dbd_rate == "Table":
        result.shadow_dbd = rates_db.get_rates("DBD", shp) or []


def _load_benefit_rates(
    result: IllustrationRates,
    policy: IllustrationPolicyData,
    rates_db: Rates,
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


def _load_rider_rates(result: IllustrationRates, policy: IllustrationPolicyData, rates_db: Rates) -> None:
    for rider in policy.riders:
        if not rider.is_active or not rider.plancode:
            continue
        result.rider_rates[rider.export_key] = _load_rider_coi_rates(rates_db, rider)
def initialize_rollback_bands(policy: IllustrationPolicyData, rates_db: Rates) -> None:
    """Resolve edited current bands without rewriting the original surrender basis."""
    band = rates_db.get_band(
        policy.plancode, policy.band_specified_amount, issue_date=policy.issue_date)
    if band is None:
        raise RateLookupError("Cannot determine the rate band for the starting specified amount.")
    policy.band = int(band)
    for segment in policy.segments:
        segment.band = policy.band
    for rider in policy.riders:
        if rider_bands_as_base(rider.plancode):
            rider.band = policy.band
        else:
            band = rates_db.get_band(rider.plancode, rider.face_amount)
            if band is None:
                raise RateLookupError(f"Cannot determine the starting band for rider {rider.plancode}.")
            rider.band = int(band)


def initialize_issue_bands(policy: IllustrationPolicyData, rates_db: Rates) -> None:
    """Resolve edited issue bands at the existing database boundary, once per basis.

    At issue, original and current amounts coincide for every dynamic-banding
    configuration. Later engine changes must not rewrite this original band.
    """
    band = rates_db.get_band(
        policy.plancode, policy.band_specified_amount, issue_date=policy.issue_date,
    )
    policy.band = int(band) if band is not None else 1
    for segment in policy.segments:
        segment.band = segment.original_band = policy.band
    for rider in policy.riders:
        if rider_bands_as_base(rider.plancode):
            rider.band = policy.band
        else:
            rider_band = rates_db.get_band(rider.plancode, rider.face_amount)
            rider.band = int(rider_band) if rider_band is not None else 1
    policy._issue_bands_initialized = True
