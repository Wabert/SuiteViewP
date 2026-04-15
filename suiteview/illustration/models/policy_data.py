from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional


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
    benefit_type: str = ""          # SPM_BNF_TYP_CD
    benefit_subtype: str = ""       # SPM_BNF_SBY_CD
    benefit_amount: float = 0.0
    units: float = 0.0
    vpu: float = 0.0
    issue_date: Optional[date] = None
    issue_age: int = 0
    cease_date: Optional[date] = None
    rating_factor: float = 0.0     # BNF_RT_FCT
    coi_rate: Optional[float] = None
    is_active: bool = True


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

    # ── Premium ───────────────────────────────────────────────
    modal_premium: float = 0.0
    annual_premium: float = 0.0
    billing_frequency: int = 1     # Months between payments
    premiums_paid_to_date: float = 0.0
    premiums_ytd: float = 0.0

    # ── Interest / Crediting ──────────────────────────────────
    guaranteed_interest_rate: float = 0.0
    current_interest_rate: float = 0.0

    # ── Duration / Timing ─────────────────────────────────────
    policy_year: int = 1
    policy_month: int = 1          # 1-12 within year
    duration: int = 1              # Total months since issue
    valuation_date: Optional[date] = None
    maturity_age: int = 121

    # ── 7702 / Guideline ──────────────────────────────────────
    def_of_life_ins: str = "GPT"   # "GPT" or "CVAT"
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
    tamra_7pay_cash_value: float = 0.0
    tamra_7year_lowest_db: float = 0.0
    tamra_7year_contributions: List[float] = field(default_factory=lambda: [0.0] * 7)

    # ── Loans ─────────────────────────────────────────────────
    regular_loan_principal: float = 0.0
    regular_loan_accrued: float = 0.0
    preferred_loan_principal: float = 0.0
    preferred_loan_accrued: float = 0.0
    variable_loan_principal: float = 0.0
    variable_loan_accrued: float = 0.0

    # ── Withdrawals ───────────────────────────────────────────
    withdrawals_to_date: float = 0.0

    # ── Shadow Account ────────────────────────────────────────
    shadow_account_value: float = 0.0
    swam: float = 0.0
    ccv_active: bool = False            # True if benefit type "A" is active
    ccv_units: float = 0.0              # CCV benefit units
    ccv_coi_rate: Optional[float] = None  # CCV rider COI rate (for regular-side charge)

    # ── CVAT / DCV ────────────────────────────────────────────
    deemed_cash_value: float = 0.0

    # ── Base Coverage Segments ───────────────────────────────
    segments: List[CoverageSegment] = field(default_factory=list)

    # ── Benefits / Riders ─────────────────────────────────────
    benefits: List[BenefitInfo] = field(default_factory=list)

    # ── Debug ─────────────────────────────────────────────────
    _debug_csv: float = 0.0

    # ── Computed Properties ───────────────────────────────────

    @property
    def total_face(self) -> float:
        return sum(s.face_amount for s in self.segments) if self.segments else self.face_amount

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
    def has_loans(self) -> bool:
        return self.total_loan_balance > 0

    @property
    def has_shadow_account(self) -> bool:
        """True if policy has an active shadow account (CCV benefit or inherent)."""
        return self.ccv_active

    @property
    def is_smoker(self) -> bool:
        return self.rate_class.upper() in ("S", "Q", "T")

    @property
    def base_segment(self) -> Optional[CoverageSegment]:
        return self.segments[0] if self.segments else None
