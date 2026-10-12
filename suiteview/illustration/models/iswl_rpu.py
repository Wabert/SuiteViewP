"""Interest sensitive whole life on reduced paid-up (ISWL RPU) in-force illustration data.

When an ISWL policy (CyberLife advanced product, base product line ``I``) is converted to
reduced paid-up (premium pay status ``45``) CyberLife treats it as traditional (CyberDoc
B10 p.57): no premiums, no account value, a level paid-up face, and a cash value from
the net single premiums (NSPs) stored on the base coverage and extended one year at each
anniversary (``core/iswl_rpu/nsp_roll.py``). ``ISWLRPUPolicy`` is the in-force snapshot,
``ISWLRPUInputs`` the illustration choices and ``ISWLRPUResult`` the monthly rows, the
NSP schedule and the annual ledger built from them. Amounts are dollars; NSPs are per
$1,000 (the value per unit is $1,000 on every coverage illustrated).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Tuple

from dateutil.relativedelta import relativedelta

STATUS_RPU = "45"
ISWL_PRODUCT_LINE = "I"
STORED_NSP_COLUMNS = ("LOW_DUR_NSP_AMT", "LOW_DUR_1_NSP_AMT", "LOW_DUR_2_NSP_AMT")

SOURCE_STORED = "stored"
SOURCE_ROLLED = "rolled"
SOURCE_NEGATIVE = "negative"


@dataclass(frozen=True)
class ISWLRPUBenefit:
    """A supplemental benefit left on the record (``LH_SPM_BNF``); shown, not valued."""

    phase: int
    code: str
    description: str
    form_number: str
    units: float
    value_per_unit: float
    annual_premium_per_unit: float
    issue_date: Optional[date]
    cease_date: Optional[date]


@dataclass(frozen=True)
class ISWLRPULoan:
    """A loan row on the record: traditional (``LH_CSH_VAL_LOAN``) or advanced (``LH_FND_VAL_LOAN``)."""

    table: str
    as_of: Optional[date]                   # MVRY_DT (12/31/9999 = current)
    principal: float
    accrued_interest: float
    rate: Optional[float]                   # LN_CRG_ITS_RT as a decimal
    current: bool                           # a loan the RPU policy carries now

    @property
    def balance(self) -> float:
        return round(self.principal + self.accrued_interest, 2)


@dataclass(frozen=True)
class ISWLRPUPolicy:
    """In-force snapshot of an ISWL policy on reduced paid-up."""

    policy_number: str
    company_code: str
    region: str
    insured_name: str
    issue_state: str
    phase: int
    plancode: str
    form_number: str
    description: str
    issue_date: date
    issue_age: int
    rate_sex: str
    sex_description: str
    rate_class: str
    premium_status: str
    premium_status_description: str
    valuation_date: date                    # PolView's NSP cash value date (last processed monthliversary)
    last_anniversary: Optional[date]
    paid_to_date: Optional[date]
    last_account_value_date: Optional[date]  # last UL monthliversary value (before the conversion)
    units: float
    value_per_unit: float
    maturity_date: date
    nsp_table: str                          # NSP_RPU_TBL_CD
    eti_table: str                          # NSP_EI_TBL_CD
    nsp_interest: float                     # NSP_ITS_RT as a decimal
    rpu_benefit_code: str                   # RPU_BNF_CD
    low_duration: int                       # LOW_DUR_PER
    stored_nsp: Tuple[float, float, float]  # per $1,000 at LOW_DUR_PER, +1, +2
    polview_cash_value: Optional[float] = None   # PolView's NSP cash value (rates.guaranteed_cash_value)
    polview_reason: str = ""
    # MTL_FUN_CD (CyberDoc D20 p.94): the NSP claims basis, 0 curtate, 1/2 claims paid at death
    # (core/parwl/nsp.claims_factor_for). None (not loaded) falls back to the table's age basis.
    mortality_function_code: Optional[str] = None
    record_death_benefit: Optional[float] = None
    benefits: Tuple[ISWLRPUBenefit, ...] = ()
    loans: Tuple[ISWLRPULoan, ...] = ()
    other_coverages: Tuple[str, ...] = ()
    run_block: str = ""                     # why Run Values is refused ("" = allowed)
    notes: Tuple[str, ...] = ()

    @property
    def face_amount(self) -> float:
        return round(self.units * self.value_per_unit, 2)

    @property
    def maturity_duration(self) -> int:
        delta = relativedelta(self.maturity_date, self.issue_date)
        return delta.years

    @property
    def maturity_age(self) -> int:
        return self.issue_age + self.maturity_duration

    @property
    def current_loans(self) -> Tuple[ISWLRPULoan, ...]:
        return tuple(loan for loan in self.loans if loan.current)

    @property
    def loan_balance(self) -> float:
        return round(sum(loan.balance for loan in self.current_loans), 2)


@dataclass
class ISWLRPUInputs:
    """Illustration choices: a paid-up policy has nothing to pay, withdraw or change."""

    end_age: Optional[int] = None           # stop at this attained age (maturity when None)


@dataclass(frozen=True)
class NSPValue:
    """The NSP per $1,000 at one policy duration (anniversary), on both bases."""

    duration: int
    anniversary: date
    age: int                                # issue age + duration
    carry: float                            # stored, or rolled and carried to 6 decimals
    per_unit: float                         # the value the cash value uses (rolled values in cents)
    source: str                             # stored / rolled / negative
    column: str = ""                        # the stored column, when stored
    comparison: Optional[float] = None      # paid-up endowment NSP at ``age`` (nsp_roll.endowment_nsp)

    @property
    def difference(self) -> Optional[float]:
        return None if self.comparison is None else self.per_unit - self.comparison


@dataclass
class ISWLRPUMonth:
    """One monthliversary of the projection."""

    index: int
    when: date
    policy_year: int
    month_of_year: int                      # completed months since the anniversary (0-11)
    duration: int                           # completed policy years
    attained_age: int
    boy_nsp: float
    eoy_nsp: float
    nsp: float                              # interpolated NSP per $1,000
    cash_value: float                       # CyberLife basis
    comparison_nsp: Optional[float]
    comparison_cash_value: Optional[float]
    death_benefit: float
    loan: float = 0.0
    frozen: bool = False                    # past CyberLife's last NSP update (unverified)
    notes: str = ""


@dataclass
class ISWLRPUYear:
    """One policy year of the annual ledger (end-of-year values)."""

    policy_year: int
    end_date: date
    age: int                                # attained age at the year's end
    nsp: float
    cash_value: float
    comparison_nsp: Optional[float]
    comparison_cash_value: Optional[float]
    death_benefit: float
    loan: float = 0.0
    frozen: bool = False
    notes: str = ""

    @property
    def difference(self) -> Optional[float]:
        if self.comparison_cash_value is None:
            return None
        return round(self.cash_value - self.comparison_cash_value, 2)


@dataclass
class ISWLRPUResult:
    """An ISWL RPU projection."""

    policy: ISWLRPUPolicy
    inputs: ISWLRPUInputs
    schedule: List[NSPValue]
    months: List[ISWLRPUMonth]
    years: List[ISWLRPUYear]
    peak: Optional[NSPValue] = None         # highest CyberLife-basis NSP from the valuation date on
    negative: Optional[NSPValue] = None     # first rolled NSP below zero
    freeze_from: Optional[date] = None      # anniversary from which values are held (unverified)
    divergence_from: Optional[int] = None   # first ledger year the bases differ materially
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
