from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional


@dataclass
class CoverageSegment:
    """A single base coverage segment."""

    # Identity
    coverage_phase: int = 1
    is_base: bool = True

    # Demographics (per-segment — may differ from policy-level)
    issue_date: Optional[date] = None
    issue_age: int = 0
    rate_sex: str = ""          # "M", "F", "U" — from LH_COV_INS_RNL_RT.RT_SEX_CD
    rate_class: str = ""        # "N", "S", "P", "Q", "R", "T"

    # Face / Units
    face_amount: float = 0.0
    original_face_amount: float = 0.0
    units: float = 0.0          # face_amount / 1000
    vpu: float = 1000.0

    # Band
    band: int = 1               # Rate band (1-5) based on face amount
    original_band: int = 1

    # Substandard
    table_rating: int = 0       # 0 = standard, 1-16 = table A-P
    table_cease_date: Optional[date] = None
    flat_extra: float = 0.0     # Per $1000 annual flat extra
    flat_cease_date: Optional[date] = None

    # Coverage status
    status: str = "A"           # "A" = active, "T" = terminated
    maturity_date: Optional[date] = None
    months_since_terminated: int = 0

    # COI
    coi_renewal_rate: Optional[float] = None


@dataclass
class BenefitInfo:
    """A single benefit/rider on a coverage (not used in M1)."""

    coverage_phase: int = 1
    form_number: str = ""
    benefit_type: str = ""          # SPM_BNF_TYP_CD
    benefit_subtype: str = ""       # SPM_BNF_SBY_CD
    benefit_amount: float = 0.0
    units: float = 0.0
    vpu: float = 0.0
    issue_date: Optional[date] = None
    issue_age: int = 0
    pay_up_date: Optional[date] = None
    cease_date: Optional[date] = None
    rating_factor: float = 0.0     # BNF_RT_FCT
    coi_rate: Optional[float] = None
    is_active: bool = True


@dataclass
class RiderInfo:
    """A rider coverage from LH_COV_PHA with a different plancode than base."""

    coverage_phase: int = 0
    occurrence: int = 1
    plancode: str = ""
    issue_date: Optional[date] = None
    issue_age: int = 0
    rate_sex: str = ""
    rate_class: str = ""
    face_amount: float = 0.0
    units: float = 0.0
    vpu: float = 1000.0
    band: int = 1
    table_rating: int = 0
    flat_extra: float = 0.0
    maturity_date: Optional[date] = None
    status: str = ""
    premium_rate: Optional[float] = None
    coi_rate: Optional[float] = None
    is_active: bool = True
    on_primary_insured: bool = False  # covers the base insured → face adds to illustrated DB
    cov_type: str = ""
    cease_age_dur: Optional[int] = None
    cease_use_code: str = ""
    description: str = ""

    @property
    def export_key(self) -> str:
        return f"{self.plancode}_{self.occurrence}"


@dataclass
class IllustrationPolicyData:
    """Complete policy data for UL illustration projection.

    Mutable by design — load from DB2 via build_illustration_data(),
    then override any field for what-if analysis before projecting.
    """

    # ── Identity ──────────────────────────────────────────────
    policy_number: str = ""
    region: str = "CKPR"
    company_code: str = ""
    reins_partner: str = ""         # "R" selects the RGA index-rate basis
    insured_name: str = ""

    # ── Plan / Product ────────────────────────────────────────
    plancode: str = ""
    product_type: str = ""          # "UL", "IUL", "SGUL"
    form_number: str = ""
    issue_state: str = ""
    company_sub: str = ""           # "ANICO", "EMC", etc.

    # ── Demographics (policy-level = base coverage) ───────────
    issue_date: Optional[date] = None
    issue_age: int = 0
    attained_age: int = 0
    insured_birth_date: Optional[date] = None  # Primary insured DOB (LH_CTT_CLIENT.BIR_DT)
    rate_sex: str = ""              # "M", "F", "U"
    rate_class: str = ""            # "N", "S", "P", "Q", "R", "T"

    # ── Face / Death Benefit ──────────────────────────────────
    face_amount: float = 0.0       # Total base face (sum of all base segments)
    units: float = 0.0
    db_option: str = "A"           # "A" (Level), "B" (Increasing), "C" (ROP)
    band: int = 1

    # ── Account Value ─────────────────────────────────────────
    account_value: float = 0.0     # Current total fund value
    cost_basis: float = 0.0
    system_coi_charge: float = 0.0
    system_expense_charge: float = 0.0
    system_other_charge: float = 0.0
    system_monthly_deduction: float = 0.0

    # ── Premium ───────────────────────────────────────────────
    modal_premium: float = 0.0
    annual_premium: float = 0.0
    billing_frequency: int = 1     # Months between payments
    premiums_paid_to_date: float = 0.0
    premiums_ytd: float = 0.0

    # ── Interest / Crediting ──────────────────────────────────
    guaranteed_interest_rate: float = 0.0
    current_interest_rate: float = 0.0

    # ── IUL Funds / Strategies ────────────────────────────────
    # Current fund value by fund ID (LH_POL_FND_VAL_TOT; includes SW sweep).
    fund_values: dict[str, float] = field(default_factory=dict)
    # Inforce premium allocation % by fund ID (LH_FND_ALC, type "P").
    premium_allocations: dict[str, float] = field(default_factory=dict)
    # Current UL_Rates values selected by illustration date. None means no lookup
    # was performed; an empty dict means a lookup ran but found no applicable row.
    index_illustration_rates: Optional[Dict[str, Optional[float]]] = None
    index_strategy_parameters: Optional[Dict[str, Dict[str, float]]] = None
    index_benchmark_minimum: Optional[float] = None
    index_benchmark_maximum: Optional[float] = None
    # Historical year-end market returns used by the IUL lookback report.
    # Each entry is {"date": date, "return": decimal return}.
    index_market_returns: Optional[Dict[str, List[Dict[str, object]]]] = None
    # Sweep account minimum.  # TODO: verify DB2 source (CyberLife segment 53)
    sweep_account_min: float = 0.0
    # Declared (fixed/sweep) crediting rate for the WAIR sweep slice (RERUN UJ =
    # PolicyRates!CH5). None → the engine falls back to the plan guaranteed
    # rate; the Inputs tab overrides it with the fixed-strategy illustrated rate.
    iul_declared_rate: Optional[float] = None
    # Σ IP/IR allocation × asset charge (RERUN SU before the regime gate).
    # None → computed from premium_allocations; the Inputs tab overrides it with
    # the allocation panel's blend.
    iul_asset_charge_rate: Optional[float] = None

    # ── Duration / Timing ─────────────────────────────────────
    illustration_date: Optional[date] = None
    policy_year: int = 1
    policy_month: int = 1          # 1-12 within year
    duration: int = 1              # Total months since issue
    valuation_date: Optional[date] = None
    maturity_age: int = 121

    # ── 7702 / Guideline ──────────────────────────────────────
    def_of_life_ins: str = "GPT"   # "GPT", "CVAT", or blank when not defined
    glp: float = 0.0
    gsp: float = 0.0
    accumulated_glp: float = 0.0
    corridor_percent: float = 100.0

    # ── Targets ───────────────────────────────────────────────
    mtp: float = 0.0              # Minimum Target Premium (monthly)
    accumulated_mtp: float = 0.0  # Accumulated MTP through valuation date
    map_cease_date: Optional[date] = None  # Minimum Accumulation Premium cease date
    ctp: float = 0.0              # Commission Target Premium (annual)

    # ── TAMRA / MEC ───────────────────────────────────────────
    is_mec: bool = False
    tamra_7pay_level: float = 0.0
    tamra_7pay_start_date: Optional[date] = None
    tamra_7pay_start_av: float = 0.0   # account value at the 7-pay period start (SVPY_BEG_CSV_AMT)
    tamra_7pay_cash_value: float = 0.0
    tamra_7year_lowest_db: float = 0.0
    tamra_7year_contributions: List[float] = field(default_factory=lambda: [0.0] * 7)

    # ── Loans ─────────────────────────────────────────────────
    regular_loan_principal: float = 0.0
    regular_loan_accrued: float = 0.0
    preferred_loan_principal: float = 0.0
    preferred_loan_accrued: float = 0.0
    preferred_loans_available: bool = False
    variable_loan_principal: float = 0.0
    variable_loan_accrued: float = 0.0
    variable_loan_charge_rate: Optional[float] = None

    # ── Withdrawals ───────────────────────────────────────────
    withdrawals_to_date: float = 0.0

    # ── Shadow Account ────────────────────────────────────────
    shadow_account_value: float = 0.0
    swam: float = 0.0
    ccv_active: bool = False            # True if benefit type "A" is active
    ccv_ceased: bool = False            # True if a benefit type "A" exists but has ceased
    ccv_units: float = 0.0              # CCV benefit units
    ccv_coi_rate: Optional[float] = None  # CCV rider COI rate (for regular-side charge)

    # ── CVAT / DCV ────────────────────────────────────────────
    deemed_cash_value: float = 0.0

    # ── Base Coverage Segments ───────────────────────────────
    segments: List[CoverageSegment] = field(default_factory=list)

    # ── Benefits / Riders ─────────────────────────────────────
    benefits: List[BenefitInfo] = field(default_factory=list)
    riders: List[RiderInfo] = field(default_factory=list)

    # ── Debug ─────────────────────────────────────────────────
    _debug_csv: float = 0.0

    # ── Computed Properties ───────────────────────────────────

    @property
    def total_face(self) -> float:
        return sum(s.face_amount for s in self.segments) if self.segments else self.face_amount

    @property
    def band_specified_amount(self) -> float:
        """Total face used for BASE band determination.

        The base specified amount (``total_face``) plus the face of any rider
        that bands as base coverage (e.g. ``1U144A00`` on IUL08 plans — see
        ``suiteview.core.band_rules``). Kept separate from ``total_face`` (death
        benefit / NAR), which must never include these riders. For a policy with
        no such rider this equals ``total_face`` exactly.
        """
        from suiteview.core.band_rules import rider_bands_as_base

        extra = sum(
            r.face_amount for r in self.riders
            if r.is_active and rider_bands_as_base(r.plancode)
        )
        return self.total_face + extra

    @property
    def total_units(self) -> float:
        return sum(s.units for s in self.segments) if self.segments else self.units

    @property
    def total_loan_balance(self) -> float:
        return (
            self.regular_loan_principal + self.regular_loan_accrued
            + self.preferred_loan_principal + self.preferred_loan_accrued
            + self.variable_loan_principal + self.variable_loan_accrued
        )

    @property
    def is_gpt(self) -> bool:
        return self.def_of_life_ins == "GPT"

    @property
    def is_cvat(self) -> bool:
        return self.def_of_life_ins == "CVAT"

    @property
    def has_defined_life_insurance(self) -> bool:
        return bool((self.def_of_life_ins or "").strip())

    @property
    def has_loans(self) -> bool:
        return self.total_loan_balance > 0

    @property
    def has_shadow_account(self) -> bool:
        """True if policy has an active shadow account (CCV benefit or inherent)."""
        return self.ccv_active

    @property
    def is_smoker(self) -> bool:
        return self.rate_class.upper() in ("S", "Q")

    @property
    def base_segment(self) -> Optional[CoverageSegment]:
        return self.segments[0] if self.segments else None

    def segment_for_phase(self, coverage_phase: int) -> Optional[CoverageSegment]:
        """Return the coverage segment for a phase, falling back to the base."""
        for seg in self.segments:
            if seg.coverage_phase == coverage_phase:
                return seg
        return self.base_segment


def benefit_rate_keys(benefits: List[BenefitInfo]) -> Dict[int, str]:
    """Map each benefit object (by ``id()``) to a stable, unique schedule key.

    Multiple benefits can legitimately share a ``type+subtype`` (rare, but valid
    — e.g. two type-11 benefits). The COI-rate schedule and the per-benefit
    breakdown must be keyed uniquely per benefit instance or the later one
    silently reuses/overwrites the earlier. The first occurrence of a
    ``type+subtype`` keeps the bare key; duplicates get ``#2``, ``#3`` suffixes,
    numbered by their position in ``benefits`` so keys stay stable regardless of
    later sorting or which benefits are active in a given month.
    """
    counts: Dict[str, int] = {}
    keys: Dict[int, str] = {}
    for ben in benefits:
        type_subtype = (ben.benefit_type or "") + (ben.benefit_subtype or "")
        occurrence = counts.get(type_subtype, 0) + 1
        counts[type_subtype] = occurrence
        keys[id(ben)] = type_subtype if occurrence == 1 else f"{type_subtype}#{occurrence}"
    return keys


def benefit_rate_issue_age(policy: IllustrationPolicyData, benefit: BenefitInfo) -> int:
    """Rate-table issue age for a benefit's COI lookup.

    CyberLife looks up a benefit's renewal COI rate by the *attained age of the
    coverage phase the benefit is assigned to*, regardless of the benefit's own
    stored ``BNF_ISS_AGE``. Our rates are loaded by issue age + duration, so we
    reconstruct that behaviour: the rate issue age is the assigned coverage
    segment's issue age plus the number of complete coverage anniversaries
    elapsed between that segment's issue date and the date the benefit was added.
    Combined with the existing duration logic (which steps from the benefit's own
    issue date), the looked-up attained age tracks the coverage's attained age.

    For a benefit added at (its coverage's) issue this equals the stored issue
    age; for a benefit added mid-term it can be a year lower than the stored true
    age (e.g. base issued at 26, benefit added after 2 complete years → 28, not
    the stored 29).
    """
    segment = policy.segment_for_phase(benefit.coverage_phase)
    if segment is None or segment.issue_date is None or benefit.issue_date is None:
        return benefit.issue_age
    elapsed = benefit.issue_date.year - segment.issue_date.year
    if (benefit.issue_date.month, benefit.issue_date.day) < (
        segment.issue_date.month,
        segment.issue_date.day,
    ):
        elapsed -= 1
    elapsed = max(0, elapsed)
    return segment.issue_age + elapsed


def rider_effective_maturity_date(rider: RiderInfo, policy: IllustrationPolicyData) -> Optional[date]:
    """Return the maturity date that should control rider activity."""
    if _is_ctr_cease_rider(rider):
        maturity_date = _ctr_cease_date(rider, policy)
        if maturity_date is not None:
            return maturity_date
    return rider.maturity_date


def rider_active_on(rider: RiderInfo, policy: IllustrationPolicyData, projection_date: Optional[date]) -> bool:
    if not rider.is_active:
        return False
    maturity_date = rider_effective_maturity_date(rider, policy)
    if maturity_date is not None and projection_date is not None and projection_date >= maturity_date:
        return False
    return True


def _is_ctr_cease_rider(rider: RiderInfo) -> bool:
    return (
        (rider.cov_type or "").upper() == "CTR"
        and (rider.cease_use_code or "").upper() in {"AGE", "DUR"}
        and rider.cease_age_dur is not None
    )


def _ctr_cease_date(rider: RiderInfo, policy: IllustrationPolicyData) -> Optional[date]:
    first = _first_coverage(policy)
    issue_date = (first.issue_date if first is not None else None) or policy.issue_date
    if issue_date is None:
        return None

    cease_use_code = (rider.cease_use_code or "").upper()
    if cease_use_code == "AGE":
        issue_age = _first_coverage_issue_age(policy, first)
        years_to_cease = max(0, int(rider.cease_age_dur or 0) - issue_age)
    else:
        years_to_cease = max(0, int(rider.cease_age_dur or 0))
    return _add_years(issue_date, years_to_cease)


def _first_coverage(policy: IllustrationPolicyData) -> Optional[CoverageSegment]:
    segments = list(policy.segments or [])
    if not segments:
        return None
    return min(
        segments,
        key=lambda segment: (
            segment.issue_date or policy.issue_date or date.max,
            segment.coverage_phase,
        ),
    )


def _first_coverage_issue_age(policy: IllustrationPolicyData, first: Optional[CoverageSegment]) -> int:
    if first is not None and first.issue_age:
        return int(first.issue_age)
    return int(policy.issue_age or 0)


def _add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)
