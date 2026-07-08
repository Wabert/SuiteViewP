from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from suiteview.core.rates import Rates
from suiteview.illustration.models.policy_data import IllustrationPolicyData
from suiteview.illustration.models.plancode_config import PlancodeConfig


@dataclass
class IllustrationRates:
    """Pre-loaded rate arrays for a single policy segment.

    All arrays are 1-indexed by duration. Access: rates.coi[duration].
    """

    # Duration-based arrays
    coi: List = field(default_factory=list)
    segment_coi: Dict[int, List] = field(default_factory=dict)

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

    # Loan credit rates (duration-based)
    rlncrg: List = field(default_factory=list)   # Regular loan credit rate — guaranteed
    rlncrd: List = field(default_factory=list)   # Regular loan credit rate — declared
    plncrg: List = field(default_factory=list)   # Preferred loan credit rate — guaranteed
    plncrd: List = field(default_factory=list)   # Preferred loan credit rate — declared

    # Shadow account (CCV) COI rates (duration-based)
    shadow_coi: List = field(default_factory=list)

    # Benefit COI rates — keyed by combined type+subtype string (e.g. "39" for PW)
    # Each value is a 1-indexed list by policy year (benefit duration)
    benefit_coi: Dict[str, List] = field(default_factory=dict)

    # Rider COI rates — keyed by RiderInfo.export_key (plancode_occurrence)
    rider_rates: Dict[str, List] = field(default_factory=dict)

    # Single values
    mtp: float = 0.0
    ctp: float = 0.0


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
    band = rates_db.get_band(rider.plancode, rider.face_amount)
    if band is None:
        band = rider.band if rider.band is not None else 1
    rider.band = int(band)
    return rates_db.get_coi(
        rider.plancode,
        rider.issue_age,
        rider.rate_sex,
        rider.rate_class,
        scale=1,
        band=rider.band,
    ) or []


def load_rates(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    coi_scale: int = 1,
) -> IllustrationRates:
    """Load all rate arrays for the policy's base segment.

    Uses the Rates class to fetch from UL_Rates SQL Server database.
    Rates are cached at the Rates class level.

    ``coi_scale`` selects the COI scale: 1 = current (illustrated, the default and
    what matches RERUN's projection), 0 = guaranteed maximum COI. Build guaranteed
    rates with ``coi_scale=0`` to feed the 7702 guideline / TAMRA calculators
    (loads/fees stay current). The active scale per plancode is in
    ``Select_SCALE_COI`` (= 1 for these plancodes).
    """
    rates_db = Rates()
    seg = policy.base_segment

    if seg is None:
        return IllustrationRates()

    segment_coi = {}
    segment_epu = {}
    segment_scr = {}
    for base_seg in policy.segments:
        segment_coi[base_seg.coverage_phase] = rates_db.get_rates(
            "COI", policy.plancode, base_seg.issue_age, base_seg.rate_sex,
            base_seg.rate_class, scale=coi_scale, band=base_seg.band,
        ) or []
        segment_epu[base_seg.coverage_phase] = rates_db.get_rates(
            "EPU", policy.plancode, base_seg.issue_age, base_seg.rate_sex,
            base_seg.rate_class, scale=1, band=base_seg.band,
        ) or []
        segment_scr[base_seg.coverage_phase] = rates_db.get_rates(
            "SCR", policy.plancode, base_seg.issue_age, base_seg.rate_sex,
            base_seg.rate_class, scale=1, band=base_seg.band,
            state=policy.issue_state,
        ) or []

    result = IllustrationRates(
        coi=segment_coi.get(seg.coverage_phase, []),
        segment_coi=segment_coi,
        epu=segment_epu.get(seg.coverage_phase, []),
        segment_epu=segment_epu,
        scr=segment_scr.get(seg.coverage_phase, []),
        segment_scr=segment_scr,
        mfee=rates_db.get_rates(
            "MFEE", policy.plancode, seg.issue_age, seg.rate_sex,
            seg.rate_class, scale=1, band=seg.band,
        ) or [],
        gint=rates_db.get_rates("GINT", policy.plancode) or [],
        tpp=rates_db.get_rates(
            "TPP", policy.plancode, issue_age=seg.issue_age,
            sex=seg.rate_sex, rateclass=seg.rate_class,
            scale=1, band=seg.band,
        ) or [],
        epp=rates_db.get_rates(
            "EPP", policy.plancode, issue_age=seg.issue_age,
            sex=seg.rate_sex, rateclass=seg.rate_class,
            scale=1, band=seg.band,
        ) or [],
        mtp=rates_db.get_mtp(
            policy.plancode, seg.issue_age, seg.rate_sex,
            seg.rate_class, seg.band,
        ) or 0.0,
        ctp=rates_db.get_ctp(
            policy.plancode, seg.issue_age, seg.rate_sex,
            seg.rate_class, seg.band,
        ) or 0.0,
    )

    # Ratchet banding (RERUN PP-QX): load band-1 AND band-2 COI schedules for
    # each base segment. The regular path loads only the segment's own band; the
    # ratchet calc charges NAR up to the band break at band 1 and the excess at
    # band 2, so it needs both. The band break comes from BANDSPECS.
    if config.rachet_banding:
        for base_seg in policy.segments:
            result.segment_coi_band1[base_seg.coverage_phase] = rates_db.get_rates(
                "COI", policy.plancode, base_seg.issue_age, base_seg.rate_sex,
                base_seg.rate_class, scale=coi_scale, band=1,
            ) or []
            result.segment_coi_band2[base_seg.coverage_phase] = rates_db.get_rates(
                "COI", policy.plancode, base_seg.issue_age, base_seg.rate_sex,
                base_seg.rate_class, scale=coi_scale, band=2,
            ) or []
        result.band_break = rates_db.get_band_break(policy.plancode, band=2) or 0.0

    # Load PoAV (percent of AV charge) if configured
    if config.poav_code == "Table":
        result.poav = rates_db.get_rates(
            "POAV", policy.plancode, seg.issue_age, seg.rate_sex,
            seg.rate_class, scale=1, band=seg.band,
        ) or []

    # Load loan credit rates (plancode-only, no age/sex/band)
    if policy.has_loans:
        result.rlncrg = rates_db.get_rates("RLNCRG", policy.plancode) or []
        result.rlncrd = rates_db.get_rates("RLNCRD", policy.plancode) or []
        result.plncrg = rates_db.get_rates("PLNCRG", policy.plancode) or []
        result.plncrd = rates_db.get_rates("PLNCRD", policy.plancode) or []

    # Load shadow COI rates (uses CCV plancode, original band)
    if policy.has_shadow_account and config.shadow_plancode:
        result.shadow_coi = rates_db.get_rates(
            "COI", config.shadow_plancode, seg.issue_age, seg.rate_sex,
            seg.rate_class, scale=1, band=seg.original_band,
        ) or []

    # Load benefit COI rates — keyed by combined type+subtype string
    # Uses base insured sex/rateclass and policy band (per spec)
    # Benefits with type '#' are administrative/informational — skip entirely
    for ben in policy.benefits:
        if not ben.is_active:
            continue
        if (ben.benefit_type or "").startswith("#"):
            continue
        ben_key = (ben.benefit_type or "") + (ben.benefit_subtype or "")
        if not ben_key or ben_key in result.benefit_coi:
            continue
        ben_rates = rates_db.get_rates(
            "BENCOI", policy.plancode,
            issue_age=seg.issue_age,
            sex=seg.rate_sex,
            rateclass=seg.rate_class,
            scale=1,
            band=seg.band,
            benefit_type=ben_key,
        )
        result.benefit_coi[ben_key] = ben_rates or []

    # UL riders use the same UL_Rates COI tables as base coverages.
    # Same-plancode coverages are base segments and are intentionally not in
    # policy.riders; they will be handled by multi-segment base logic later.
    for rider in policy.riders:
        if not rider.is_active or not rider.plancode:
            continue
        result.rider_rates[rider.export_key] = _load_rider_coi_rates(rates_db, rider)

    return result
