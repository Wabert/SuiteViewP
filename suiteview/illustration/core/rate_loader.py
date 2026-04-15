from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

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
    epu: List = field(default_factory=list)
    scr: List = field(default_factory=list)
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


def load_rates(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
) -> IllustrationRates:
    """Load all rate arrays for the policy's base segment.

    Uses the Rates class to fetch from UL_Rates SQL Server database.
    Rates are cached at the Rates class level.
    """
    rates_db = Rates()
    seg = policy.base_segment

    if seg is None:
        return IllustrationRates()

    result = IllustrationRates(
        coi=rates_db.get_rates(
            "COI", policy.plancode, seg.issue_age, seg.rate_sex,
            seg.rate_class, scale=1, band=seg.band,
        ) or [],
        epu=rates_db.get_rates(
            "EPU", policy.plancode, seg.issue_age, seg.rate_sex,
            seg.rate_class, scale=1, band=seg.band,
        ) or [],
        scr=rates_db.get_rates(
            "SCR", policy.plancode, seg.issue_age, seg.rate_sex,
            seg.rate_class, scale=1, band=seg.band,
        ) or [],
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

    return result
