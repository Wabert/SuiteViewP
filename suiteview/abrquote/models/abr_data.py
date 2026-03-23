"""
ABR Quote — data classes for inputs, outputs, and intermediate results.

All dataclasses are pure Python — no UI or database dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional, List, Tuple

from .abr_constants import (
    MORTALITY_IMPROVEMENT_RATE,
    MORTALITY_IMPROVEMENT_CAP,
    MORTALITY_MULTIPLIER_TERMINAL,
)


@dataclass
class RiderInfo:
    """Per-rider/benefit data for computing annual premium from TERM tables.

    Each rider corresponds to a non-base coverage + benefit combination.
    The rate lookup path depends on whether benefit_type is populated:
        - If benefit_type is set: use db.get_benefit_rate(plancode, benefit_type,
          benefit_subtype, ...) → TERM_POINT_BENEFIT → TERM_RATE_BEN
        - Else: use db.get_term_rate(plancode, ...) → TERM_POINT_PVSRB → TERM_RATE_PREM

    rider_type determines the premium formula:
        "PW"    — Premium Waiver: round(round(rate × pw_sub, 2) × face/1000, 2)
                  pw_sub: 1.50 for table 1, 2.25 for table 2, else 1.0
        "CTR"   — Children's Term: round(rate × face/1000, 2)  (no substandard)
        "OTHER" — Use CyberLife cov_annual_premium as-is (fallback_premium)
    """
    plancode: str = ""
    face_amount: float = 0.0
    issue_age: int = 0
    sex: str = ""              # "M", "F", "U"
    rate_class: str = ""       # actual for PW, "0" for CTR
    table_rating: int = 0      # PW table rating (1 or 2; 0=standard)
    rider_type: str = "OTHER"  # "PW", "CTR", "COVERAGE", "OTHER"
    fallback_premium: float = 0.0  # CyberLife annual premium for "OTHER" riders
    # Benefit fields (from LH_SPM_BNF via get_benefits())
    benefit_type: str = ""     # SPM_BNF_TYP_CD (e.g. "W", "C", "4")
    benefit_subtype: str = ""  # SPM_BNF_SBY_CD
    benefit_units: float = 0.0 # BNF_UNT_QTY (for display)
    benefit_vpu: float = 0.0   # BNF_VPU_AMT (for display)
    benefit_rating_factor: float = 0.0 # BNF_RT_FCT (factor applied to PW rate)
    cease_date: Optional[date] = None  # BNF_CEA_DT (skip if expired)



@dataclass
class ABRPolicyData:
    """Policy data extracted from PolView PolicyInformation or manual entry."""

    policy_number: str = ""
    region: str = "CKPR"
    company: str = ""

    # Demographics
    issue_age: int = 0
    attained_age: int = 0
    sex: str = ""                    # "M", "F", "U" — true sex from 02 segment
    rate_sex: str = ""               # RT_SEX_CD from 67 segment (rate table sex)
    rate_class: str = ""             # "N", "S", "P", "Q", "R", "T"

    # Policy details
    face_amount: float = 0.0
    min_face_amount: float = 50_000.0
    issue_date: Optional[date] = None
    maturity_age: int = 95
    issue_state: str = ""            # 2-letter state code
    plan_code: str = ""              # e.g. "B75TL400"
    base_plancode: str = ""          # PLN_BSE_SRE_CD (plan base series)
    billing_mode: int = 1            # 1=A, 2=SA, 3=Q, 4=DM, 5=PAC, 6=BiWeekly

    # Duration
    policy_month: int = 1
    policy_year: int = 1

    # Substandard
    table_rating: int = 0            # numeric: A=1, B=2, ... G=7, 0=standard
    flat_extra: float = 0.0          # per $1000
    flat_to_age: int = 0
    flat_cease_date: Optional[date] = None

    # Premium/payment
    paid_to_date: Optional[date] = None
    modal_premium: float = 0.0
    annual_premium: float = 0.0
    rider_annual_premium: float = 0.0    # sum of non-base coverage annual premiums (legacy, CyberLife)
    riders: List[RiderInfo] = field(default_factory=list)  # per-rider data for TERM table lookups

    # Insured name (for output)
    insured_name: str = ""

    @property
    def is_smoker(self) -> bool:
        return self.rate_class.upper() in ("S", "Q", "T")

    @property
    def face_per_thousand(self) -> float:
        return self.face_amount / 1000.0


@dataclass
class MedicalAssessment:
    """Medical assessment inputs from the user (Step 2 of wizard)."""

    rider_type: str = "Terminal"       # "Terminal", "Chronic", or "Critical"

    # Checkbox flags — which inputs are active
    use_five_year: bool = False
    use_ten_year: bool = False
    use_le: bool = False
    use_table: bool = False
    use_flat: bool = False
    use_table_2: bool = False
    use_flat_2: bool = False
    use_return_5yr: bool = False          # return to normal after 5yr survival
    use_return_10yr: bool = False         # return to normal after 10yr survival
    in_lieu_of: bool = True               # True = drop policy substandards; False = keep them

    # Survival inputs
    five_year_survival: float = 0.0               # e.g. 0.018 (1.8%)
    ten_year_survival: float = 0.0                # e.g. 0.500 (50%)
    life_expectancy_years: float = 0.0            # e.g. 4.9

    # Direct table / flat inputs (set 1)
    direct_table_rating: float = 0.0              # direct table rating value
    table_start_year: int = 1
    table_stop_year: int = 99
    direct_flat_extra: float = 0.0                # per $1000/year
    flat_start_year: int = 1
    flat_stop_year: int = 99

    # Direct table / flat inputs (set 2)
    direct_table_rating_2: float = 0.0
    table_2_start_year: int = 1
    table_2_stop_year: int = 99
    direct_flat_extra_2: float = 0.0
    flat_2_start_year: int = 1
    flat_2_stop_year: int = 99

    # Derived values (from goal seek or direct)
    life_expectancy_rounded: int = 0              # rounded to nearest integer
    derived_table_rating: float = 0.0             # continuous, from goal seek or direct
    derived_table_rating_5yr: float = 0.0         # table rating for 5yr solve
    derived_table_rating_10yr: float = 0.0        # table rating for 10yr solve (years 6-10)
    derived_flat_extra: float = 0.0               # per $1000/year
    derived_increased_decrement: float = 0.0      # e.g. 200 (%)
    assessment_index: int = 0                     # 1-7 mapped from table rating letter

    # Computed output values (from mortality engine after applying substandard)
    computed_survival_5yr: float = 0.0            # modified 5yr survival probability
    computed_survival_10yr: float = 0.0           # modified 10yr survival probability
    computed_le: float = 0.0                      # modified life expectancy in years


@dataclass
class MortalityParams:
    """Parameters controlling the mortality calculation engine."""

    issue_age: int = 0
    sex: str = ""
    rate_class: str = ""

    # Policy duration
    policy_month: int = 1
    maturity_age: int = 95

    # Table ratings (may have two periods)
    # NOTE: table_rating is a CONTINUOUS float (not limited to 0-25).
    # The VBA workbook uses Excel GoalSeek which sets this to whatever value
    # produces the target survival probability. For a terminally ill young
    # insured, this can be in the 1000s-10000s range.
    table_rating_1: float = 0.0       # first table rating value (continuous)
    table_1_start_month: int = 1
    table_1_last_month: int = 9999
    table_rating_2: float = 0.0       # second table rating (for mid-policy changes)
    table_2_start_month: int = 0
    table_2_last_month: int = 0

    # Flat extras (may have two periods)
    flat_extra_1: float = 0.0         # per $1000/year → converted to monthly in engine
    flat_1_start_month: int = 1       # first applicable month
    flat_1_duration: int = 9999       # last applicable month
    flat_extra_2: float = 0.0
    flat_2_duration: int = 0

    # Additional table/flat periods layered on top (from direct user inputs)
    # Each entry: (rating_or_amount, start_month, last_month)
    additional_tables: List[Tuple[float, int, int]] = field(default_factory=list)
    additional_flats: List[Tuple[float, int, int]] = field(default_factory=list)

    # Mortality adjustments (defaults from abr_constants)
    mortality_multiplier: float = MORTALITY_MULTIPLIER_TERMINAL
    improvement_rate: float = MORTALITY_IMPROVEMENT_RATE
    improvement_cap: int = MORTALITY_IMPROVEMENT_CAP

    # Rider type affects calculation path
    is_terminal: bool = True


@dataclass
class APVResult:
    """Results from the Actuarial Present Value calculation."""

    pvfb: float = 0.0               # Present Value of Future Benefits
    pvfp: float = 0.0               # Present Value of Future Premiums
    pvfd: float = 0.0
    """Present Value of Future Dividends.

    Placeholder — always 0.0 for term products (which do not pay
    dividends).  Retained for ABR regulatory form compliance where
    the PVFD line item must be shown even when zero.
    """
    actuarial_discount: float = 0.0

    # Supporting values
    monthly_interest_rate: float = 0.0
    continuous_mort_adj: float = 0.0
    annual_interest_rate: float = 0.0


@dataclass
class PremiumResult:
    """Results from the term premium calculation."""

    base_rate: float = 0.0           # base rate per $1000 from rate table
    table_rate: float = 0.0          # additional rate from table rating
    flat_rate: float = 0.0           # additional flat extra rate
    total_rate: float = 0.0          # base + table + flat (rounded)
    policy_fee: float = 0.0          # annual policy fee
    annual_premium: float = 0.0      # total annual premium
    modal_premium: float = 0.0       # premium per billing period
    modal_label: str = ""            # e.g. "Monthly"
    lookup_key: str = ""             # rate table lookup key used


@dataclass
class ABRQuoteResult:
    """Final ABR Quote output — full and partial acceleration."""

    # Full Acceleration
    full_eligible_db: float = 0.0
    full_actuarial_discount: float = 0.0
    full_admin_fee: float = 0.0
    full_accel_benefit: float = 0.0
    full_benefit_ratio: float = 0.0

    # Max Partial Acceleration
    partial_eligible_db: float = 0.0
    partial_actuarial_discount: float = 0.0
    partial_admin_fee: float = 0.0
    partial_accel_benefit: float = 0.0
    partial_benefit_ratio: float = 0.0

    # Premium info
    premium_before: str = ""          # e.g. "59.18 Monthly"
    premium_after_full: float = 0.0   # always 0 for full acceleration
    premium_after_partial: str = ""   # min face premium for partial

    # Supporting details
    plan_description: str = ""
    abr_interest_rate: float = 0.0
    quote_date: Optional[date] = None

    # APV components (for audit display)
    apv_fb: float = 0.0               # PV of Future Benefits (full accel)
    apv_fp: float = 0.0               # PV of Future Premiums (full accel)
    apv_fd: float = 0.0               # PV of Future Dividends (always 0 for term)

    # Per diem
    per_diem_daily: float = 0.0
    per_diem_annual: float = 0.0

    # Validation messages
    messages: List[str] = field(default_factory=list)
