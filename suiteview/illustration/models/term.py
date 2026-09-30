"""Indeterminate premium term (IPT) in-force illustration data: snapshot, inputs, results.

An indeterminate premium term policy (``LH_BAS_POL.IDT_PRM_IND = '1'``) is a traditional
fixed-premium CyberLife term policy whose premium rates may change: the company charges
a current premium scale (schema ``rates`` PREM scale ``C``) that it can raise up to the
guaranteed maximum scale (scale ``G``). The base coverage is typically level for an
initial period (``INT_RNL_PER`` years) and then renews annually by attained age (ART).
There are no cash values; the illustration shows the current and guaranteed premiums
and the death benefit year by year.

``TermPolicy`` is the in-force snapshot, ``TermInputs`` the illustration choices and
``TermResult`` the monthly premium rows plus the annual ledger built from them.
Amounts are dollars; rates are premiums per unit per year.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Tuple

ROLE_BASE = "BASE"
ROLE_RIDER = "RIDER"

STATUS_PREMIUM_PAYING = "22"
STATUS_WAIVER = "32"
PREMIUM_PAYING_STATUSES = frozenset({"21", "22"})

SCALE_CURRENT = "C"
SCALE_GUARANTEED = "G"


@dataclass(frozen=True)
class TermExtra:
    """A substandard extra premium on a coverage (``LH_SST_XTR_CRG``)."""

    type_code: str                          # SST_XTR_TYP_CD
    per_unit: Optional[float]               # SST_XTR_UNT_AMT: annual extra per unit
    percent: Optional[float]                # SST_XTR_PCT
    table_code: str                         # SST_XTR_RT_TBL_CD
    cease_date: Optional[date]              # SST_XTR_CEA_DT


@dataclass(frozen=True)
class TermCoverage:
    """One LH_COV_PHA coverage phase (the base term coverage or a rider)."""

    phase: int
    plancode: str
    role: str                               # BASE / RIDER
    form_number: str
    description: str                        # official plancode common name
    product_line: str                       # PRD_LIN_TYP_CD
    issue_date: date
    issue_age: int
    rate_sex: str                           # schema rates sex M/F/U
    sex_description: str
    rate_class: str
    band_code: str
    units: float
    value_per_unit: float
    annual_premium_per_unit: float          # ANN_PRM_UNT_AMT (current period rate)
    pay_up_date: Optional[date]             # end of the current premium period
    maturity_date: Optional[date]
    renewable_code: str                     # RENEWABLE_PRM_CD: C renewable, E select renewable
    initial_renewal_period: int             # INT_RNL_PER (level period, years)
    renewal_start_duration: int             # SBQ_RNL_STR_DUR
    renewal_period: int                     # SBQ_RNL_PER (1 = annual renewable)
    guaranteed_period_months: int = 0       # IDT_PRM_GUA_PER
    table_rating: int = 0
    extras: Tuple[TermExtra, ...] = ()
    next_renewal_rate: Optional[float] = None   # LH_COV_INS_RNL_RT type C (next period, per unit)
    next_change_date: Optional[date] = None     # NXT_CHG_DT

    @property
    def face_amount(self) -> float:
        return round(self.units * self.value_per_unit, 2)


@dataclass(frozen=True)
class TermBenefit:
    """A supplemental benefit (LH_SPM_BNF): premium waiver, ADB, children's benefits..."""

    phase: int
    code: str                               # type + subtype
    type_code: str
    description: str
    form_number: str
    units: float
    value_per_unit: float
    annual_premium_per_unit: float          # BNF_ANN_PPU_AMT
    rate_factor: float
    issue_date: Optional[date]
    issue_age: Optional[int]
    cease_date: Optional[date]
    pay_up_date: Optional[date] = None
    renews: bool = False                    # RNL_RT_IND = 1
    renewal_rate: Optional[float] = None    # LH_BNF_INS_RNL_RT (next period)

    @property
    def annual_premium(self) -> float:
        return round(self.units * self.annual_premium_per_unit * self.rate_factor, 2)


@dataclass(frozen=True)
class TermPolicy:
    """In-force snapshot of an indeterminate premium term policy."""

    policy_number: str
    company_code: str
    region: str
    insured_name: str
    issue_state: str
    issue_date: date
    valuation_date: date
    last_anniversary: date
    paid_to_date: Optional[date]
    billing_frequency: int                  # months between premiums (12, 6, 3, 1)
    bill_form: str
    modal_premium: float                    # POL_PRM_AMT
    forced_premium: bool
    premium_status: str
    premium_status_description: str
    indeterminate: bool                     # IDT_PRM_IND = 1
    coverages: Tuple[TermCoverage, ...]
    benefits: Tuple[TermBenefit, ...] = ()
    notes: Tuple[str, ...] = ()

    @property
    def base(self) -> TermCoverage:
        return next(c for c in self.coverages if c.role == ROLE_BASE)

    @property
    def riders(self) -> Tuple[TermCoverage, ...]:
        return tuple(c for c in self.coverages if c.role == ROLE_RIDER)

    @property
    def is_waiver(self) -> bool:
        return self.premium_status == STATUS_WAIVER

    @property
    def premium_paying(self) -> bool:
        return self.premium_status in PREMIUM_PAYING_STATUSES or self.is_waiver


@dataclass
class TermInputs:
    """Illustration choices (all optional; the defaults project the record)."""

    billing_frequency: Optional[int] = None     # illustrate another mode (12, 6, 3, 1)
    bill_form: Optional[str] = None
    drop_riders: List[int] = field(default_factory=list)       # coverage phases removed
    drop_benefits: List[str] = field(default_factory=list)     # benefit codes removed
    end_age: Optional[int] = None                              # stop at this attained age
    stop_at: Optional[date] = None                             # lapse / stop paying on this date


@dataclass
class TermPremiumPart:
    """One element of a modal premium (a coverage, benefit, extra or the fee)."""

    label: str
    kind: str                               # coverage / benefit / extra / fee
    phase: int
    rate: float                             # annual rate per unit (0 for the fee)
    current: float                          # modal amount on the current scale
    guaranteed: float                       # modal amount on the guaranteed scale


@dataclass
class TermMonth:
    """One premium due date (or month) of the projection."""

    index: int
    when: date
    policy_year: int
    month_of_year: int
    attained_age: int
    premium_due: bool = False
    current_premium: float = 0.0
    guaranteed_premium: float = 0.0
    parts: List[TermPremiumPart] = field(default_factory=list)
    death_benefit: float = 0.0
    rider_death_benefit: float = 0.0
    period: str = ""                        # level / renewal / ART
    notes: str = ""


@dataclass
class TermYear:
    """One policy year of the annual ledger."""

    policy_year: int
    end_date: date
    age: int                                # attained age at the year's end
    current_premium: float
    guaranteed_premium: float
    death_benefit: float
    rider_death_benefit: float
    period: str


@dataclass
class TermResult:
    """An indeterminate premium term projection."""

    policy: TermPolicy
    inputs: TermInputs
    months: List[TermMonth]
    years: List[TermYear]
    notes: List[str] = field(default_factory=list)
